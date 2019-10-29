import abc

from aiowamp.message import MessageABC, WAMPDict
from aiowamp.transport import TransportABC

__all__ = ["SessionABC", "Session"]


class SessionABC(abc.ABC):
    __slots__ = ()

    @property
    @abc.abstractmethod
    def id(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def realm(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def details(self) -> WAMPDict:
        ...

    @abc.abstractmethod
    async def send(self, msg: MessageABC) -> None:
        ...


class Session(SessionABC):
    __slots__ = ("__id", "__details", "__realm",
                 "transport")

    __id: int
    __details: WAMPDict
    __realm: str
    transport: TransportABC

    @property
    def id(self) -> int:
        return self.__id

    @property
    def realm(self) -> str:
        return self.__realm

    @property
    def details(self) -> WAMPDict:
        return self.__details

    async def send(self, msg: MessageABC) -> None:
        await self.transport.send(msg)
