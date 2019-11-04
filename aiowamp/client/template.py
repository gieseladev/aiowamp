from typing import Any, Callable, TypeVar

import aiowamp

FuncT = TypeVar("FuncT", bound=Callable)
NoOpDecorator = Callable[[FuncT], FuncT]


def procedure(uri: str = None) -> NoOpDecorator:
    def decorator(fn):
        return fn

    return decorator


def event(uri: str) -> NoOpDecorator:
    def decorator(fn):
        return fn

    return decorator


async def apply_template(client: aiowamp.ClientABC, template: Any) -> None:
    pass
