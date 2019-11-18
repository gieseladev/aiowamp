import abc
import textwrap

__all__ = ["Code",
           "indent"]


class Code(abc.ABC):
    @abc.abstractmethod
    def code(self) -> str:
        ...

    def update_globals(self, globalns: dict) -> None:
        pass


def indent(level: int, s: str) -> str:
    return textwrap.indent(s, level * "    ")
