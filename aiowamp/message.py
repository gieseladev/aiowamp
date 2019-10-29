import abc
from typing import Dict, List, Type, TypeVar, Union

__all__ = ["WAMPType", "WAMPList", "WAMPDict",
           "MessageABC",
           "register_message", "get_message_type"]

WAMPType = Union[int, str, bool, "WAMPList", "WAMPDict"]
WAMPList = List[WAMPType]
WAMPDict = Dict[str, WAMPType]

T = TypeVar("T")


class MessageABC(abc.ABC):
    __slots__ = ()

    def __str__(self) -> str:
        return f"{self.message_type} {type(self).__name__}"

    @property
    @abc.abstractmethod
    def message_type(self) -> int:
        ...

    @abc.abstractmethod
    def to_message_list(self) -> WAMPList:
        ...

    @classmethod
    @abc.abstractmethod
    def from_message_list(cls: Type[T], msg_list: WAMPList) -> T:
        ...


MESSAGE_TYPE_MAP = {}


def register_message(*messages: Type[MessageABC]) -> None:
    for m in messages:
        mtyp = m.message_type
        if mtyp in MESSAGE_TYPE_MAP:
            raise ValueError(f"Cannot register message {mtyp!r} for code {mtyp}. Already exists")

        MESSAGE_TYPE_MAP[mtyp] = m


def get_message_type(msg_type: int) -> Type[MessageABC]:
    try:
        return MESSAGE_TYPE_MAP[msg_type]
    except KeyError:
        raise KeyError(f"No message type registered for type: {msg_type}") from None
