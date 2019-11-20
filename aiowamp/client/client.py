from __future__ import annotations

import abc
import array
import asyncio
import contextlib
import logging
from typing import Any, AsyncGenerator, AsyncIterator, Awaitable, Callable, Dict, MutableMapping, Optional, Tuple, \
    TypeVar, Union

import aiowamp
from aiowamp import ClientClosed, IDGenerator, Interrupt, URI, exception_to_invocation_error, message_as_type
from aiowamp.maybe_awaitable import MaybeAwaitable, call_async_fn
from aiowamp.msg import Call as CallMsg, Error as ErrorMsg, Event as EventMsg, Interrupt as InterruptMsg, \
    Invocation as InvocationMsg, Publish as PublishMsg, Published as PublishedMsg, Register as RegisterMsg, \
    Registered as RegisteredMsg, Subscribe as SubscribeMsg, Subscribed as SubscribedMsg, Unregister as UnregisterMsg, \
    Unregistered as UnregisteredMsg, Unsubscribe as UnsubscribeMsg, Unsubscribed as UnsubscribedMsg
from aiowamp.uri import INVALID_ARGUMENT
from .call import Call
from .enum import CANCEL_KILL_NO_WAIT
from .event import SubscriptionEvent
from .invocation import Invocation
from .procedure_runner import ProcedureRunnerABC, RunnerFactory, get_runner_factory
from .utils import check_message_response

__all__ = ["InvocationHandlerResult",
           "InvocationHandler", "SubscriptionHandler",
           "ClientABC", "Client"]

log = logging.getLogger(__name__)

InvocationHandlerResult = Union["aiowamp.InvocationResult",
                                Tuple["aiowamp.WAMPType", ...],
                                None,
                                "aiowamp.WAMPType"]
"""Return value for a procedure.

The most specific return value is an instance of `aiowamp.InvocationResult` 
which is sent as-is.

Tuples are unpacked as the arguments.

    async def my_procedure():
        return ("hello", "world")
        # equal to: aiowamp.InvocationResult("hello", "world")

In order to return an actual `tuple`, wrap it in another tuple:

    async def my_procedure():
        my_tuple = ("hello", "world")
        return (my_tuple,)
        # equal to: aiowamp.InvocationResult(("hello", "world"))

Please note that no built-in serializer can handle tuples, so this shouldn't be
a common use-case.

Finally, `None` results in an empty response. This is so that bare return 
statements work the way you would expect. Again, if you really wish to return
`None` as the first argument, wrap it in a `tuple` or use 
`aiowamp.InvocationResult`.

Any other value is used as the first and only argument:

    async def my_procedure():
        return {"hello": "world", "world": "hello"}
        # equal to: aiowamp.InvocationResult({"hello": "world", "world": "hello"})


The only way to set keyword arguments is to use `aiowamp.InvocationResult` 
explicitly!
"""

InvocationHandler = Callable[["aiowamp.InvocationABC"],
                             Union[Awaitable["aiowamp.InvocationHandlerResult"],
                                   AsyncGenerator["aiowamp.InvocationHandlerResult", None]]]
"""Type of a procedure function.

Upon invocation, a procedure function will be called with an 
`aiowamp.InvocationABC` instance. This invocation can be used to get arguments 
and send results.

It's also possible to send results by returning them. As a rule of thumb, 
write the procedures the same as how you would write them without WAMP.

For example:

    async def my_procedure(invocation):
        # invocation objects implement a lot of utility methods. 
        a, b, c = invocation
        return sum(a, b, c)


As you can see, this procedure returns a single value (namely the sum of the 
first three arguments passed to the call). aiowamp interprets this as the first 
argument of the result. Different return values have different 
interpretations, but they should all work like you would expect them to. 
For more, please take a look at `aiowamp.InvocationHandlerResult`.


aiowamp also supports async generators, which can be used to send progress 
results:

    async def prog_results(invocation):
        final_n = invocation.get(0, 100)
        for i in range(final_n):
            yield i

        yield final_n

This rather useless procedure sends all numbers between 0 and the first 
argument, which defaults to 100 if not specified, as progress results.
The final iteration is then sent as the final result.

The above code has been written to make this point clear, but it would've worked
the same if we used `range(final_n + 1)` and removed the `yield final_n`.

IMPORTANT:
aiowamp doesn't know whether the async generator has yielded for the last time, 
as such, **all results wait for the next yield before being sent**. The first 
progress will be sent when the second yield statement is reached, the final 
result is sent when the async generator stops.
If this is an issue, **there are ways to get around it:**

An instance of `aiowamp.InvocationProgress` can be yielded which will cause the
progress to be sent immediately.
The WAMP protocol doesn't support progressive calls without a final result, if
the last yield of a procedure function is an instance of 
`aiowamp.InvocationProgress`, then an empty final result will be sent and a 
warning is issued.

Similarly, the semantics of `aiowamp.InvocationResult` are different in an 
async generator. When yielding an instance of `aiowamp.InvocationResult` it 
will be sent as the final result immediately.
This can be used to perform some actions after the result has been sent.
"""

SubscriptionHandler = Callable[["aiowamp.SubscriptionEventABC"], MaybeAwaitable[Any]]
"""Type of a subscription handler function.

The handler receives the `aiowamp.msg.Event` each time it is published.
When the handler returns an awaitable object, it is awaited.
The return value is ignored.
"""


# TODO add client shutdown which removes all subs/procedures and waits for all
#   pending tasks to finish before closing.


class ClientABC(abc.ABC):
    """WAMP Client.

    Implements the publisher, subscriber, caller, and callee roles.
    """
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {id(self):x}"

    @abc.abstractmethod
    async def wait_until_done(self) -> None:
        ...

    @abc.abstractmethod
    async def close(self, details: aiowamp.WAMPDict = None, *,
                    reason: str = None) -> None:
        """Close the client and the underlying session.

        Args:
            details: Additional details to send with the close message.
            reason: URI denoting the reason for closing.
                Defaults to `aiowamp.uri.CLOSE_NORMAL`.
        """
        ...

    @abc.abstractmethod
    async def register(self, procedure: str, handler: aiowamp.InvocationHandler, *,
                       disclose_caller: bool = None,
                       match_policy: aiowamp.MatchPolicy = None,
                       invocation_policy: aiowamp.InvocationPolicy = None,
                       options: aiowamp.WAMPDict = None) -> int:
        ...

    @abc.abstractmethod
    async def unregister(self, procedure: str, registration_id: int = None) -> None:
        ...

    @abc.abstractmethod
    def call(self, procedure: str, *args: aiowamp.WAMPType,
             kwargs: aiowamp.WAMPDict = None,
             receive_progress: bool = None,
             call_timeout: float = None,
             cancel_mode: aiowamp.CancelMode = None,
             disclose_me: bool = None,
             resource_key: str = None,
             options: aiowamp.WAMPDict = None) -> aiowamp.CallABC:
        ...

    @abc.abstractmethod
    async def subscribe(self, topic: str, callback: aiowamp.SubscriptionHandler, *,
                        match_policy: aiowamp.MatchPolicy = None,
                        node_key: str = None,
                        options: aiowamp.WAMPDict = None) -> int:
        ...

    @abc.abstractmethod
    async def unsubscribe(self, topic: str, subscription_id: int = None) -> None:
        """Unsubscribe from the given topic.

        Args:
            topic: Topic URI to unsubscribe from.
            subscription_id: Specific subscription id to unsubscribe.

        Raises:
            KeyError: If not subscribed to the topic.
        """
        ...

    @abc.abstractmethod
    async def publish(self, topic: str, *args: aiowamp.WAMPType,
                      kwargs: aiowamp.WAMPDict = None,
                      acknowledge: bool = None,
                      blackwhitelist: aiowamp.BlackWhiteList = None,
                      exclude_me: bool = None,
                      disclose_me: bool = None,
                      resource_key: str = None,
                      options: aiowamp.WAMPDict = None) -> None:
        ...


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
        self.id_gen = IDGenerator()

        self.__awaiting_reply = {}
        self.__ongoing_calls = {}
        self.__running_procedures = {}

        self.__procedure_ids = {}
        self.__procedures = {}

        self.__sub_ids = {}
        self.__sub_handlers = {}

        self.session.add_message_handler(self.__handle_message)

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.session!r})"

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {self.session.session_id}"

    async def __handle_invocation(self, invocation_msg: aiowamp.msg.Invocation) -> None:
        try:
            runner_factory, uri = self.__procedures[invocation_msg.registration_id]
        except KeyError:
            log.warning("%s: received invocation for unknown registration: %r", self, invocation_msg)

            await self.session.send(ErrorMsg(
                InvocationMsg.message_type,
                invocation_msg.request_id,
                {},
                INVALID_ARGUMENT,
                [f"client has no procedure for registration {invocation_msg.registration_id}"]
            ))
            return

        invocation = Invocation(self.session, self, invocation_msg, procedure=uri)

        try:
            runner = runner_factory(invocation)
        except Exception as e:
            log.exception("%s: couldn't start procedure %s", self, runner_factory)
            err = exception_to_invocation_error(e)
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

        await runner.interrupt(Interrupt(interrupt_msg.options))

    async def __handle_event(self, event_msg: aiowamp.msg.Event, handler: aiowamp.SubscriptionHandler,
                             topic: aiowamp.URI) -> None:
        event = SubscriptionEvent(self, event_msg, topic=topic)
        await call_async_fn(handler, event)

    async def __handle_message(self, msg: aiowamp.MessageABC) -> None:
        invocation = message_as_type(msg, InvocationMsg)
        if invocation:
            await self.__handle_invocation(invocation)
            return

        interrupt = message_as_type(msg, InterruptMsg)
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
        event = message_as_type(msg, EventMsg)
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
        exc = ClientClosed()
        self.session.remove_message_handler(self.__handle_message)

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

    async def wait_until_done(self) -> None:
        await self.session.wait_until_done()

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
            procedure_uri = URI(procedure, match_policy=match_policy)
        else:
            procedure_uri = URI.as_uri(procedure)

        if disclose_caller is not None:
            options = _set_value(options, "disclose_caller", disclose_caller)

        if procedure_uri.match_policy is not None:
            options = _set_value(options, "match", procedure_uri.match_policy)

        if invocation_policy is not None:
            options = _set_value(options, "invoke", invocation_policy)

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(RegisterMsg(
                req_id,
                options or {},
                procedure_uri,
            ))

        registered = check_message_response(await resp, RegisteredMsg)

        reg_id = registered.registration_id
        _add_to_array(self.__procedure_ids, procedure_uri, reg_id)

        self.__procedures[reg_id] = runner, procedure_uri

        return reg_id

    async def __unregister(self, reg_id: int) -> None:
        with contextlib.suppress(KeyError):
            del self.__procedures[reg_id]

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(UnregisterMsg(req_id, reg_id))

        check_message_response(await resp, UnregisteredMsg)

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
        call = Call(
            self.session,
            CallMsg(
                req_id,
                options or {},
                procedure,
                list(args) or None,
                kwargs,
            ),
            cancel_mode=cancel_mode or CANCEL_KILL_NO_WAIT
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
            topic_uri = URI(topic, match_policy=match_policy)
        else:
            topic_uri = URI.as_uri(topic)

        if topic_uri.match_policy:
            options = _set_value(options, "match", topic_uri.match_policy)

        if node_key is not None:
            options = _set_value(options, "nkey", node_key)

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(SubscribeMsg(
                req_id,
                options or {},
                topic_uri,
            ))

        subscribed = check_message_response(await resp, SubscribedMsg)

        sub_id = subscribed.subscription_id
        _add_to_array(self.__sub_ids, topic_uri, sub_id)
        self.__sub_handlers[sub_id] = callback, topic_uri

        return sub_id

    async def __unsubscribe(self, sub_id: int) -> None:
        with contextlib.suppress(KeyError):
            del self.__sub_handlers[sub_id]

        req_id = next(self.id_gen)
        async with self._expecting_response(req_id) as resp:
            await self.session.send(UnsubscribeMsg(req_id, sub_id))

        check_message_response(await resp, UnsubscribedMsg)

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
        send_coro = self.session.send(PublishMsg(
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

        check_message_response(await resp, PublishedMsg)


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
