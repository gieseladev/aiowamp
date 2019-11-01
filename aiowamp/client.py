from __future__ import annotations

import abc
import asyncio
import contextlib
from typing import Any, Awaitable, ContextManager, Dict, MutableMapping, Optional, Iterator

import aiowamp

__all__ = ["ClientABC", "Client"]


class ClientABC(abc.ABC):
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {id(self):x}"

    @abc.abstractmethod
    async def close(self) -> None:
        ...

    @abc.abstractmethod
    async def call(self, procedure: str, *args: aiowamp.WAMPType, options: aiowamp.WAMPDict = None,
                   **kwargs: aiowamp.WAMPType) -> Any:
        ...

    @abc.abstractmethod
    async def subscribe(self, topic: str, *, options: aiowamp.WAMPDict = None) -> None:
        ...

    @abc.abstractmethod
    async def unsubscribe(self, topic: str) -> None:
        ...

    @abc.abstractmethod
    async def publish(self, topic: str, *args: aiowamp.WAMPType, options: aiowamp.WAMPDict = None,
                      **kwargs: aiowamp.WAMPType) -> None:
        ...


class Client(ClientABC):
    session: aiowamp.SessionABC
    id_gen: aiowamp.IDGeneratorABC

    __awaiting_reply: Dict[int, asyncio.Future]

    def __init__(self, session: aiowamp.SessionABC) -> None:
        self.session = session
        self.id_gen = aiowamp.IDGenerator()

        self.__awaiting_reply = {}

        self.session.message_handler.on(callback=self.__handle_message)

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.session!r})"

    async def __handle_message(self, msg: aiowamp.MessageABC) -> None:
        try:
            waiter = self.__awaiting_reply[getattr(msg, "request_id")]
        except (AttributeError, KeyError):
            pass
        else:
            waiter.set_result(msg)

    @contextlib.contextmanager
    def _expecting_response(self, req_id: int) -> Iterator[Awaitable[aiowamp.MessageABC]]:
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self.__awaiting_reply[req_id] = fut

        try:
            yield fut
        finally:
            with contextlib.suppress(KeyError):
                del self.__awaiting_reply[req_id]

    async def close(self) -> None:
        await self.session.close()

    async def call(self, procedure: str, *args: aiowamp.WAMPType, options: aiowamp.WAMPDict = None,
                   **kwargs: aiowamp.WAMPType) -> Any:
        options = _check_kwargs_options(options, kwargs)

        req_id = next(self.id_gen)
        with self._expecting_response(req_id) as resp:
            await self.session.send(aiowamp.msg.Call(
                req_id,
                options,
                aiowamp.URI(procedure),
                list(args),
                kwargs,
            ))

        msg = await resp
        result = aiowamp.message_as_type(msg, aiowamp.msg.Result)
        if result: return result

        error = aiowamp.message_as_type(msg, aiowamp.msg.Error)
        if error: raise aiowamp.RPCError()

        raise aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Result)

    async def subscribe(self, topic: str, *, options: aiowamp.WAMPDict = None) -> None:
        req_id = next(self.id_gen)

        await self.session.send(aiowamp.msg.Subscribe(
            req_id,
            options or {},
            aiowamp.URI(topic),
        ))

    async def unsubscribe(self, topic: str) -> None:
        pass

    async def publish(self, topic: str, *args: aiowamp.WAMPType, options: aiowamp.WAMPDict = None,
                      **kwargs: aiowamp.WAMPType) -> None:
        options = _check_kwargs_options(options, kwargs)

        req_id = next(self.id_gen)

        await self.session.send(aiowamp.msg.Publish(
            req_id,
            options,
            aiowamp.URI(topic),
            list(args),
            kwargs,
        ))


def _check_kwargs_options(options: Optional[aiowamp.WAMPDict],
                          kwargs: MutableMapping[str, aiowamp.WAMPType]) -> aiowamp.WAMPDict:
    if isinstance(options, dict):
        return options

    if options is not None:
        kwargs["options"] = options

    return {}


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
