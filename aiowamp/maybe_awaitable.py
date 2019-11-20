import asyncio
import inspect
import logging
from typing import Awaitable, Callable, TypeVar, Union

__all__ = ["MaybeAwaitable",
           "call_async_fn", "call_async_fn_background"]

log = logging.getLogger(__name__)

T = TypeVar("T")

MaybeAwaitable = Union[T, Awaitable[T]]
"""Either a concrete object or an awaitable."""


async def call_async_fn(f: Callable[..., MaybeAwaitable[T]], *args, **kwargs) -> T:
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


def call_async_fn_background(f: Callable[..., MaybeAwaitable[T]], msg: str, *args, **kwargs) -> None:
    async def wrapper():
        try:
            await call_async_fn(f, *args, **kwargs)
        except Exception:
            log.exception(msg)

    asyncio.create_task(wrapper())
