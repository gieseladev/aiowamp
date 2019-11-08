import abc
from typing import Iterator

__all__ = ["IDGeneratorABC", "IDGenerator"]

MAX_ID = 1 << 53
"""The biggest id that should be used in the WAMP protocol.

This is to support languages which only support IEEE 754 floating point numbers
(like JavaScript).
"""


class IDGeneratorABC(Iterator[int], abc.ABC):
    """Abstract WAMP ID generator type.

    Should be used like an iterator by passing it to `next`.
    Note that the generator should never raise `StopIteration`.
    """
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {id(self):x}"

    def __iter__(self):
        return self

    @abc.abstractmethod
    def __next__(self) -> int:
        """Generate the next id.

        Returns:
            The generated id.
        """
        ...


class IDGenerator(IDGeneratorABC):
    """Sequential ID generator.

    Generates sequential ids starting from 1 up to 2^53 (inclusive) before
    restarting.
    """
    __slots__ = ("__id",)

    __id: int

    def __init__(self) -> None:
        """Create a new id generator.

        The first generated id will be 1.
        """
        self.__id = 0

    def __repr__(self) -> str:
        return "IDGenerator()"

    def __str__(self) -> str:
        return f"IDGenerator {self.__id}"

    def __next__(self) -> int:
        self.__id += 1
        if self.__id > MAX_ID:
            self.__id = 1

        return self.__id
