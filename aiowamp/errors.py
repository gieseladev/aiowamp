from __future__ import annotations

import dataclasses
import logging
from typing import Callable, Dict, Optional, Type

import aiowamp
from .args_mixin import ArgsMixin
from .uri import RUNTIME_ERROR, URI
from .uri_map import URIMap

__all__ = ["BaseError",
           "TransportError",
           "AbortError", "AuthError",
           "InvalidMessage", "UnexpectedMessageError",
           "ErrorResponse",
           "ClientClosed",
           "Interrupt",
           "register_error_response", "error_to_exception",
           "InvocationError", "exception_to_invocation_error",
           "set_invocation_error"]

log = logging.getLogger(__name__)


class BaseError(Exception):
    """Base exception for all WAMP related errors.

    You will most likely never encounter this error directly, but its
    subclasses.
    """
    __slots__ = ()


class TransportError(BaseError):
    """Transport level error."""
    __slots__ = ()


class AbortError(BaseError):
    """Join abort error."""
    __slots__ = ("reason", "details")

    reason: str
    details: aiowamp.WAMPDict

    def __init__(self, msg: aiowamp.msg.Abort) -> None:
        self.reason = msg.reason
        self.details = msg.details

    def __str__(self) -> str:
        return f"{self.reason} (details = {self.details})"


class AuthError(BaseError):
    __slots__ = ()


class InvalidMessage(BaseError):
    """Exception for invalid messages."""
    __slots__ = ()


@dataclasses.dataclass()
class UnexpectedMessageError(InvalidMessage):
    """Exception raised when an unexpected message type is received."""
    __slots__ = ("received", "expected")

    received: aiowamp.MessageABC
    """Message that was received."""

    expected: Type["aiowamp.MessageABC"]
    """Message type that was expected."""

    def __str__(self) -> str:
        return f"received message {self.received!r} but expected message of type {self.expected.__qualname__}"


class ErrorResponse(BaseError, ArgsMixin):
    __slots__ = ("message",
                 "uri", "args", "kwargs", "details")

    message: aiowamp.msg.Error
    """Error message."""

    uri: aiowamp.URI
    details: aiowamp.WAMPDict

    def __init__(self, message: aiowamp.msg.Error):
        self.message = message

        self.uri = message.error
        self.args = tuple(message.args) if message.args else ()
        self.kwargs = message.kwargs or {}
        self.details = message.details

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.message!r})"

    def __str__(self) -> str:
        s = f"{self.uri}"

        args_str = ", ".join(map(repr, self.args))
        if args_str:
            s += f" {args_str}"

        kwargs_str = ", ".join(f"{k}={v!r}" for k, v in self.kwargs.items())
        if kwargs_str:
            s += f" ({kwargs_str})"

        return s


ErrorFactory = Callable[["aiowamp.msg.Error"], Exception]
"""Callable creating an exception from a WAMP error message."""

ERR_RESP_MAP: URIMap[ErrorFactory] = URIMap()
EXC_URI_MAP: Dict[Type[Exception], "aiowamp.URI"] = {}


def register_error_response(uri: str, *,
                            match_policy: aiowamp.MatchPolicy = None):
    if match_policy is not None:
        uri = URI(uri, match_policy=match_policy)
    else:
        uri = URI.as_uri(uri)

    def decorator(cls: ErrorFactory):
        if not callable(cls):
            raise TypeError("error factory must be callable")

        ERR_RESP_MAP[uri] = cls

        return cls

    return decorator


def get_exception_factory(uri: str) -> ErrorFactory:
    return ERR_RESP_MAP[uri]


def error_to_exception(message: aiowamp.msg.Error) -> Exception:
    try:
        return get_exception_factory(message.error)(message)
    except LookupError:
        return ErrorResponse(message)


def get_exception_uri(exc: Type[Exception]) -> aiowamp.URI:
    return EXC_URI_MAP[exc]


class InvocationError(BaseError):
    __slots__ = ("uri",
                 "args", "kwargs",
                 "details")

    uri: aiowamp.URI
    args: Optional["aiowamp.WAMPList"]
    kwargs: Optional["aiowamp.WAMPDict"]
    details: Optional["aiowamp.WAMPDict"]

    def __init__(self, uri: str, *args: aiowamp.WAMPType,
                 kwargs: aiowamp.WAMPDict = None,
                 details: aiowamp.WAMPDict = None) -> None:
        self.uri = URI(uri)
        self.args = list(args) or None
        self.kwargs = kwargs or None
        self.details = details or None

    def _init(self, other: InvocationError) -> None:
        self.uri = other.uri
        self.args = other.args
        self.kwargs = other.kwargs
        self.details = other.details

    def __repr__(self) -> str:
        if self.args:
            args_str = ", " + ", ".join(map(repr, self.args))
        else:
            args_str = ""

        if self.kwargs:
            kwargs_str = f", kwargs={self.kwargs!r}"
        else:
            kwargs_str = ""

        if self.details:
            details_str = f", details={self.details!r}"
        else:
            details_str = ""

        return f"{type(self).__qualname__}({self.uri!r}{args_str}{kwargs_str}{details_str})"

    def __str__(self) -> str:
        if self.args:
            args_str = ", ".join(map(str, self.args))
            return f"{self.uri} {args_str}"

        return self.uri


ATTACHED_ERR_KEY = "__invocation_error__"


def set_invocation_error(exc: Exception, err: InvocationError) -> None:
    """Attach an invocation error to an exception.

    This makes it possible to raise a seemingly normal python `Exception` while
    preserving the additional information for WAMP.

    The attached error can then be retrieved by `exception_to_invocation_error`.

    If the exception is an invocation error, it is overwritten with the new
    error.

    Args:
        exc: Exception to attach the invocation error to.
        err: Invocation error to attach.
    """
    if isinstance(exc, InvocationError):
        log.info("overwriting %s with %s", exc, err)
        exc._init(err)
        return

    setattr(exc, ATTACHED_ERR_KEY, err)


def exception_to_invocation_error(exc: Exception) -> InvocationError:
    if isinstance(exc, InvocationError):
        return exc

    try:
        return getattr(exc, ATTACHED_ERR_KEY)
    except AttributeError:
        pass

    try:
        uri = get_exception_uri(type(exc))
    except LookupError:
        log.info(f"no uri registered for exception {type(exc).__qualname__}. "
                 f"Using {RUNTIME_ERROR!r}")
        uri = RUNTIME_ERROR

    return InvocationError(uri, *exc.args)


class ClientClosed(BaseError):
    __slots__ = ()


class Interrupt(BaseError):
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
