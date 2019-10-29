import abc

from aiowamp.message import MessageABC

__all__ = ["SerializerABC"]


class SerializerABC(abc.ABC):
    __slots__ = ()

    @abc.abstractmethod
    def serialize(self, msg: MessageABC) -> bytes:
        ...

    @abc.abstractmethod
    def deserialize(self, data: bytes) -> MessageABC:
        ...
