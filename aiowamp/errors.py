from __future__ import annotations

import dataclasses
from typing import Type

import aiowamp
from .uri_map import URIMap

__all__ = ["Error",
           "TransportError",
           "AbortError", "AuthError",
           "InvalidMessage", "UnexpectedMessageError",
           "ErrorResponse",
           "register_error_response", "get_error_response_class", "create_error_response",
           "ClientClosed",
           "Interrupt"]


class Error(Exception):
    """Base exception for all WAMP related errors."""
    __slots__ = ()


class TransportError(Error):
    """Transport level error."""
    __slots__ = ()


class AbortError(Error):
    __slots__ = ("reason", "details")

    reason: str
    details: aiowamp.WAMPDict

    def __init__(self, msg: aiowamp.msg.Abort) -> None:
        self.reason = msg.reason
        self.details = msg.details

    def __str__(self) -> str:
        return f"{self.reason} (details = {self.details})"


class AuthError(Error):
    __slots__ = ()


class InvalidMessage(Error):
    """Exception for invalid messages."""
    __slots__ = ()


@dataclasses.dataclass()
class UnexpectedMessageError(InvalidMessage):
    """Exception raised when an unexpected message type is received."""
    __slots__ = ("received", "expected")

    received: aiowamp.MessageABC
    """Message that was received."""

    expected: Type[aiowamp.MessageABC]
    """Message type that was expected."""

    def __str__(self) -> str:
        return f"received message {self.received!r} but expected message of type {self.expected.__qualname__}"


class ErrorResponse(Error):
    __slots__ = ("message",)

    message: aiowamp.msg.Error
    """Error message."""

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

    @property
    def uri(self) -> aiowamp.URI:
        return self.message.error


ERR_RESP_MAP: URIMap[Type[ErrorResponse]] = URIMap()


def register_error_response(uri: str):
    uri = aiowamp.URI.as_uri(uri)

    def decorator(cls: Type[ErrorResponse]):
        if not issubclass(cls, ErrorResponse):
            raise TypeError(f"error class must be of type {ErrorResponse.__qualname__}")

        ERR_RESP_MAP[uri] = cls

        return cls

    return decorator


def get_error_response_class(uri: str) -> Type[ErrorResponse]:
    return ERR_RESP_MAP[uri]


def create_error_response(message: aiowamp.msg.Error) -> aiowamp.ErrorResponse:
    try:
        return get_error_response_class(message.error)(message)
    except LookupError:
        return ErrorResponse(message)


class ClientClosed(Error):
    __slots__ = ()


class Interrupt(Error):
    __slots__ = ("options",)

    options: aiowamp.WAMPDict
    """Options sent with the interrupt."""

    def __init__(self, options: aiowamp.WAMPDict) -> None:
        self.options = options

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}(options={self.options!r})"

    @property
    def cancel_mode(self) -> aiowamp.CancelMode:
        """Cancel mode sent with the interrupt."""
        return self.options["mode"]
