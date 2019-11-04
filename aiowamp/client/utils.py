from __future__ import annotations

import inspect
from typing import Callable, Type, TypeVar

import aiowamp

__all__ = ["check_message_response", "call_async_fn"]


def check_message_response(msg: aiowamp.MessageABC, ok_type: Type[aiowamp.MessageABC]) -> None:
    ok = aiowamp.message_as_type(msg, ok_type)
    if ok:
        return

    error = aiowamp.message_as_type(msg, aiowamp.msg.Error)
    if error:
        raise aiowamp.ErrorResponse(error)

    raise aiowamp.UnexpectedMessageError(msg, ok_type)


T = TypeVar("T")


async def call_async_fn(f: Callable[..., aiowamp.MaybeAwaitable[T]], *args, **kwargs) -> T:
    """Call function and await result if awaitable.

    Args:
        f: Function to call.
        *args: Arguments to pass to the function.
        **kwargs: Keyword-arguments to pass to the function.

    Returns:
        The result of the function.
    """
    res = f(*args, **kwargs)
    if inspect.isawaitable(res):
        res = await res

    return res
