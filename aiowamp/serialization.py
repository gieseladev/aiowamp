import abc

import aiowamp

__all__ = ["SerializerABC"]


class SerializerABC(abc.ABC):
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {id(self):x}"

    @abc.abstractmethod
    def serialize(self, msg: aiowamp.MessageABC) -> bytes:
        ...

    @abc.abstractmethod
    def deserialize(self, data: bytes) -> aiowamp.MessageABC:
        ...
