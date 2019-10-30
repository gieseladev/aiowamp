from __future__ import annotations

import abc
import asyncio
import contextlib
from typing import Any, Dict, MutableMapping, Optional

import aiobservable

import aiowamp

__all__ = ["ClientABC", "Client"]


class ClientABC(abc.ABC):
    __slots__ = ()

    @abc.abstractmethod
    async def call(self, procedure: str, *args: aiowamp.WAMPType, options: aiowamp.WAMPDict = None,
                   **kwargs: aiowamp.WAMPType) -> Any:
        ...

    @abc.abstractmethod
    async def subscribe(self, topic: str, *, options: aiowamp.WAMPDict = None) -> aiobservable.SubscriptionABC:
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

    def _expect_response(self, req_id: int) -> None:
        loop = asyncio.get_event_loop()
        fut = loop.create_future()

        self.__awaiting_reply[req_id] = fut

    async def _await_response(self, req_id: int) -> aiowamp.MessageABC:
        try:
            fut = self.__awaiting_reply[req_id]
        except KeyError:
            raise KeyError(f"not expecting a response for request {req_id}") from None

        try:
            return await fut
        finally:
            with contextlib.suppress(KeyError):
                del self.__awaiting_reply[req_id]

    async def call(self, procedure: str, *args: aiowamp.WAMPType, options: aiowamp.WAMPDict = None,
                   **kwargs: aiowamp.WAMPType) -> Any:
        options = _check_kwargs_options(options, kwargs)

        req_id = next(self.id_gen)
        self._expect_response(req_id)

        await self.session.send(aiowamp.msg.Call(
            req_id,
            options,
            aiowamp.URI(procedure),
            list(args),
            kwargs,
        ))

        msg = await self._await_response(req_id)
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
