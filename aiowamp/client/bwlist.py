from __future__ import annotations

import bisect
from typing import Container, Iterable, List, Optional, Set, TypeVar, Union

import aiowamp

__all__ = ["BlackWhiteList"]

BWItemType = Union[int, str]


class BlackWhiteList(Container[BWItemType]):
    """Data type for black- and whitelisting subscribers.

    BlackWhiteList is quite a mouthful, so let's use bwlist for short.

    If both exclusion and eligible rules are present, the Broker
    will dispatch events published only to Subscribers that are not explicitly
    excluded and which are explicitly eligible.

    Like `list`, an empty bwlist is falsy
    (i.e. `bool(BlackWhiteList()) is False`).

    bwlist is also a container (i.e. support `x in bwlist`), it returns whether
    the given key will receive the event with the current constraints.

    bwlist will keep the constraint lists in ascending order and its methods are
    optimised under the assumption that the order is maintained.
    """
    __slots__ = ("excluded_ids", "excluded_auth_ids", "excluded_auth_roles",
                 "eligible_ids", "eligible_auth_ids", "eligible_auth_roles")

    excluded_ids: Optional[List[int]]
    """Excluded session ids.
    
    Only subscribers whose session id IS NOT in this list will receive the event.
    """
    excluded_auth_ids: Optional[List[str]]
    """Excluded auth ids."""
    excluded_auth_roles: Optional[List[str]]
    """Excluded auth roles."""

    eligible_ids: Optional[List[int]]
    """Eligible session ids.
    
    Only subscribers whose session id IS in this list will receive the event.
    """
    eligible_auth_ids: Optional[List[str]]
    """Eligible auth ids."""
    eligible_auth_roles: Optional[List[str]]
    """Eligible auth roles."""

    def __init__(self, *,
                 excluded_ids: Iterable[int] = None,
                 excluded_auth_ids: Iterable[str] = None,
                 excluded_auth_roles: Iterable[str] = None,
                 eligible_ids: Iterable[int] = None,
                 eligible_auth_ids: Iterable[str] = None,
                 eligible_auth_roles: Iterable[str] = None,
                 ) -> None:
        self.excluded_ids = unique_list_or_none(excluded_ids)
        self.excluded_auth_ids = unique_list_or_none(excluded_auth_ids)
        self.excluded_auth_roles = unique_list_or_none(excluded_auth_roles)

        self.eligible_ids = unique_list_or_none(eligible_ids)
        self.eligible_auth_ids = unique_list_or_none(eligible_auth_ids)
        self.eligible_auth_roles = unique_list_or_none(eligible_auth_roles)

    def __str__(self) -> str:
        return f"{type(self).__qualname__}"

    def __bool__(self) -> bool:
        return any((self.excluded_ids, self.excluded_auth_ids, self.excluded_auth_roles,
                    self.eligible_ids, self.eligible_auth_ids, self.eligible_auth_roles))

    def __contains__(self, receiver):
        return self.is_eligible(receiver) and not self.is_excluded(receiver)

    def is_excluded(self, receiver: BWItemType) -> bool:
        if isinstance(receiver, str):
            return contains_if_not_none(self.excluded_auth_roles, receiver, False) or \
                   contains_if_not_none(self.excluded_auth_ids, receiver, False)

        return contains_if_not_none(self.excluded_ids, receiver, False)

    def is_eligible(self, receiver: BWItemType) -> bool:
        if isinstance(receiver, str):
            return contains_if_not_none(self.eligible_auth_roles, receiver, True) or \
                   contains_if_not_none(self.eligible_auth_ids, receiver, True)

        return contains_if_not_none(self.eligible_ids, receiver, True)

    def exclude_session_id(self, session_id: int) -> None:
        self.excluded_ids = add_optional_unique_list(self.excluded_ids, session_id)

    def exclude_auth_id(self, auth_id: str) -> None:
        self.excluded_auth_ids = add_optional_unique_list(self.excluded_auth_ids, auth_id)

    def exclude_auth_role(self, auth_role: str) -> None:
        self.excluded_auth_roles = add_optional_unique_list(self.excluded_auth_roles, auth_role)

    def allow_session_id(self, session_id: int) -> None:
        self.eligible_ids = add_optional_unique_list(self.eligible_ids, session_id)

    def allow_auth_id(self, auth_id: str) -> None:
        self.eligible_auth_ids = add_optional_unique_list(self.eligible_auth_ids, auth_id)

    def allow_auth_role(self, auth_role: str) -> None:
        self.eligible_auth_roles = add_optional_unique_list(self.eligible_auth_roles, auth_role)

    def to_options(self, options: aiowamp.WAMPDict = None) -> aiowamp.WAMPDict:
        options = options or {}

        if self.excluded_ids is not None:
            options["exclude"] = self.excluded_ids
        if self.excluded_auth_ids is not None:
            options["exclude_authid"] = self.excluded_auth_ids
        if self.excluded_auth_roles is not None:
            options["exclude_authrole"] = self.excluded_auth_roles

        if self.eligible_ids is not None:
            options["eligible"] = self.eligible_ids
        if self.eligible_auth_ids is not None:
            options["eligible_authid"] = self.eligible_auth_ids
        if self.eligible_auth_roles is not None:
            options["eligible_authrole"] = self.eligible_auth_roles

        return options


T = TypeVar("T")


def contains_if_not_none(c: Optional[Container[T]], v: T, default: bool) -> bool:
    if c is None:
        return default

    return v in c


def unique_list_or_none(it: Optional[Iterable[T]]) -> Optional[List[T]]:
    if it is None:
        return None

    # KeysView is a subtype of set, so this should do.
    if isinstance(it, Set):
        return list(it)

    return list(set(it))


def add_optional_unique_list(l: Optional[List[T]], v: T) -> List[T]:
    if l is None:
        return [v]

    if v not in l:
        bisect.insort(l, v)

    return v
