from __future__ import annotations

import abc
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping, Optional, Tuple, TypeVar, Union

import aiowamp

__all__ = ["ClientABC", "CallABC",
           "InvocationABC", "InvocationHandler", "InvocationHandlerResult", "InvocationResult",
           "SubscriptionHandler",
           "MaybeAwaitable"]

T = TypeVar("T")
MaybeAwaitable = Union[T, Awaitable[T]]
"""Either a concrete object or an awaitable."""


class InvocationResult:
    __slots__ = ("args", "kwargs")

    args: Tuple[aiowamp.WAMPType, ...]
    kwargs: Mapping[str, aiowamp.WAMPType]

    def __init__(self, *args: aiowamp.WAMPType, **kwargs: aiowamp.WAMPType) -> None:
        self.args = args
        self.kwargs = kwargs

    def __repr__(self) -> str:
        arg_str = ", ".join(map(repr, self.args))
        kwarg_str = ", ".join(f"{key} = {value!r}" for key, value in self.kwargs.items())
        if kwarg_str and arg_str:
            join_str = ", "
        else:
            join_str = ""

        return f"{type(self).__qualname__}({arg_str}{join_str}{kwarg_str})"


class InvocationABC(abc.ABC):
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

    def __getitem__(self, key: Union[int, str]) -> aiowamp.WAMPType:
        if isinstance(key, str):
            return self.kwargs[key]

        return self.args[key]

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


InvocationHandlerResult = Union[Tuple[aiowamp.WAMPType, ...], InvocationResult, aiowamp.WAMPType]
InvocationHandler = Callable[[InvocationABC],
                             Union[MaybeAwaitable[InvocationHandlerResult], AsyncIterator[InvocationHandlerResult]]]


# TODO on_progress event listener which suppresses the progress queue?
#       also maybe raise an error if this is done AFTER the call went out.
class CallABC(Awaitable[aiowamp.msg.Result], AsyncIterator[aiowamp.msg.Result], abc.ABC):
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
    async def result(self) -> aiowamp.msg.Result:
        ...

    @abc.abstractmethod
    async def next_progress(self) -> Optional[aiowamp.msg.Result]:
        ...

    @abc.abstractmethod
    async def cancel(self, cancel_mode: aiowamp.CancelMode = None, *,
                     options: aiowamp.WAMPDict = None) -> None:
        ...


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
    async def register(self, procedure: str, handler: InvocationHandler, *,
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
             options: aiowamp.WAMPDict = None) -> CallABC:
        ...

    @abc.abstractmethod
    async def subscribe(self, topic: str, callback: SubscriptionHandler, *,
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
