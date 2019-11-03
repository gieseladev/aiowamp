from __future__ import annotations

import dataclasses
from typing import Type

import aiowamp

__all__ = ["Error",
           "TransportError",
           "InvalidMessage", "UnexpectedMessageError",
           "ErrorResponse", "RPCError",
           "ClientClosed"]


class Error(Exception):
    """Base exception for all WAMP related errors."""
    __slots__ = ()


class TransportError(Error):
    __slots__ = ()


class InvalidMessage(Error):
    __slots__ = ()


@dataclasses.dataclass()
class UnexpectedMessageError(InvalidMessage):
    __slots__ = ("received", "expected")

    received: aiowamp.MessageABC
    expected: Type[aiowamp.MessageABC]

    def __str__(self) -> str:
        return f"received message {self.received!r} but expected message of type {self.expected.__qualname__}"


class ErrorResponse(Error):
    __slots__ = ("message",)

    message: aiowamp.msg.Error

    def __init__(self, message: aiowamp.msg.Error):
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.message!r})"

    def __str__(self) -> str:
        s = f"{self.message.error}"

        args_str = ", ".join(map(repr, self.message.args))
        if args_str:
            s += f" {args_str}"

        kwargs_str = ", ".join(f"{k}={v!r}" for k, v in self.message.kwargs.items())
        if kwargs_str:
            s += f" ({kwargs_str})"

        return s


class RPCError(ErrorResponse):
    __slots__ = ()


class ClientClosed(Error):
    __slots__ = ()
