import abc
from typing import Any, MutableMapping, Optional

import aiobservable

from aiowamp import msg
from aiowamp.id import IDGenerator, IDGeneratorABC
from aiowamp.message import WAMPDict, WAMPType
from aiowamp.session import SessionABC
from aiowamp.uri import URI

__all__ = ["ClientABC", "Client"]


class ClientABC(abc.ABC):
    @abc.abstractmethod
    async def call(self, procedure: str, *args: WAMPType, options: WAMPDict = None, **kwargs: WAMPType) -> Any:
        ...

    @abc.abstractmethod
    async def subscribe(self, topic: str, *, options: WAMPDict = None) -> aiobservable.SubscriptionABC:
        ...

    @abc.abstractmethod
    async def unsubscribe(self, topic: str) -> None:
        ...

    @abc.abstractmethod
    async def publish(self, topic: str, *args: WAMPType, options: WAMPDict = None, **kwargs: WAMPType) -> None:
        ...


class Client(ClientABC):
    session: SessionABC
    id_gen: IDGeneratorABC

    def __init__(self, session: SessionABC) -> None:
        self.session = session
        self.id_gen = IDGenerator()

    async def call(self, procedure: str, *args: WAMPType, options: WAMPDict = None, **kwargs: WAMPType) -> Any:
        options = _check_kwargs_options(options, kwargs)

        req_id = next(self.id_gen)

        await self.session.send(msg.Call(
            req_id,
            options,
            URI(procedure),
            list(args),
            kwargs,
        ))

    async def subscribe(self, topic: str, *, options: WAMPDict = None) -> None:
        req_id = next(self.id_gen)

        await self.session.send(msg.Subscribe(
            req_id,
            options or {},
            URI(topic),
        ))

    async def unsubscribe(self, topic: str) -> None:
        pass

    async def publish(self, topic: str, *args: WAMPType, options: WAMPDict = None, **kwargs: WAMPType) -> None:
        options = _check_kwargs_options(options, kwargs)

        req_id = next(self.id_gen)

        await self.session.send(msg.Publish(
            req_id,
            options,
            URI(topic),
            list(args),
            kwargs,
        ))


def _check_kwargs_options(options: Optional[WAMPDict], kwargs: MutableMapping[str, WAMPType]) -> WAMPDict:
    if isinstance(options, dict):
        return options

    if options is not None:
        kwargs["options"] = options

    return {}
