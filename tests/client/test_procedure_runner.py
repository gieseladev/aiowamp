import asyncio
import logging

import pytest

import aiowamp
from aiowamp.client.invocation import AsyncGenRunner, AwaitableRunner, CoroRunner, get_runner_factory
from tests import mock
from tests.client.check import check_invocation

log = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


def make_interrupt(options: aiowamp.WAMPDict = None, *,
                   cancel_mode: aiowamp.CancelMode = aiowamp.CANCEL_KILL) -> aiowamp.Interrupt:
    options = options or {}
    options["mode"] = cancel_mode

    return aiowamp.Interrupt(options)


async def test_get_runner_factory():
    invocation = mock.make_dummy_invocation()

    async def coro(_):
        return None

    assert type(get_runner_factory(coro)(invocation)) == CoroRunner

    async def gen(_):
        yield None

    assert type(get_runner_factory(gen)(invocation)) == AsyncGenRunner

    def awaitable(_):
        return asyncio.Future()

    assert type(get_runner_factory(awaitable)(invocation)) == AwaitableRunner

    # this is only here to kill all pending coroutines by the above code.
    # It's not necessary but it removes the "coroutine was never awaited"
    # errors.
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()


async def test_async_gen_runner():
    async def gen():
        yield "progress0"
        yield aiowamp.InvocationProgress("instant progress")
        yield "progress1"

        yield "final"

    invocation = mock.make_dummy_invocation()
    await AsyncGenRunner(invocation, gen())

    check_invocation(invocation,
                     ("progress0", "instant progress", "progress1"),
                     "final")


async def test_async_gen_runner_interrupt():
    async def gen():
        yield "a"
        await asyncio.sleep(0)
        yield "final"

    invocation = mock.make_dummy_invocation()
    runner = AsyncGenRunner(invocation, gen())
    await asyncio.sleep(0)

    await runner.interrupt(make_interrupt())
    await runner

    check_invocation(invocation, (), error=True)


async def test_async_gen_runner_interrupt_handle():
    async def gen():
        yield "a"
        yield "b"
        await asyncio.sleep(0)

        try:
            yield "c"
        except aiowamp.Interrupt:
            yield "plz no error"

    invocation = mock.make_dummy_invocation()
    runner = AsyncGenRunner(invocation, gen())
    await asyncio.sleep(0)

    await runner.interrupt(make_interrupt())
    await runner

    check_invocation(invocation, ("a",), "plz no error")


async def test_coro_runner():
    async def procedure():
        return "hello world"

    invocation = mock.make_dummy_invocation()
    await CoroRunner(invocation, procedure())

    check_invocation(invocation, (), "hello world")


async def test_coro_runner_interrupt():
    async def procedure():
        await asyncio.sleep(50)
        return "hello world"

    invocation = mock.make_dummy_invocation()
    runner = CoroRunner(invocation, procedure())
    await asyncio.sleep(0)
    await runner.interrupt(make_interrupt())
    await runner

    check_invocation(invocation, (), error=True)


async def test_coro_runner_interrupt_handle():
    async def procedure():
        try:
            await asyncio.sleep(50)
        except aiowamp.Interrupt:
            pass

        return "hello world"

    invocation = mock.make_dummy_invocation()
    runner = CoroRunner(invocation, procedure())
    await asyncio.sleep(0)
    await runner.interrupt(make_interrupt())
    await runner

    check_invocation(invocation, (), "hello world")


async def test_awaitable_runner():
    def a():
        return asyncio.sleep(0, "hello world")

    invocation = mock.make_dummy_invocation()
    await AwaitableRunner(invocation, a())

    check_invocation(invocation, (), "hello world")


async def test_awaitable_runner_interrupt():
    def a():
        return asyncio.create_task(asyncio.sleep(3600, "hello world"))

    invocation = mock.make_dummy_invocation()
    runner = AwaitableRunner(invocation, a())
    await runner.interrupt(make_interrupt())
    await runner

    check_invocation(invocation, (), error=True)
