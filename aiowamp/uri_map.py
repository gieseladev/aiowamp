from __future__ import annotations

import itertools
from typing import Dict, Generic, ItemsView, Iterable, Iterator, List, MutableMapping, MutableSequence, Tuple, TypeVar, \
    ValuesView

import aiowamp
from .uri import MATCH_PREFIX, MATCH_WILDCARD, URI

__all__ = ["URIMap",
           "URIMapValuesView", "URIMapItemsView"]

Rank = Tuple[int, ...]


def rank_prefix(u: aiowamp.URI) -> Rank:
    comps = u.count(".") + 1
    last_comp_len = len(u.rsplit(".", 1)[0])
    # match most components first,
    # break ties using length of final comp
    return comps, last_comp_len


def rank_wildcard(u: aiowamp.URI) -> Rank:
    comp_bitmap = map(lambda c: 2 * bool(c) - 1, u.split("."))
    return tuple(sum(g) for _, g in itertools.groupby(comp_bitmap))


KV_co = TypeVar("KV_co", covariant=True)

ValueTuple = Tuple[Rank, "aiowamp.URI", KV_co]


def iter_values_keys(e: Iterable[ValueTuple]) -> Iterator["aiowamp.URI"]:
    for _, uri, _ in e:
        yield uri


def iter_values_values(e: Iterable[ValueTuple]) -> Iterator[KV_co]:
    for _, _, v in e:
        yield v


Item = Tuple["aiowamp.URI", KV_co]


def iter_values_items(e: Iterable[ValueTuple]) -> Iterator[Item]:
    for _, k, v in e:
        yield k, v


def sort_values(e: List[ValueTuple]) -> None:
    e.sort(key=lambda v: v[0], reverse=True)


def insort_values_value(e: List[ValueTuple], v: ValueTuple) -> None:
    e.append(v)
    sort_values(e)


def remove_values_key(e: MutableSequence[ValueTuple], uri: aiowamp.URI) -> None:
    for i, (_, u, _) in enumerate(e):
        if u == uri:
            break
    else:
        raise KeyError(uri)

    del e[i]


class URIMap(MutableMapping["aiowamp.URI", KV_co], Generic[KV_co]):
    __slots__ = ("_exact", "_prefix", "_wildcard")

    _exact: Dict[str, KV_co]
    _prefix: List[ValueTuple]
    _wildcard: List[ValueTuple]

    def __init__(self) -> None:
        self._exact = {}
        self._prefix = []
        self._wildcard = []

    def __getitem__(self, uri: str) -> KV_co:
        uri = URI.as_uri(uri)

        try:
            return self._exact[uri]
        except KeyError:
            pass

        for _, prefix, val in self._prefix:
            if URI.prefix_match(uri, prefix):
                return val

        for _, wildcard, val in self._wildcard:
            if URI.wildcard_match(uri, wildcard):
                return val

        raise KeyError(uri)

    def __setitem__(self, uri: aiowamp.URI, value: KV_co) -> None:
        if not isinstance(uri, URI):
            raise TypeError(f"instance of aiowamp.URI required, not {type(uri).__name__}")

        match_policy = uri.match_policy

        if match_policy is None:
            self._exact[uri] = value
        elif match_policy == MATCH_PREFIX:
            rank = rank_prefix(uri)
            insort_values_value(self._prefix, (rank, uri, value))
        elif match_policy == MATCH_WILDCARD:
            rank = rank_wildcard(uri)
            insort_values_value(self._wildcard, (rank, uri, value))
        else:
            raise ValueError(f"unknown match policy: {match_policy!r}")

    def __delitem__(self, uri: aiowamp.URI) -> None:
        if not isinstance(uri, URI):
            raise TypeError(f"instance of aiowamp.URI required, not {type(uri).__name__}")

        match_policy = uri.match_policy

        if match_policy is None:
            del self._exact[uri]
        elif match_policy == MATCH_PREFIX:
            remove_values_key(self._prefix, uri)
        elif match_policy == MATCH_WILDCARD:
            remove_values_key(self._wildcard, uri)
        else:
            raise ValueError(f"unknown match policy: {match_policy!r}")

    def __len__(self) -> int:
        return len(self._exact) + len(self._prefix) + len(self._wildcard)

    def __iter__(self):
        yield from self._exact
        yield from iter_values_keys(self._prefix)
        yield from iter_values_keys(self._wildcard)

    def values(self) -> URIMapValuesView[KV_co]:
        return URIMapValuesView(self)

    def items(self) -> URIMapItemsView[KV_co]:
        return URIMapItemsView(self)


class URIMapValuesView(ValuesView[KV_co], Generic[KV_co]):
    __slots__ = ()

    _mapping: URIMap[KV_co]

    def __init__(self, mapping: URIMap[KV_co]) -> None:
        self._mapping = mapping

    def __contains__(self, item: KV_co) -> bool:
        mapping = self._mapping

        return item in mapping._exact.values() or \
               item in iter_values_values(mapping._prefix) or \
               item in iter_values_values(mapping._wildcard)

    def __iter__(self) -> Iterator[KV_co]:
        mapping = self._mapping

        yield from mapping._exact.values()
        yield from iter_values_values(mapping._prefix)
        yield from iter_values_values(mapping._wildcard)


class URIMapItemsView(ItemsView["aiowamp.URI", KV_co], Generic[KV_co]):
    __slots__ = ()

    _mapping: URIMap[KV_co]

    def __init__(self, mapping: URIMap[KV_co]) -> None:
        self._mapping = mapping

    def __contains__(self, item: Item) -> bool:
        key, value = item
        try:
            actual = self._mapping[key]
        except LookupError:
            return False

        return actual is value or actual == value

    def __iter__(self) -> Iterator[Iterator]:
        mapping = self._mapping

        yield from mapping._exact.items()
        yield from iter_values_items(mapping._prefix)
        yield from iter_values_items(mapping._wildcard)
