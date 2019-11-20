from __future__ import annotations

import abc
import contextlib
import datetime
import logging
import time
from typing import Generic, Optional, Tuple, TypeVar, Union

import aiowamp
from aiowamp import InvocationError, URI, set_invocation_error
from aiowamp.args_mixin import ArgsMixin
from aiowamp.msg import Error as ErrorMsg, Invocation as InvocationMsg, Yield as YieldMsg
from aiowamp.uri import INVALID_ARGUMENT
from .enum import CANCEL_KILL_NO_WAIT

__all__ = ["InvocationABC", "Invocation",
           "InvocationResult", "InvocationProgress"]

log = logging.getLogger(__name__)

ClientT = TypeVar("ClientT", bound="aiowamp.ClientABC")


class InvocationABC(ArgsMixin, abc.ABC, Generic[ClientT]):
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {self.request_id}"

    @property
    @abc.abstractmethod
    def client(self) -> ClientT:
        ...

    @property
    @abc.abstractmethod
    def request_id(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def registered_procedure(self) -> aiowamp.URI:
        ...

    @property
    def procedure(self) -> aiowamp.URI:
        """Concrete procedure that caused the invocation.

        This will be the same as `registered_procedure` unless the procedure was
        registered with a pattern-based matching policy.
        """
        try:
            return URI(self.details["procedure"])
        except KeyError:
            return self.registered_procedure

    @property
    @abc.abstractmethod
    def args(self) -> Tuple[aiowamp.WAMPType, ...]:
        ...

    @property
    @abc.abstractmethod
    def kwargs(self) -> aiowamp.WAMPDict:
        ...

    @property
    @abc.abstractmethod
    def details(self) -> aiowamp.WAMPDict:
        ...

    @property
    def may_send_progress(self) -> bool:
        """Whether or not the caller is willing to receive progressive results."""
        try:
            return bool(self.details["receive_progress"])
        except KeyError:
            return False

    @property
    def caller_id(self) -> Optional[int]:
        """Get the caller's id.

        You can specify the "disclose_caller" option when registering a
        procedure to force disclosure.

        Returns:
            WAMP id of the caller, or `None` if not specified.
        """
        return self.details.get("caller")

    @property
    def trust_level(self) -> Optional[int]:
        """Get the router assigned trust level.

        The trust level 0 means lowest trust, and higher integers represent
        (application-defined) higher levels of trust.

        Returns:
            The trust level, or `None` if not specified.
        """
        return self.details.get("trustlevel")

    @property
    @abc.abstractmethod
    def timeout(self) -> float:
        """Timeout in seconds.

        `0` if no timeout was provided which means the call doesn't time out.
        """
        ...

    @property
    @abc.abstractmethod
    def timeout_at(self) -> Optional[datetime.datetime]:
        """Time at which the invocation will be cancelled.

        `None` if the call doesn't time out.

        Trying to send a message (result, progress, error) after the call is
        cancelled will raise an exception. Use `.done` to check whether the
        invocation can send messages.
        """
        ...

    @property
    @abc.abstractmethod
    def done(self) -> bool:
        ...

    @property
    @abc.abstractmethod
    def interrupt(self) -> Optional[aiowamp.Interrupt]:
        ...

    @abc.abstractmethod
    async def send_progress(self, *args: aiowamp.WAMPType,
                            kwargs: aiowamp.WAMPDict = None,
                            options: aiowamp.WAMPDict = None) -> None:
        ...

    @abc.abstractmethod
    async def send_result(self, *args: aiowamp.WAMPType,
                          kwargs: aiowamp.WAMPDict = None,
                          options: aiowamp.WAMPDict = None) -> None:
        ...

    @abc.abstractmethod
    async def send_error(self, error: str, *args: aiowamp.WAMPType,
                         kwargs: aiowamp.WAMPDict = None,
                         details: aiowamp.WAMPDict = None) -> None:
        ...

    @abc.abstractmethod
    def _cancel(self) -> None:
        ...

    @abc.abstractmethod
    async def _receive_interrupt(self, interrupt: aiowamp.Interrupt) -> None:
        ...


class Invocation(InvocationABC[ClientT], Generic[ClientT]):
    __slots__ = ("session",
                 "__client",
                 "__timeout", "__timeout_at",
                 "__done", "__interrupt",
                 "__procedure", "__request_id",
                 "__args", "__kwargs", "__details")

    session: aiowamp.SessionABC
    """Session used to send messages."""

    __client: ClientT

    __done: bool
    __interrupt: Optional[aiowamp.Interrupt]

    __procedure: aiowamp.URI
    __request_id: int

    __args: Tuple[aiowamp.WAMPType, ...]
    __kwargs: aiowamp.WAMPDict
    __details: aiowamp.WAMPDict

    def __init__(self, session: aiowamp.SessionABC, client: ClientT, msg: aiowamp.msg.Invocation, *,
                 procedure: aiowamp.URI) -> None:
        """Create a new invocation instance.

        Normally you should not create these yourself, they don't actively listen
        for incoming messages. Instead, they rely on the `aiowamp.ClientABC` to
        receive and pass them.

        Args:
            session: WAMP Session to send messages in.
            msg: Invocation message that spawned the invocation.
            procedure: Registered procedure URI.
        """
        self.session = session
        self.__client = client

        self.__done = False
        self.__interrupt = None

        self.__procedure = procedure
        self.__request_id = msg.request_id

        self.__args = tuple(msg.args) if msg.args else ()
        self.__kwargs = msg.kwargs or {}
        self.__details = msg.details

        try:
            self.__timeout = self.__details["timeout"] / 1e3
        except KeyError:
            self.__timeout = 0

        # the default is 0 which means no timeout
        if self.__timeout:
            ts = time.time() + self.__timeout
            self.__timeout_at = datetime.datetime.utcfromtimestamp(ts)
        else:
            self.__timeout_at = None

    def __getitem__(self, key: Union[int, str]) -> aiowamp.WAMPType:
        try:
            return super().__getitem__(key)
        except LookupError as e:
            if isinstance(key, int):
                msg = f"expected {key + 1} arguments, got {len(self)}"
            else:
                msg = f"missing keyword argument {key!r}"

            set_invocation_error(e, InvocationError(
                INVALID_ARGUMENT,
                msg,
                kwargs={"key": key},
            ))
            raise e from None

    @property
    def client(self) -> ClientT:
        return self.__client

    @property
    def request_id(self) -> int:
        return self.__request_id

    @property
    def registered_procedure(self) -> aiowamp.URI:
        return self.__procedure

    @property
    def args(self) -> Tuple[aiowamp.WAMPType, ...]:
        return self.__args

    @property
    def kwargs(self) -> aiowamp.WAMPDict:
        return self.__kwargs

    @property
    def details(self) -> aiowamp.WAMPDict:
        return self.__details

    @property
    def timeout(self) -> float:
        return self.__timeout

    @property
    def timeout_at(self) -> Optional[datetime.datetime]:
        return self.__timeout_at

    @property
    def done(self) -> bool:
        return self.__done

    @property
    def interrupt(self) -> Optional[aiowamp.Interrupt]:
        return self.__interrupt

    def __assert_not_done(self) -> None:
        if self.__done:
            raise RuntimeError(f"{self}: already completed")

    def __mark_done(self) -> None:
        self.__assert_not_done()
        self.__done = True

    async def send_progress(self, *args: aiowamp.WAMPType,
                            kwargs: aiowamp.WAMPDict = None,
                            options: aiowamp.WAMPDict = None) -> None:
        self.__assert_not_done()

        if not self.may_send_progress:
            raise RuntimeError(f"{self}: caller is unwilling to receive progress")

        # must not send progress when interrupted.
        if self.__interrupt:
            raise self.__interrupt

        options = options or {}
        options["progress"] = True

        await self.session.send(YieldMsg(
            self.__request_id,
            options,
            list(args) or None,
            kwargs,
        ))

    async def send_result(self, *args: aiowamp.WAMPType,
                          kwargs: aiowamp.WAMPDict = None,
                          options: aiowamp.WAMPDict = None) -> None:
        self.__mark_done()

        if options:
            # make sure we're not accidentally sending a result with progress=True
            with contextlib.suppress(KeyError):
                del options["progress"]
        else:
            options = {}

        await self.session.send(YieldMsg(
            self.__request_id,
            options,
            list(args) or None,
            kwargs,
        ))

    async def send_error(self, error: str, *args: aiowamp.WAMPType,
                         kwargs: aiowamp.WAMPDict = None,
                         details: aiowamp.WAMPDict = None) -> None:
        self.__mark_done()

        await self.session.send(ErrorMsg(
            InvocationMsg.message_type,
            self.__request_id,
            details or {},
            error,
            list(args) or None,
            kwargs,
        ))

    def _cancel(self) -> None:
        self.__done = True

    async def _receive_interrupt(self, interrupt: aiowamp.Interrupt) -> None:
        self.__interrupt = interrupt

        # if the cancel mode is killnowait the caller won't accept a response.
        if interrupt.cancel_mode == CANCEL_KILL_NO_WAIT:
            self._cancel()


class InvocationResult(ArgsMixin):
    """Helper class for procedures.

    Use this to return/yield a result from a `aiowamp.InvocationHandler`
    containing keyword arguments.
    """

    __slots__ = ("args", "kwargs",
                 "details")

    args: Tuple[aiowamp.WAMPType, ...]
    """Arguments."""

    kwargs: aiowamp.WAMPDict
    """Keyword arguments."""

    details: aiowamp.WAMPDict
    """Details."""

    def __init__(self, *args: aiowamp.WAMPType, **kwargs: aiowamp.WAMPType) -> None:
        self.args = args
        self.kwargs = kwargs

        self.details = {}


class InvocationProgress(InvocationResult):
    """Helper class for procedures.

    Instances of this class can be yielded by procedures to indicate that it
    it's intended to be sent as a progress.

    Usually, because there's no way to tell whether an async generator has
    yielded for the last time, aiowamp waits for the next yield before sending
    a progress result (i.e. it always lags behind one message).
    When returning an instance of this class however, aiowamp will send it
    immediately.

    It is possible to abuse this by returning an instance of this class for the
    final yield. This is not supported by the WAMP protocol and currently
    results in aiowamp sending an empty final result.
    """
    __slots__ = ()
