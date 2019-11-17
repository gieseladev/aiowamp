import dataclasses
from typing import Any, Callable, Optional, Tuple

import aiowamp

__all__ = ["Handler",
           "get_registration_handler", "set_registration_handler",
           "get_subscription_handler", "set_subscription_handler",
           "get_handlers",
           "create_registration_entry_point", "create_registration_handler",
           "create_subscription_entry_point", "create_subscription_handler"]


def full_qualname(o: object) -> str:
    return f"{o.__module__}.{o.__qualname__}"


@dataclasses.dataclass()
class Handler:
    uri: aiowamp.URI
    wrapped: Callable
    entry_point: Any

    options: Optional[aiowamp.WAMPDict]

    def __str__(self) -> str:
        return f"<function {full_qualname(self.wrapped)} uri={self.uri}>"

    def uri_with_prefix(self, prefix: str = None) -> str:
        if prefix is None:
            return self.uri

        return prefix + self.uri


REGISTRATION_HANDLER_ATTR = "__registration_handler__"


def get_registration_handler(fn: Callable) -> Optional[Handler]:
    return getattr(fn, REGISTRATION_HANDLER_ATTR, None)


def set_registration_handler(fn: Callable, handler: Handler) -> None:
    _ensure_no_handlers(fn)
    setattr(fn, REGISTRATION_HANDLER_ATTR, handler)


SUBSCRIPTION_HANDLER_ATTR = "__subscription_handler__"


def get_subscription_handler(fn: Callable) -> Optional[Handler]:
    return getattr(fn, SUBSCRIPTION_HANDLER_ATTR, None)


def set_subscription_handler(fn: Callable, handler: Handler) -> None:
    _ensure_no_handlers(fn)
    setattr(fn, SUBSCRIPTION_HANDLER_ATTR, handler)


def get_handlers(fn: Callable) -> Tuple[Optional[Handler], Optional[Handler]]:
    return get_registration_handler(fn), get_subscription_handler(fn)


def _ensure_no_handlers(fn: Callable):
    """Make sure the function isn't registered already."""
    inv_handler = get_registration_handler(fn)
    if inv_handler:
        raise ValueError(f"{full_qualname(fn)} is already registered as a procedure {inv_handler.uri}")

    sub_handler = get_subscription_handler(fn)
    if sub_handler:
        raise ValueError(f"{full_qualname(fn)} is already registered as an event handler for {sub_handler.uri}")


def create_registration_entry_point(fn: Callable) -> aiowamp.InvocationHandler:
    return fn


def create_registration_handler(uri: Optional[str], fn: Callable, options: Optional[aiowamp.WAMPDict]) -> Handler:
    if uri is not None:
        uri = aiowamp.URI.as_uri(uri)
    else:
        uri = fn.__name__.lower()

    entry = create_registration_entry_point(fn)
    return Handler(uri, fn, entry, options)


def create_subscription_entry_point(fn: Callable) -> aiowamp.SubscriptionHandler:
    return fn


def create_subscription_handler(uri: str, fn: Callable, options: Optional[aiowamp.WAMPDict]) -> Handler:
    entry = create_subscription_entry_point(fn)
    return Handler(aiowamp.URI.as_uri(uri), fn, entry, options)
