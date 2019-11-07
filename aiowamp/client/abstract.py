from __future__ import annotations

import abc
from typing import Any, AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterator, Optional, Tuple, TypeVar, Union, \
    overload

import aiowamp

__all__ = ["MaybeAwaitable",
           "InvocationResult", "InvocationProgress", "InvocationABC",
           "ProgressHandler",
           "CallABC",
           "InvocationHandlerResult", "InvocationHandler",
           "SubscriptionHandler",
           "ClientABC"]

T = TypeVar("T")

MaybeAwaitable = Union[T, Awaitable[T]]
"""Either a concrete object or an awaitable."""


class ArgsMixin:
    """Helper class which provides useful methods for types with args and kwargs."""
    __slots__ = ()

    args: Tuple[aiowamp.WAMPType, ...]
    kwargs: aiowamp.WAMPDict

    def __repr__(self) -> str:
        arg_str = ", ".join(map(repr, self.args))
        kwarg_str = ", ".join(f"{key} = {value!r}" for key, value in self.kwargs.items())
        if kwarg_str and arg_str:
            join_str = ", "
        else:
            join_str = ""

        return f"{type(self).__qualname__}({arg_str}{join_str}{kwarg_str})"

    def __len__(self) -> int:
        return len(self.args)

    def __iter__(self) -> Iterator[aiowamp.WAMPType]:
        return iter(self.args)

    def __getitem__(self, key: Union[int, str]) -> aiowamp.WAMPType:
        if isinstance(key, str):
            return self.kwargs[key]

        return self.args[key]

    def __contains__(self, key: str) -> bool:
        return key in self.kwargs

    @overload
    def get(self, key: Union[int, str]) -> Optional[aiowamp.WAMPType]:
        ...

    @overload
    def get(self, key: Union[int, str], default: T) -> Union[aiowamp.WAMPType, T]:
        ...

    def get(self, key: Union[int, str], default: T = None) -> Union[aiowamp.WAMPType, T, None]:
        """Get the value assigned to the given key.

        If the key is a string it is looked-up in the keyword arguments.
        If it's an integer it is treated as an index for the arugments.

        Args:
            key: Index or keyword to get value for.
            default: Default value to return. Defaults to `None`.

        Returns:
            The value assigned to the key or the default value if not found.
        """
        try:
            return self[key]
        except (KeyError, IndexError):
            return default


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


class InvocationABC(ArgsMixin, abc.ABC):
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {self.request_id}"

    @property
    @abc.abstractmethod
    def request_id(self) -> int:
        ...

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
        try:
            return bool(self.details["receive_progress"])
        except KeyError:
            return False

    @property
    def caller_id(self) -> Optional[int]:
        return self.details.get("caller")

    @property
    def trust_level(self) -> Optional[int]:
        return self.details.get("trustlevel")

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
    async def _receive_interrupt(self, interrupt: aiowamp.Interrupt) -> None:
        ...


ProgressHandler = Callable[[InvocationProgress], MaybeAwaitable[Any]]


class CallABC(Awaitable[InvocationResult], AsyncIterator[InvocationProgress], abc.ABC):
    __slots__ = ()

    def __str__(self) -> str:
        return f"Call {self.request_id}"

    def __await__(self):
        return self.result().__await__()

    def __aiter__(self):
        return self

    async def __anext__(self):
        progress = await self.next_progress()
        if progress is None:
            raise StopAsyncIteration

        return progress

    @property
    @abc.abstractmethod
    def request_id(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def done(self) -> bool:
        ...

    @property
    @abc.abstractmethod
    def cancelled(self) -> bool:
        ...

    @abc.abstractmethod
    def on_progress(self, handler: aiowamp.ProgressHandler) -> None:
        ...

    @abc.abstractmethod
    async def result(self) -> aiowamp.InvocationResult:
        ...

    @abc.abstractmethod
    async def next_progress(self) -> Optional[aiowamp.InvocationProgress]:
        ...

    @abc.abstractmethod
    async def cancel(self, cancel_mode: aiowamp.CancelMode = None, *,
                     options: aiowamp.WAMPDict = None) -> None:
        ...


InvocationHandlerResult = Union[InvocationResult,
                                Tuple[aiowamp.WAMPType, ...],
                                None,
                                aiowamp.WAMPType]
"""Return value for a procedure.

The most specific return value is an instance of `aiowamp.InvocationResult` 
which is sent as-is.

Tuples are unpacked as the arguments.

    async def my_procedure():
        return ("hello", "world")
        # equal to: aiowamp.InvocationResult("hello", "world")

In order to return an actual `tuple`, wrap it in another tuple:

    async def my_procedure():
        my_tuple = ("hello", "world")
        return (my_tuple,)
        # equal to: aiowamp.InvocationResult(("hello", "world"))

Please note that no built-in serializer can handle tuples, so this shouldn't be
a common use-case.

Finally, `None` results in an empty response. This is so that bare return 
statements work the way you would expect. Again, if you really wish to return
`None` as the first argument, wrap it in a `tuple` or use 
`aiowamp.InvocationResult`.

Any other value is used as the first and only argument:

    async def my_procedure():
        return {"hello": "world", "world": "hello"}
        # equal to: aiowamp.InvocationResult({"hello": "world", "world": "hello"})


The only way to set keyword arguments is to use `aiowamp.InvocationResult` 
explicitly!
"""

InvocationHandler = Callable[[InvocationABC],
                             Union[MaybeAwaitable[InvocationHandlerResult],
                                   AsyncGenerator[InvocationHandlerResult, None]]]

SubscriptionHandler = Callable[[aiowamp.msg.Event], MaybeAwaitable[Any]]


class ClientABC(abc.ABC):
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {id(self):x}"

    @abc.abstractmethod
    async def close(self, details: aiowamp.WAMPDict = None, *,
                    uri: str = None) -> None:
        ...

    @abc.abstractmethod
    async def register(self, procedure: str, handler: aiowamp.InvocationHandler, *,
                       disclose_caller: bool = None,
                       match_policy: aiowamp.MatchPolicy = None,
                       invocation_policy: aiowamp.InvocationPolicy = None,
                       options: aiowamp.WAMPDict = None) -> None:
        ...

    @abc.abstractmethod
    def call(self, procedure: str, *args: aiowamp.WAMPType,
             kwargs: aiowamp.WAMPDict = None,
             cancel_mode: aiowamp.CancelMode = None,
             call_timeout: float = None,
             disclose_me: bool = None,
             options: aiowamp.WAMPDict = None) -> aiowamp.CallABC:
        ...

    @abc.abstractmethod
    async def subscribe(self, topic: str, callback: aiowamp.SubscriptionHandler, *,
                        match_policy: aiowamp.MatchPolicy = None,
                        options: aiowamp.WAMPDict = None) -> None:
        ...

    @abc.abstractmethod
    async def unsubscribe(self, topic: str) -> None:
        ...

    @abc.abstractmethod
    async def publish(self, topic: str, *args: aiowamp.WAMPType,
                      kwargs: aiowamp.WAMPDict = None,
                      acknowledge: bool = True,
                      # TODO blackwhitelisting
                      exclude_me: bool = None,
                      disclose_me: bool = None,
                      options: aiowamp.WAMPDict = None) -> None:
        ...
