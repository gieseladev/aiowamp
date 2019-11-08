from __future__ import annotations

import abc
from typing import Any, AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterator, Mapping, Optional, Sequence, \
    Tuple, TypeVar, Union, overload

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
    """Helper class which provides useful methods for types with args and kwargs.

    The args and kwargs attributes ARE NOT part of this class, they are expected
    to exist.
    """
    __slots__ = ()

    args: Sequence[aiowamp.WAMPType]
    kwargs: Mapping[str, aiowamp.WAMPType]

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
        If it's an integer it is treated as an index for the arguments.

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
"""Type of a progress handler function.

The function is called with the invocation progress instance.
If a progress handler returns an awaitable object, it is awaited.

The return value is ignored.
"""


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
"""Type of a procedure function.

Upon invocation, a procedure function will be called with an 
`aiowamp.InvocationABC` instance. This invocation can be used to get arguments 
and send results.

It's also possible to send results by returning them. As a rule of thumb, 
write the procedures the same as how you would write them without WAMP.

For example:

    async def my_procedure(invocation):
        # invocation objects implement a lot of utility methods. 
        a, b, c = invocation
        return sum(a, b, c)


As you can see, this procedure returns a single value (namely the sum of the 
first three arguments passed to the call). aiowamp interprets this as the first 
argument of the result. Different return values have different 
interpretations, but they should all work like you would expect them to. 
For more, please take a look at `aiowamp.InvocationHandlerResult`.


aiowamp also supports async generators, which can be used to send progress 
results:

    async def prog_results(invocation):
        final_n = invocation.get(0, 100)
        for i in range(final_n):
            yield i
        
        yield final_n

This rather useless procedure sends all numbers between 0 and the first 
argument, which defaults to 100 if not specified, as progress results.
The final iteration is then sent as the final result.

The above code has been written to make this point clear, but it would've worked
the same if we used `range(final_n + 1)` and removed the `yield final_n`.

IMPORTANT:
aiowamp doesn't know whether the async generator has yielded for the last time, 
as such, **all results wait for the next yield before being sent**. The first 
progress will be sent when the second yield statement is reached, the final 
result is sent when the async generator stops.
If this is an issue, **there are ways to get around it:**

An instance of `aiowamp.InvocationProgress` can be yielded which will cause the
progress to be sent immediately.
The WAMP protocol doesn't support progressive calls without a final result, if
the last yield of a procedure function is an instance of 
`aiowamp.InvocationProgress`, then an empty final result will be sent and a 
warning is issued.

Similarly, the semantics of `aiowamp.InvocationResult` are different in an 
async generator. When yielding an instance of `aiowamp.InvocationResult` it 
will be sent as the final result immediately.
This can be used to perform some actions after the result has been sent.
"""

SubscriptionHandler = Callable[[aiowamp.msg.Event], MaybeAwaitable[Any]]
"""Type of a subscription handler function.

The handler receives the `aiowamp.msg.Event` each time it is published.
When the handler returns an awaitable object, it is awaited.
The return value is ignored.
"""


class ClientABC(abc.ABC):
    """WAMP Client.

    Implements the publisher, subscriber, caller, and callee roles.
    """
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {id(self):x}"

    @abc.abstractmethod
    async def close(self, details: aiowamp.WAMPDict = None, *,
                    reason: str = None) -> None:
        """Close the client and the underlying session.

        Args:
            details: Additional details to send with the close message.
            reason: URI denoting the reason for closing.
                Defaults to `aiowamp.uri.CLOSE_NORMAL`.
        """
        ...

    @abc.abstractmethod
    async def register(self, procedure: str, handler: aiowamp.InvocationHandler, *,
                       disclose_caller: bool = None,
                       match_policy: aiowamp.MatchPolicy = None,
                       invocation_policy: aiowamp.InvocationPolicy = None,
                       options: aiowamp.WAMPDict = None) -> None:
        ...

    @abc.abstractmethod
    async def unregister(self, procedure: str) -> None:
        ...

    @abc.abstractmethod
    def call(self, procedure: str, *args: aiowamp.WAMPType,
             kwargs: aiowamp.WAMPDict = None,
             receive_progress: bool = None,
             call_timeout: float = None,
             cancel_mode: aiowamp.CancelMode = None,
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
        """Unsubscribe from the given topic.

        Args:
            topic: Topic URI to unsubscribe from.

        Raises:
            KeyError: If not subscribed to the topic.
        """
        ...

    @abc.abstractmethod
    async def publish(self, topic: str, *args: aiowamp.WAMPType,
                      kwargs: aiowamp.WAMPDict = None,
                      acknowledge: bool = True,
                      blackwhitelist: aiowamp.BlackWhiteList = None,
                      exclude_me: bool = None,
                      disclose_me: bool = None,
                      options: aiowamp.WAMPDict = None) -> None:
        ...
