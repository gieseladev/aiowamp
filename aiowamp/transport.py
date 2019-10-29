import abc

from aiowamp.message import MessageABC

__all__ = ["TransportABC"]


class TransportABC(abc.ABC):
    __slots__ = ()

    @abc.abstractmethod
    async def close(self) -> None:
        ...

    @abc.abstractmethod
    async def send(self, msg: MessageABC) -> None:
        ...

    @abc.abstractmethod
    async def recv(self) -> MessageABC:
        ...
