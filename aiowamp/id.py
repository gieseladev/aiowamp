import abc
from typing import Iterator

__all__ = ["IDGeneratorABC", "IDGenerator"]

MAX_ID = 1 << 53


class IDGeneratorABC(Iterator[int], abc.ABC):
    """Abstract WAMP ID generator type."""
    __slots__ = ()

    def __next__(self) -> int:
        return self.next()

    @abc.abstractmethod
    def next(self) -> int:
        """Return the next id.

        Returns:
            The next id.
        """
        ...


class IDGenerator(IDGeneratorABC):
    """Sequential ID generator."""
    __slots__ = ("__id",)

    __id: int

    def __init__(self) -> None:
        self.__id = 0

    def __str__(self) -> str:
        return f"IDGenerator{self.__id}"

    def next(self) -> int:
        self.__id += 1
        if self.__id > MAX_ID:
            self.__id = 1

        return self.__id
