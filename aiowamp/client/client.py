from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from typing import AsyncIterator, Awaitable, Dict, Optional, TypeVar

import aiowamp
from .abstract import ClientABC
from .utils import call_async_fn, check_message_response

__all__ = ["Client"]

log = logging.getLogger(__name__)


class Client(ClientABC):
    __slots__ = ("session", "id_gen",
                 "__ongoing_calls", "__awaiting_reply",
                 "__sub_ids", "__sub_handlers")

    session: aiowamp.SessionABC
    id_gen: aiowamp.IDGeneratorABC

    __ongoing_calls: Dict[int, aiowamp.Call]
    __awaiting_reply: Dict[int, asyncio.Future]

    __sub_ids: Dict[aiowamp.URI, int]
    __sub_handlers: Dict[int, aiowamp.SubscriptionHandler]

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

        # received event
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

    async def register(self, procedure: str, handler: aiowamp.InvocationHandler, *, disclose_caller: bool = None,
                       match_policy: aiowamp.MatchPolicy = None, invocation_policy: aiowamp.InvocationPolicy = None,
                       options: aiowamp.WAMPDict = None) -> None:
        if inspect.isasyncgenfunction(handler):
            pass

        raise NotImplementedError("WIP")

    def call(self, procedure: str, *args: aiowamp.WAMPType,
             kwargs: aiowamp.WAMPDict = None,
             cancel_mode: aiowamp.CancelMode = None,
             call_timeout: float = None,
             disclose_me: bool = None,
             options: aiowamp.WAMPDict = None) -> aiowamp.CallABC:
        if call_timeout is not None:
            options = _set_value(options, "timeout", round(1000 * call_timeout))

        if disclose_me is not None:
            options = _set_value(options, "disclose_me", disclose_me)

        req_id = next(self.id_gen)
        call = aiowamp.Call(
            self.session,
            aiowamp.msg.Call(
                req_id,
                options or {},
                aiowamp.URI(procedure),
                list(args) or None,
                kwargs,
            ),
            cancel_mode=cancel_mode or aiowamp.CANCEL_KILL_NO_WAIT
        )

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

    async def subscribe(self, topic: str, callback: aiowamp.SubscriptionHandler, *,
                        match_policy: aiowamp.MatchPolicy = None,
                        options: aiowamp.WAMPDict = None) -> None:
        topic = aiowamp.URI(topic)

        if match_policy:
            options = _set_value(options, "match", match_policy)

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(aiowamp.msg.Subscribe(
                req_id,
                options or {},
                topic,
            ))

        msg = await resp
        check_message_response(msg, aiowamp.msg.Subscribed)
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

        check_message_response(await resp, aiowamp.msg.Unsubscribed)

    async def publish(self, topic: str, *args: aiowamp.WAMPType,
                      kwargs: aiowamp.WAMPDict = None,
                      acknowledge: bool = True,
                      exclude_me: bool = None,
                      disclose_me: bool = None,
                      options: aiowamp.WAMPDict = None) -> None:
        if acknowledge or (options and "acknowledge" in options):
            options = _set_value(options, "acknowledge", acknowledge)

        if exclude_me is not None:
            options = _set_value(options, "exclude_me", exclude_me)

        if disclose_me is not None:
            options = _set_value(options, "disclose_me", disclose_me)

        req_id = next(self.id_gen)
        send_coro = self.session.send(aiowamp.msg.Publish(
            req_id,
            options or {},
            aiowamp.URI(topic),
            list(args) or None,
            kwargs,
        ))

        # don't wait for a response when acknowledge=False
        # because the router won't send one.
        if not acknowledge:
            await send_coro
            return

        # wait for acknowledgment.

        async with self._expecting_response(req_id) as resp:
            await send_coro

        check_message_response(await resp, aiowamp.msg.Published)


T = TypeVar("T")


def _set_value(d: Optional[T], key: str, value: aiowamp.WAMPType) -> T:
    if d is None:
        d = {}

    d[key] = value
    return d
