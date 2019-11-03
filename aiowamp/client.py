from __future__ import annotations

import abc
import asyncio
import contextlib
import inspect
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional, Type, TypeVar, Union

import aiowamp

__all__ = ["ClientABC", "Client"]

log = logging.getLogger(__name__)

T = TypeVar("T")
MaybeAwaitable = Union[T, Awaitable[T]]
SubscriptionHandler = Callable[[aiowamp.msg.Event], MaybeAwaitable[Any]]


class CallABC(Awaitable[aiowamp.msg.Result], AsyncIterator[aiowamp.msg.Result], abc.ABC):
    __slots__ = ()

    def __str__(self) -> str:
        return f"Call {self.request_id}"

    def __await__(self):
        return self.result().__await__()

    def __aiter__(self):
        return self

    async def __anext__(self):
        progress = await self.next_progress()
        if progress is None:
            raise StopAsyncIteration

        return progress

    @property
    @abc.abstractmethod
    def request_id(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def done(self) -> bool:
        ...

    @property
    @abc.abstractmethod
    def cancelled(self) -> bool:
        ...

    @abc.abstractmethod
    async def result(self) -> aiowamp.msg.Result:
        ...

    @abc.abstractmethod
    async def next_progress(self) -> Optional[aiowamp.msg.Result]:
        ...

    @abc.abstractmethod
    async def cancel(self, options: aiowamp.WAMPDict = None) -> None:
        ...


# TODO on_progress event listener which suppresses the progress queue?
#       also maybe raise an error if this is done AFTER the call went out.

# TODO cancel mode setting

class ClientABC(abc.ABC):
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {id(self):x}"

    @abc.abstractmethod
    async def close(self, details: aiowamp.WAMPDict = None, *,
                    uri: str = None) -> None:
        ...

    @abc.abstractmethod
    def call(self, procedure: str, *args: aiowamp.WAMPType,
             kwargs: aiowamp.WAMPDict = None,
             call_timeout: float = None,
             disclose_me: bool = None,
             options: aiowamp.WAMPDict = None) -> CallABC:
        ...

    @abc.abstractmethod
    async def subscribe(self, topic: str, callback: SubscriptionHandler, *,
                        options: aiowamp.WAMPDict = None) -> None:
        ...

    @abc.abstractmethod
    async def unsubscribe(self, topic: str) -> None:
        ...

    @abc.abstractmethod
    async def publish(self, topic: str, *args: aiowamp.WAMPType,
                      kwargs: aiowamp.WAMPDict = None,
                      acknowledge: bool = True,
                      options: aiowamp.WAMPDict = None) -> None:
        ...


class Client(ClientABC):
    __slots__ = ("session", "id_gen",
                 "__ongoing_calls", "__awaiting_reply",
                 "__sub_ids", "__sub_handlers")

    session: aiowamp.SessionABC
    id_gen: aiowamp.IDGeneratorABC

    __ongoing_calls: Dict[int, Call]
    __awaiting_reply: Dict[int, asyncio.Future]

    __sub_ids: Dict[aiowamp.URI, int]
    __sub_handlers: Dict[int, SubscriptionHandler]

    def __init__(self, session: aiowamp.SessionABC) -> None:
        self.session = session
        self.id_gen = aiowamp.IDGenerator()

        self.__ongoing_calls = {}
        self.__awaiting_reply = {}

        self.__sub_ids = {}
        self.__sub_handlers = {}

        self.session.message_handler.on(callback=self.__handle_message)

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.session!r})"

    async def __handle_message(self, msg: aiowamp.MessageABC) -> None:
        try:
            request_id: int = getattr(msg, "request_id")
        except AttributeError:
            pass
        else:
            # received a message with a request_id

            try:
                call = self.__ongoing_calls[request_id]
            except KeyError:
                pass
            else:
                # response to an ongoing call

                if call.handle_response(msg):
                    if log.isEnabledFor(logging.DEBUG):
                        log.debug("%s: %s done", self, call)

                    del self.__ongoing_calls[request_id]

                return

            try:
                waiter = self.__awaiting_reply[request_id]
            except KeyError:
                pass
            else:
                # response to another message

                waiter.set_result(msg)
                return

            log.warning("%s: message with unexpected request id: %r", self, msg)

        event = aiowamp.message_as_type(msg, aiowamp.msg.Event)
        if event:
            try:
                callback = self.__sub_handlers[event.subscription_id]
            except KeyError:
                log.warning(f"%s: received event for unknown subscription: %r", self, event)
            else:
                await call_async_fn(callback, event)

            return

    @contextlib.asynccontextmanager
    async def _expecting_response(self, req_id: int) -> AsyncIterator[Awaitable[aiowamp.MessageABC]]:
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self.__awaiting_reply[req_id] = fut

        try:
            yield fut

            # wait for the response to come in before removing the future,
            # otherwise it won't receive the response.
            await fut
        finally:
            with contextlib.suppress(KeyError):
                del self.__awaiting_reply[req_id]

    def _cleanup(self) -> None:
        exc = aiowamp.ClientClosed()

        self.__sub_handlers.clear()
        self.__sub_ids.clear()

        for call in self.__ongoing_calls.values():
            call.kill(exc)
        self.__ongoing_calls.clear()

        for fut in self.__awaiting_reply.values():
            fut.set_exception(exc)
        self.__awaiting_reply.clear()

    async def close(self, details: aiowamp.WAMPDict = None, *,
                    uri: str = None) -> None:
        try:
            await self.session.close(details, uri=uri)
        finally:
            self._cleanup()

    def call(self, procedure: str, *args: aiowamp.WAMPType,
             kwargs: aiowamp.WAMPDict = None,
             call_timeout: float = None,
             disclose_me: bool = None,
             options: aiowamp.WAMPDict = None) -> CallABC:
        if call_timeout is not None:
            options = _set_value(options, "timeout", round(1000 * call_timeout))

        if disclose_me is not None:
            options = _set_value(options, "disclose_me", disclose_me)

        req_id = next(self.id_gen)
        call = Call(self.session, aiowamp.msg.Call(
            req_id,
            options or {},
            aiowamp.URI(procedure),
            list(args) or None,
            kwargs or None,
        ))
        self.__ongoing_calls[req_id] = call

        return call

    def get_subscription_id(self, topic: str) -> Optional[int]:
        """Get the id of the subscription for the given topic.

        Args:
            topic: Topic to get subscription id for.

        Returns:
            Subscription id. `None`, if not subscribed to the topic.
        """
        return self.__sub_ids.get(aiowamp.URI(topic))

    async def subscribe(self, topic: str, callback: SubscriptionHandler, *,
                        options: aiowamp.WAMPDict = None) -> None:
        topic = aiowamp.URI(topic)

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(aiowamp.msg.Subscribe(
                req_id,
                options or {},
                topic,
            ))

        msg = await resp
        # TODO _check_message_response should work as a type guard!
        _check_message_response(msg, aiowamp.msg.Subscribed)
        self.__sub_ids[topic] = msg.subscription_id
        self.__sub_handlers[msg.subscription_id] = callback

    async def unsubscribe(self, topic: str) -> None:
        # delete the local subscription first. This might lead to the situation
        # where we still receive events but don't have a handler but that's at
        # least better than the alternative.
        try:
            sub_id, _ = self.__sub_ids.pop(aiowamp.URI(topic))
        except KeyError:
            raise KeyError(f"not subscribed to {topic!r}") from None

        with contextlib.suppress(KeyError):
            del self.__sub_handlers[sub_id]

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(aiowamp.msg.Unsubscribe(req_id, sub_id))

        _check_message_response(await resp, aiowamp.msg.Unsubscribed)

    async def publish(self, topic: str, *args: aiowamp.WAMPType,
                      kwargs: aiowamp.WAMPDict = None,
                      acknowledge: bool = True,
                      options: aiowamp.WAMPDict = None) -> None:
        if options or acknowledge:
            options = _set_value(options, "acknowledge", acknowledge)

        req_id = next(self.id_gen)
        send_coro = self.session.send(aiowamp.msg.Publish(
            req_id,
            options or {},
            aiowamp.URI(topic),
            list(args) or None,
            kwargs or None,
        ))

        # don't wait for a response when acknowledge=False
        # because the router won't send one.
        if not acknowledge:
            await send_coro
            return

        # wait for acknowledgment.

        async with self._expecting_response(req_id) as resp:
            await send_coro

        _check_message_response(await resp, aiowamp.msg.Published)


class Call(CallABC):
    __slots__ = ("session",
                 "_call_msg", "_call_sent",
                 "__cancel_mode",
                 "__result_fut", "__progress_queue")

    session: aiowamp.SessionABC
    _call_msg: aiowamp.msg.Call
    _call_sent: bool

    __cancel_mode: str

    __result_fut: asyncio.Future
    __progress_queue: Optional[asyncio.Queue]

    def __init__(self, session: aiowamp.SessionABC, call: aiowamp.msg.Call) -> None:
        self.session = session
        self._call_msg = call
        self._call_sent = False

        self.__cancel_mode = "killnowait"

        loop = asyncio.get_event_loop()
        assert loop.is_running(), "loop isn't running"

        self.__result_fut = loop.create_future()
        self.__progress_queue = None

    def __repr__(self) -> str:
        return f"Call({self.session!r}, {self._call_msg!r})"

    @property
    def request_id(self) -> int:
        return self._call_msg.request_id

    @property
    def done(self) -> bool:
        return self.__result_fut.done()

    @property
    def cancelled(self) -> bool:
        return self.__result_fut.cancelled()

    def kill(self, e: Exception) -> None:
        if self.done:
            return

        self.__result_fut.set_exception(e)
        if self.__progress_queue is not None:
            self.__progress_queue.put_nowait(None)

    def handle_response(self, msg: aiowamp.MessageABC) -> bool:
        result = aiowamp.message_as_type(msg, aiowamp.msg.Result)
        if result and result.details.get("progress"):
            if self.__progress_queue is not None:
                self.__progress_queue.put_nowait(result)

            return False

        if result or aiowamp.is_message_type(msg, aiowamp.msg.Error):
            self.__result_fut.set_result(msg)
        else:
            self.__result_fut.set_exception(aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Result))

        if self.__progress_queue is not None:
            # add none to wake up
            self.__progress_queue.put_nowait(None)

        return True

    async def __send_call(self) -> None:
        if self.done:
            raise self.__result_fut.exception()

        self._call_sent = True
        self.__progress_queue = asyncio.Queue()

        try:
            await self.session.send(self._call_msg)
        except Exception as e:
            self.__result_fut.set_exception(e)

    async def __next_final(self) -> Union[aiowamp.msg.Result, aiowamp.msg.Error]:
        if not self._call_sent:
            await self.__send_call()

        return await self.__result_fut

    async def __next_progress(self) -> Optional[aiowamp.msg.Result]:
        if not self._call_sent:
            await self.__send_call()

        if self.__progress_queue.empty() and self.done:
            return None

        # this depends on the fact that None is pushed to the queue.
        # it would be nicer to use asyncio.wait, but this way is
        # "cheaper"
        return await self.__progress_queue.get()

    async def result(self) -> aiowamp.msg.Result:
        try:
            msg = await self.__next_final()
        except asyncio.CancelledError:
            if not self.cancelled:
                await self.cancel()

            raise

        # TODO raise proper exception
        _check_message_response(msg, aiowamp.msg.Result)

        return msg

    async def next_progress(self) -> Optional[aiowamp.msg.Result]:
        return await self.__next_progress()

    async def cancel(self, options: aiowamp.WAMPDict = None) -> None:
        self.__result_fut.cancel()

        if not self._call_sent:
            log.debug("%s: cancelled before call was sent", self)
            return

        options = options or {}
        if self.__cancel_mode:
            options.setdefault("mode", self.__cancel_mode)

        await self.session.send(aiowamp.msg.Cancel(self._call_msg.request_id, options))
        try:
            await self.__next_final()
        except Exception:
            pass


def _check_message_response(msg: aiowamp.MessageABC, ok_type: Type[aiowamp.MessageABC]) -> None:
    ok = aiowamp.message_as_type(msg, ok_type)
    if ok:
        return

    error = aiowamp.message_as_type(msg, aiowamp.msg.Error)
    if error:
        raise aiowamp.ErrorResponse(error)

    raise aiowamp.UnexpectedMessageError(msg, ok_type)


def _set_value(d: Optional[T], key: str, value: aiowamp.WAMPType) -> T:
    if d is None:
        d = {}

    d[key] = value
    return d


async def call_async_fn(f: Callable[..., MaybeAwaitable[T]], *args, **kwargs) -> T:
    res = f(*args, **kwargs)
    if inspect.isawaitable(res):
        res = await res

    return res


CLIENT_ROLES: aiowamp.WAMPDict = {
    "publisher": {
        "features": {
            "subscriber_blackwhite_listing": True,
            "publisher_exclusion": True,
        },
    },
    "subscriber": {
        "features": {
            "pattern_based_subscription": True,
            "publisher_identification": True,
        },
    },
    "callee": {
        "features": {
            "pattern_based_registration": True,
            "shared_registration": True,
            "call_canceling": True,
            "call_timeout": True,
            "caller_identification": True,
            "progressive_call_results": True,
        },
    },
    "caller": {
        "features": {
            "call_canceling": True,
            "call_timeout": True,
            "caller_identification": True,
            "progressive_call_results": True,
        },
    },
}
