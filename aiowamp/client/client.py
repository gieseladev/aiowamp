from __future__ import annotations

import array
import asyncio
import contextlib
import logging
from typing import AsyncIterator, Awaitable, Dict, MutableMapping, Optional, Tuple, TypeVar

import aiowamp
from .abstract import ClientABC
from .invocation import ProcedureRunnerABC, RunnerFactory, get_runner_factory
from .utils import call_async_fn, check_message_response

__all__ = ["Client"]

log = logging.getLogger(__name__)


# TODO add client shutdown which removes all subs/procedures and waits for all
#   pending tasks to finish before closing.

class Client(ClientABC):
    __slots__ = ("session", "id_gen",
                 "__awaiting_reply", "__ongoing_calls", "__running_procedures",
                 "__procedure_ids", "__procedures",
                 "__sub_ids", "__sub_handlers")

    session: aiowamp.SessionABC
    """Session the client is attached to."""
    id_gen: aiowamp.IDGeneratorABC
    """ID generator used to generate the client ids."""

    __awaiting_reply: Dict[int, asyncio.Future]
    __ongoing_calls: Dict[int, aiowamp.Call]
    __running_procedures: Dict[int, ProcedureRunnerABC]

    __procedure_ids: Dict[str, array.ArrayType]
    __procedures: Dict[int, Tuple[RunnerFactory, aiowamp.URI]]

    __sub_ids: Dict[str, array.ArrayType]
    __sub_handlers: Dict[int, Tuple[aiowamp.SubscriptionHandler, aiowamp.URI]]

    def __init__(self, session: aiowamp.SessionABC) -> None:
        self.session = session
        self.id_gen = aiowamp.IDGenerator()

        self.__awaiting_reply = {}
        self.__ongoing_calls = {}
        self.__running_procedures = {}

        self.__procedure_ids = {}
        self.__procedures = {}

        self.__sub_ids = {}
        self.__sub_handlers = {}

        self.session.message_handler.on(callback=self.__handle_message)

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.session!r})"

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {self.session.session_id}"

    async def __handle_invocation(self, invocation_msg: aiowamp.msg.Invocation) -> None:
        try:
            runner_factory, uri = self.__procedures[invocation_msg.registration_id]
        except KeyError:
            log.warning("%s: received invocation for unknown registration: %r", self, invocation_msg)

            await self.session.send(aiowamp.msg.Error(
                aiowamp.msg.Invocation.message_type,
                invocation_msg.request_id,
                {},
                aiowamp.uri.INVALID_ARGUMENT,
                [f"client has no procedure for registration {invocation_msg.registration_id}"]
            ))
            return

        invocation = aiowamp.Invocation(self.session, self, invocation_msg, procedure=uri)

        try:
            runner = runner_factory(invocation)
        except Exception as e:
            log.exception("%s: couldn't start procedure %s", self, runner_factory)
            err = aiowamp.exception_to_invocation_error(e)
            await invocation.send_error(err.uri, *err.args, kwargs=err.kwargs)
            return

        self.__running_procedures[invocation.request_id] = runner
        try:
            await runner
        finally:
            log.debug("%s: invocation %s is done", self, invocation)
            del self.__running_procedures[invocation.request_id]

    async def __handle_interrupt(self, interrupt_msg: aiowamp.msg.Interrupt) -> None:
        try:
            runner = self.__running_procedures[interrupt_msg.request_id]
        except KeyError:
            log.info("%s: received interrupt for invocation that doesn't exist", self)
            return

        await runner.interrupt(aiowamp.Interrupt(interrupt_msg.options))

    async def __handle_event(self, event_msg: aiowamp.msg.Event, handler: aiowamp.SubscriptionHandler,
                             topic: aiowamp.URI) -> None:
        event = aiowamp.SubscriptionEvent(self, event_msg, topic=topic)
        await call_async_fn(handler, event)

    async def __handle_message(self, msg: aiowamp.MessageABC) -> None:
        invocation = aiowamp.message_as_type(msg, aiowamp.msg.Invocation)
        if invocation:
            await self.__handle_invocation(invocation)
            return

        interrupt = aiowamp.message_as_type(msg, aiowamp.msg.Interrupt)
        if interrupt:
            await self.__handle_interrupt(interrupt)
            return

        try:
            request_id: int = getattr(msg, "request_id")
        except AttributeError:
            pass
        else:
            # received a message with a request_id

            try:
                waiter = self.__awaiting_reply[request_id]
            except KeyError:
                pass
            else:
                # response to another message

                waiter.set_result(msg)
                return

            try:
                call = self.__ongoing_calls[request_id]
            except KeyError:
                pass
            else:
                # response to an ongoing call

                if call.handle_response(msg):
                    log.debug("%s: %s done", self, call)

                    del self.__ongoing_calls[request_id]

                return

            log.warning("%s: message with unexpected request id: %r", self, msg)

        # received event
        event = aiowamp.message_as_type(msg, aiowamp.msg.Event)
        if event:
            try:
                handler, uri = self.__sub_handlers[event.subscription_id]
            except KeyError:
                log.warning(f"%s: received event for unknown subscription: %r", self, event)
            else:
                await self.__handle_event(event, handler, uri)

            return

    @contextlib.asynccontextmanager
    async def _expecting_response(self, req_id: int) -> AsyncIterator[Awaitable[aiowamp.MessageABC]]:
        loop = asyncio.get_running_loop()
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

    async def _cleanup(self) -> None:
        exc = aiowamp.ClientClosed()
        self.session.message_handler.off(callback=self.__handle_message)

        self.__procedure_ids.clear()
        self.__procedures.clear()

        for procedure in self.__running_procedures.values():
            procedure.cancel()

        self.__running_procedures.clear()

        self.__sub_handlers.clear()
        self.__sub_ids.clear()

        for call in self.__ongoing_calls.values():
            call.kill(exc)
        self.__ongoing_calls.clear()

        for fut in self.__awaiting_reply.values():
            fut.set_exception(exc)
        self.__awaiting_reply.clear()

    async def close(self, details: aiowamp.WAMPDict = None, *,
                    reason: str = None) -> None:
        try:
            await self.session.close(details, reason=reason)
        finally:
            await self._cleanup()

    def get_registration_ids(self, procedure: str) -> Tuple[int, ...]:
        """Get the ids of the registrations for the given procedure.

        Args:
            procedure: Procedure to get registration ids for.

        Returns:
            Tuple containing the registration ids.
        """
        try:
            return tuple(self.__procedure_ids[procedure])
        except KeyError:
            return ()

    async def register(self, procedure: str, handler: aiowamp.InvocationHandler, *,
                       disclose_caller: bool = None,
                       match_policy: aiowamp.MatchPolicy = None,
                       invocation_policy: aiowamp.InvocationPolicy = None,
                       options: aiowamp.WAMPDict = None) -> int:
        # get runner factory up here already to catch errors early
        runner = get_runner_factory(handler)

        if match_policy is not None:
            procedure_uri = aiowamp.URI(procedure, match_policy=match_policy)
        else:
            procedure_uri = aiowamp.URI.as_uri(procedure)

        if disclose_caller is not None:
            options = _set_value(options, "disclose_caller", disclose_caller)

        if procedure_uri.match_policy is not None:
            options = _set_value(options, "match", procedure_uri.match_policy)

        if invocation_policy is not None:
            options = _set_value(options, "invoke", invocation_policy)

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(aiowamp.msg.Register(
                req_id,
                options or {},
                procedure_uri,
            ))

        registered = check_message_response(await resp, aiowamp.msg.Registered)

        reg_id = registered.registration_id
        _add_to_array(self.__procedure_ids, procedure_uri, reg_id)

        self.__procedures[reg_id] = runner, procedure_uri

        return reg_id

    async def __unregister(self, reg_id: int) -> None:
        with contextlib.suppress(KeyError):
            del self.__procedures[reg_id]

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(aiowamp.msg.Unregister(req_id, reg_id))

        check_message_response(await resp, aiowamp.msg.Unregistered)

    async def unregister(self, procedure: str, registration_id: int = None) -> None:
        if registration_id is None:
            try:
                reg_ids = self.__procedure_ids.pop(procedure)
            except KeyError:
                raise KeyError(f"no procedure registered for {procedure!r}") from None

            await asyncio.gather(*(self.__unregister(reg_id) for reg_id in reg_ids))
            return

        if registration_id not in self.__procedures:
            raise KeyError(f"unknown registration id {registration_id!r}")

        with contextlib.suppress(KeyError, ValueError):
            self.__procedure_ids[procedure].remove(registration_id)

        await self.__unregister(registration_id)

    def call(self, procedure: str, *args: aiowamp.WAMPType,
             kwargs: aiowamp.WAMPDict = None,
             receive_progress: bool = None,
             call_timeout: float = None,
             cancel_mode: aiowamp.CancelMode = None,
             disclose_me: bool = None,
             resource_key: str = None,
             options: aiowamp.WAMPDict = None) -> aiowamp.CallABC:
        if receive_progress is not None:
            options = _set_value(options, "receive_progress", receive_progress)

        if call_timeout is not None:
            options = _set_value(options, "timeout", round(1e3 * call_timeout))

        if disclose_me is not None:
            options = _set_value(options, "disclose_me", disclose_me)

        if resource_key is not None:
            options = _set_value(options, "rkey", resource_key)
            options["runmode"] = "partition"

        req_id = next(self.id_gen)
        call = aiowamp.Call(
            self.session,
            aiowamp.msg.Call(
                req_id,
                options or {},
                procedure,
                list(args) or None,
                kwargs,
            ),
            cancel_mode=cancel_mode or aiowamp.CANCEL_KILL_NO_WAIT
        )

        self.__ongoing_calls[req_id] = call

        return call

    def get_subscription_ids(self, topic: str) -> Tuple[int, ...]:
        """Get the ids of the subscriptions for the given topic.

        Args:
            topic: Topic to get subscription ids for.

        Returns:
            Tuple of subscription ids.
        """
        try:
            return tuple(self.__sub_ids[topic])
        except KeyError:
            return ()

    async def subscribe(self, topic: str, callback: aiowamp.SubscriptionHandler, *,
                        match_policy: aiowamp.MatchPolicy = None,
                        node_key: str = None,
                        options: aiowamp.WAMPDict = None) -> int:
        if match_policy is not None:
            topic_uri = aiowamp.URI(topic, match_policy=match_policy)
        else:
            topic_uri = aiowamp.URI.as_uri(topic)

        if topic_uri.match_policy:
            options = _set_value(options, "match", topic_uri.match_policy)

        if node_key is not None:
            options = _set_value(options, "nkey", node_key)

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(aiowamp.msg.Subscribe(
                req_id,
                options or {},
                topic_uri,
            ))

        subscribed = check_message_response(await resp, aiowamp.msg.Subscribed)

        sub_id = subscribed.subscription_id
        _add_to_array(self.__sub_ids, topic_uri, sub_id)
        self.__sub_handlers[sub_id] = callback, topic_uri

        return sub_id

    async def __unsubscribe(self, sub_id: int) -> None:
        with contextlib.suppress(KeyError):
            del self.__sub_handlers[sub_id]

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(aiowamp.msg.Unsubscribe(req_id, sub_id))

        check_message_response(await resp, aiowamp.msg.Unsubscribed)

    async def unsubscribe(self, topic: str, subscription_id: int = None) -> None:
        if subscription_id is None:
            try:
                sub_ids = self.__procedure_ids.pop(topic)
            except KeyError:
                raise KeyError(f"no subscription for {topic!r}") from None

            await asyncio.gather(*(self.__unsubscribe(sub_id) for sub_id in sub_ids))
            return

        if subscription_id not in self.__procedures:
            raise KeyError(f"unknown subscription id {subscription_id!r}")

        with contextlib.suppress(KeyError, ValueError):
            self.__sub_ids[topic].remove(subscription_id)

        await self.__unsubscribe(subscription_id)

    async def publish(self, topic: str, *args: aiowamp.WAMPType,
                      kwargs: aiowamp.WAMPDict = None,
                      acknowledge: bool = None,
                      blackwhitelist: aiowamp.BlackWhiteList = None,
                      exclude_me: bool = None,
                      disclose_me: bool = None,
                      resource_key: str = None,
                      options: aiowamp.WAMPDict = None) -> None:
        if acknowledge is not None:
            options = _set_value(options, "acknowledge", acknowledge)

        if blackwhitelist:
            options = blackwhitelist.to_options(options)

        if exclude_me is not None:
            options = _set_value(options, "exclude_me", exclude_me)

        if disclose_me is not None:
            options = _set_value(options, "disclose_me", disclose_me)

        if resource_key is not None:
            options = _set_value(options, "rkey", resource_key)

        req_id = next(self.id_gen)
        send_coro = self.session.send(aiowamp.msg.Publish(
            req_id,
            options or {},
            topic,
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


def _add_to_array(d: MutableMapping[str, array.ArrayType], key: str, value: int) -> None:
    try:
        a = d[key]
    except KeyError:
        d[key] = array.array("Q", (value,))
    else:
        a.append(value)
