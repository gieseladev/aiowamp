from typing import Any

import pytest

import aiowamp.templ
from aiowamp.templ.handler import Handler, get_handlers_in_instance, get_registration_handler, get_subscription_handler
from tests.mock import make_dummy_invocation, make_dummy_subscription_event

pytestmark = pytest.mark.asyncio


async def invoke_procedure(fn: Any, args: aiowamp.WAMPList, kwargs: aiowamp.WAMPDict) -> aiowamp.Invocation:
    if isinstance(fn, Handler):
        handler = fn
    else:
        handler = get_registration_handler(fn)
        assert handler, "no handler attached"

    invocation = make_dummy_invocation(args=args, kwargs=kwargs)
    entry = handler.get_entry_point()
    await entry(invocation)
    return invocation


async def invoke_event(fn: Any, args: aiowamp.WAMPList, kwargs: aiowamp.WAMPDict) -> aiowamp.SubscriptionEvent:
    if isinstance(fn, Handler):
        handler = fn
    else:
        handler = get_subscription_handler(fn)
        assert handler, "no handler attached"

    event = make_dummy_subscription_event(args=args, kwargs=kwargs)
    entry = handler.get_entry_point()
    await entry(event)
    return event


async def test_procedure_entry_point_fn():
    got = []

    @aiowamp.templ.procedure()
    async def f1(a, b, *, integer=False):
        nonlocal got
        got = [a, b, integer]

    await invoke_procedure(f1, [1, 5], {"integer": True})
    assert got == [1, 5, True]

    with pytest.raises(aiowamp.InvocationError):
        await invoke_procedure(f1, [], {"integer": True})

    @aiowamp.templ.procedure()
    async def f2(h, *msgs, opt_out, **opts):
        nonlocal got
        got = [h, msgs, opt_out, opts]

    # tolerated because h has the same value twice
    await invoke_procedure(f2, [0, 1, 2, 3, 4], {"h": 0, "opt_out": False, "anything": "no"})
    assert got == [0, (1, 2, 3, 4), False, {"anything": "no"}]

    with pytest.raises(aiowamp.InvocationError):
        # raises because h has 2 different values
        await invoke_procedure(f2, [0, 1, 2, 3, 4], {"h": 1, "opt_out": False, "anything": "no"})

    @aiowamp.templ.procedure()
    async def f3(inv: aiowamp.InvocationABC, a):
        nonlocal got
        got = [inv, a]

    invocation = await invoke_procedure(f3, ["test"], {})
    assert got == [invocation, "test"]


async def test_event_entry_point_fn():
    got = []

    @aiowamp.templ.event("test")
    async def f1(a, b, *, integer=False):
        nonlocal got
        got = [a, b, integer]

    await invoke_event(f1, [1, 5], {"integer": True})
    assert got == [1, 5, True]

    @aiowamp.templ.event("test2")
    async def f2(h, *msgs, opt_out, **opts):
        nonlocal got
        got = [h, msgs, opt_out, opts]

    await invoke_event(f2, [0, 1, 2, 3, 4], {"h": 0, "opt_out": False, "anything": "no"})
    assert got == [0, (1, 2, 3, 4), False, {"anything": "no"}]


async def test_method_entry_point():
    got = []

    class Test:
        @aiowamp.templ.procedure()
        async def f1(self, *, a, b) -> None:
            nonlocal got
            got = [self, a, b]

        @classmethod
        @aiowamp.templ.procedure()
        async def f2(cls, a) -> None:
            nonlocal got
            got = [cls, a]

        @aiowamp.templ.event("e1")
        async def e1(self, a, b) -> None:
            nonlocal got
            got = [self, a, b]

        @staticmethod
        @aiowamp.templ.event("e2")
        async def e2(ev: aiowamp.SubscriptionEvent) -> None:
            nonlocal got
            got = [ev]

    t = Test()
    regs, subs = get_handlers_in_instance(t)
    f1, f2 = regs
    e1, e2 = subs

    await invoke_procedure(f1, [], {"a": 3, "b": 6})
    assert got == [t, 3, 6]

    await invoke_procedure(f2, [77], {})
    assert got == [Test, 77]

    await invoke_event(e1, ["hello", "world"], {})
    assert got == [t, "hello", "world"]

    event = await invoke_event(e2, [], {})
    assert got == [event]
