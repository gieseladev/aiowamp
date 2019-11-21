from __future__ import annotations

import bisect
from typing import Any, Container, Iterable, List, Optional, Set, Type, TypeVar, Union

import aiowamp

__all__ = ["BlackWhiteList"]

T = TypeVar("T")

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

    bwlist will keep the constraint lists in ascending order.

    Notes:
        bwlist assumes that the set of auth ids is distinct from the set of
        auth roles. If they are not, the checks may return invalid results.
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
        """Create a new bwlist.

        The given iterables are converted into lists, sorted, and
        duplicates are removed.

        Args:
            excluded_ids: Session IDs to exclude.
            excluded_auth_ids: Auth IDs to exclude.
            excluded_auth_roles: Auth roles to exclude.

            eligible_ids: Eligible session IDs.
            eligible_auth_ids: Eligible auth IDs.
            eligible_auth_roles: Eligible auth roles.
        """
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

    def __contains__(self, receiver: Any) -> bool:
        """Check if the receiver would receive the event.

        Args:
            receiver: Session id, auth id, or auth role to check.

        Returns:
            `True` if the receiver is eligible and not excluded, `False`
            otherwise.
        """
        return self.is_eligible(receiver) and not self.is_excluded(receiver)

    def is_excluded(self, receiver: BWItemType) -> bool:
        """Check if the receiver is excluded.

        Args:
            receiver: Session id, auth id, or auth role to check.

        Returns:
            `True` if there is an exclusion list and the receiver is in it,
            `False` otherwise.
        """
        if isinstance(receiver, str):
            return contains_if_not_none(self.excluded_auth_roles, receiver, False) or \
                   contains_if_not_none(self.excluded_auth_ids, receiver, False)

        return contains_if_not_none(self.excluded_ids, receiver, False)

    def is_eligible(self, receiver: BWItemType) -> bool:
        """Check if the receiver is eligible.

        Args:
            receiver: Session id, auth id, or auth role to check.

        Returns:
            `True` if there is no eligible list or the receiver is in it,
            `False` otherwise.
        """
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

    def unexclude(self, receiver: BWItemType) -> None:
        if isinstance(receiver, str):
            if remove_from_any(receiver,
                               self.excluded_auth_roles,
                               self.excluded_auth_ids):
                return

            raise ValueError(f"receiver {receiver!r} is neither an excluded "
                             f"auth id, nor an auth role") from None

        try:
            self.excluded_ids.remove(receiver)
        except (TypeError, ValueError):
            raise ValueError(f"session id {receiver!r} isn't excluded") from None

    def allow_session_id(self, session_id: int) -> None:
        self.eligible_ids = add_optional_unique_list(self.eligible_ids, session_id)

    def allow_auth_id(self, auth_id: str) -> None:
        self.eligible_auth_ids = add_optional_unique_list(self.eligible_auth_ids, auth_id)

    def allow_auth_role(self, auth_role: str) -> None:
        self.eligible_auth_roles = add_optional_unique_list(self.eligible_auth_roles, auth_role)

    def disallow(self, receiver: BWItemType) -> None:
        if isinstance(receiver, str):
            if remove_from_any(receiver,
                               self.eligible_auth_roles,
                               self.eligible_auth_ids):
                return

            raise ValueError(f"receiver {receiver!r} is neither an eligible "
                             f"auth id, nor an auth role") from None

        try:
            self.eligible_ids.remove(receiver)
        except (TypeError, ValueError):
            raise ValueError(f"session id {receiver!r} isn't eligible") from None

    def to_options(self, options: aiowamp.WAMPDict = None) -> aiowamp.WAMPDict:
        """Convert the bwlist to WAMP options.

        Args:
            options: Dict to write the options to.
                If not specified, a `dict` will be created,

        Returns:
            WAMP dict containing the constraints from the bwlist.
            If an argument for options was passed, the return value will be the
            same instance.
        """
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

    @classmethod
    def from_options(cls: Type[T], options: aiowamp.WAMPDict) -> T:
        """Create a bwlist from WAMP options.

        Args:
            options: WAMP options as returned by `.to_options`.

        Returns:
            New bwlist with the constraints from the options.
        """
        return cls(
            excluded_ids=options.get("exclude"),
            excluded_auth_ids=options.get("exclude_authid"),
            excluded_auth_roles=options.get("exclude_authrole"),

            eligible_ids=options.get("eligible"),
            eligible_auth_ids=options.get("eligible_authid"),
            eligible_auth_roles=options.get("eligible_authrole"),
        )


def contains_if_not_none(c: Optional[Container[T]], v: T, default: bool) -> bool:
    """Check if the optional container contains a value.

    Args:
        c: Optional container.
        v: Value to check.
        default: Default value to return if the container is `None`

    Returns:
        Whether the value is in the container, or the default value if the
        container is `None`.
    """
    if c is None:
        return default

    return v in c


def unique_list_or_none(it: Optional[Iterable[T]]) -> Optional[List[T]]:
    """Convert the optional iterable into an optional unique list.

    Args:
        it: Optional iterable to convert.

    Returns:
        `None` if the iterable is `None`, a list containing the unique elements
        from the iterable in ascending order otherwise.
    """
    if it is None:
        return None

    # KeysView is a subtype of set, so this should do.
    if isinstance(it, Set):
        return list(it)

    return list(set(it))


def add_optional_unique_list(l: Optional[List[T]], v: T) -> List[T]:
    """Add a value to an optional list.

    If the list is sorted, the value is inserted at the appropriate position.
    If it isn't, then the position is undefined.

    Args:
        l: List to add the value to. If `None`, a new list will be created.
        v: Value to add.

    Returns:
        List containing the value. If l is not `None`, this will be the same
        list.
    """
    if l is None:
        return [v]

    if v not in l:
        bisect.insort(l, v)

    return v


def remove_from_any(v: T, *sequences: Optional[List[T]]) -> bool:
    """Remove the value from the first list.

    Args:
        v: Value to remove.
        *sequences: Optional lists to try to remove the value from.

    Returns:
        Whether the value was removed from any list.
    """
    for seq in sequences:
        try:
            seq.remove(v)
        except (TypeError, KeyError):
            pass
        else:
            return True

    return False
