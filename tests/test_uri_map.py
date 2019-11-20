import pytest

import aiowamp
from aiowamp.uri_map import URIMap


def prefix(s: str) -> aiowamp.URI:
    return aiowamp.URI(s, match_policy=aiowamp.MATCH_PREFIX)


def wildcard(s: str) -> aiowamp.URI:
    return aiowamp.URI(s, match_policy=aiowamp.MATCH_WILDCARD)


def test_order():
    u = URIMap()
    u[aiowamp.URI("a1.b2.c3.d4.e55")] = 1

    u[prefix("a1.b2.c3")] = 2
    u[prefix("a1.b2.c3.d4")] = 3

    u[wildcard("a1.b2..d4.e5")] = 4
    u[wildcard("a1.b2.c33..e5")] = 5
    u[wildcard("a1.b2..d4.e5..g7")] = 6
    u[wildcard("a1.b2..d4..f6.g7")] = 7

    assert u["a1.b2.c3.d4.e55"] == 1

    assert u["a1.b2.c3.d98.e74"] == 2
    assert u["a1.b2.c3.d4.e325"] == 3

    assert u["a1.b2.c55.d4.e5"] == 4
    assert u["a1.b2.c33.d4.e5"] == 5
    assert u["a1.b2.c88.d4.e5.f6.g7"] == 6

    with pytest.raises(LookupError):
        _ = u["a2.b2.c2.d2.e2"]
