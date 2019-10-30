from __future__ import annotations

import dataclasses
from typing import Type

import aiowamp

__all__ = ["Error",
           "InvalidMessage", "UnexpectedMessageError",
           "RPCError"]


class Error(Exception):
    """Base exception for all WAMP related errors."""
    ...


class InvalidMessage(Error):
    ...


@dataclasses.dataclass()
class UnexpectedMessageError(InvalidMessage):
    received: aiowamp.MessageABC
    expected: Type[aiowamp.MessageABC]

    def __str__(self) -> str:
        return f"received message {self.received!r} but expected message of type {self.expected.__qualname__}"


class RPCError(Error):
    ...
