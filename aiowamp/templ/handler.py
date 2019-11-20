import dataclasses
import inspect
import types
import warnings
from typing import Any, Awaitable, Callable, List, Optional, Tuple, TypeVar

import aiowamp
from aiowamp import URI
from aiowamp.args_mixin import ArgsMixin
from .entry_point import EventEntryPoint, ProcedureEntryPoint

__all__ = ["Handler",
           "get_registration_handler", "set_registration_handler",
           "get_subscription_handler", "set_subscription_handler",
           "get_handlers", "get_handlers_in_instance",
           "create_procedure_uri",
           "create_invocation_entry_point", "create_registration_handler",
           "create_subscription_entry_point", "create_subscription_handler"]

T = TypeVar("T")


def ensure_callable(fn: Callable) -> Callable:
    """Make sure the given object is callable.


    Args:
        fn: Function to check. May be a method descriptor,
        in which case a warning is issued.

    Returns:
        Callable function.

    Raises:
        TypeError: If the given function is not callable.
    """
    if inspect.ismethoddescriptor(fn):
        if hasattr(fn, "__func__"):
            fn = fn.__func__
            warnings.warn("decorated a method descriptor. If you are using "
                          "@classmethod or @staticmethod, make sure they are applied last!",
                          SyntaxWarning, stacklevel=4)
        else:
            raise TypeError(f"received method descriptor {fn} instead of callable."
                            f"If you are using other decorators, "
                            f"try applying them after this one.")

    if callable(fn) and hasattr(fn, "__name__"):
        return fn
    else:
        raise TypeError(f"unexpected type {type(fn).__qualname__}. "
                        f"Excepted a callable object.")


def full_qualname(o: object) -> str:
    """Get the fully qualified name of the object.

    Args:
        o: Object to get name for.

    Returns:
        For normal object this returns <module name>.<qualified object name>.
        If that raises an `AttributeError`, the default representation is
        returned instead.
    """
    try:
        return f"{o.__module__}.{o.__qualname__}"
    except AttributeError:
        return repr(o)


@dataclasses.dataclass()
class Handler:
    uri: str
    """URI for the wrapped function."""
    options: Optional[aiowamp.WAMPDict]
    """Options to be passed to the registration/subscription."""
    wrapped: Callable
    """Wrapped function."""
    entry_point_factory: Callable
    """Callable which generates the entry point for the wrapped function."""

    _entry_point: Callable[[ArgsMixin], Awaitable[None]] = dataclasses.field(init=False, repr=False, compare=False)

    def __str__(self) -> str:
        return f"<function {full_qualname(self.wrapped)} uri={self.uri}>"

    def uri_with_prefix(self, prefix: str = None) -> str:
        """Return the uri with the given prefix.

        Args:
            prefix: Prefix or `None` if no prefix is to be used.

        Returns:
            URI prefixed with the prefix, unless the prefix is `None`, in which
            case the uri is returned directly.

            The return value will be an instance of `aiowamp.URI` with a match
            policy if the URI or the prefix is a uri with a match policy.
        """
        if prefix is None:
            return self.uri

        uri = self.uri

        if isinstance(uri, URI):
            match_policy = uri.match_policy
        else:
            match_policy = None

        if match_policy is None and isinstance(prefix, URI):
            match_policy = prefix.match_policy

        uri = prefix + self.uri
        if match_policy is not None:
            return URI(uri, match_policy=match_policy)

        return uri

    def get_option(self, key: str) -> Optional[aiowamp.WAMPType]:
        """Get the value of the option with the given key.

        Args:
            key: Key to get value for.

        Returns:
            Value of the given key or `None` if the key either doesn't exist, or
            no options are specified.
        """
        try:
            return self.options[key]
        except (TypeError, KeyError):
            return None

    def set_option(self, key: str, value: aiowamp.WAMPType) -> None:
        """Set the option key to the given value.

        If options doesn't exist, it is created by this function.

        Args:
            key: Key to set value to.
            value: Value to set.
        """
        if self.options is None:
            self.options = {key: value}
            return

        self.options[key] = value

    def get_entry_point(self) -> Callable[[ArgsMixin], Awaitable[None]]:
        """Get the entry point function.

        The function is only generated once.

        Returns:
            The generated entry point function.
        """
        try:
            return self._entry_point
        except AttributeError:
            self._entry_point = entry = self.entry_point_factory(self.wrapped)
            return entry

    def with_wrapped(self: T, new: Callable) -> T:
        """Create a new handler wrapping the given callable.

        Args:
            new: Callable to replace the wrapped with.

        Returns:
            A shallow copy of the handler wrapping the new function.
            The same handler is returned if the new wrapped is the same as the
            current one.
        """
        new = ensure_callable(new)
        if self.wrapped is new:
            return self

        return dataclasses.replace(self, wrapped=new)


REGISTRATION_HANDLER_ATTR = "__registration_handler__"
"""Name of the attribute that holds registration handlers."""


def get_registration_handler(fn: Callable) -> Optional[Handler]:
    """Get the registration handler for the function.

    Args:
        fn: Function to get handler from.

    Returns:
        Attached handler or `None`
    """
    return getattr(ensure_callable(fn), REGISTRATION_HANDLER_ATTR, None)


def set_registration_handler(fn: Callable, handler: Handler) -> None:
    """Attach the registration handler to the function."""
    fn = ensure_callable(fn)

    _ensure_no_handlers(fn)
    setattr(fn, REGISTRATION_HANDLER_ATTR, handler)


SUBSCRIPTION_HANDLER_ATTR = "__subscription_handler__"
"""Name of the attribute that holds subscription handlers."""


def get_subscription_handler(fn: Callable) -> Optional[Handler]:
    """Get the subscription handler attached to the function."""
    return getattr(ensure_callable(fn), SUBSCRIPTION_HANDLER_ATTR, None)


def set_subscription_handler(fn: Callable, handler: Handler) -> None:
    """Attach the subscription handler to the function."""
    fn = ensure_callable(fn)

    _ensure_no_handlers(fn)
    setattr(fn, SUBSCRIPTION_HANDLER_ATTR, handler)


def get_handlers(fn: Callable) -> Tuple[Optional[Handler], Optional[Handler]]:
    """Get both handlers from the function.

    Args:
        fn: Function to get handlers from.

    Returns:
        2-tuple with the registration handler and the subscription handler
        (in that order).
        Either (or even both) may be `None` if no handler is attached.
    """
    return get_registration_handler(fn), get_subscription_handler(fn)


def get_bound_handlers(fn: types.MethodType) -> Tuple[Optional[Handler], Optional[Handler]]:
    """Get the handlers for the given method.

    This works just like `get_handlers` but it doesn't necessarily return the
    attached handlers. Instead, it returns the handlers wrapping the bound method.

    Args:
        fn: Method to get handlers from.

    Returns:
        2-tuple containing the handlers or `None`.
    """
    reg, sub = get_handlers(fn.__func__)
    if reg:
        reg = reg.with_wrapped(fn)
    if sub:
        sub = sub.with_wrapped(fn)

    return reg, sub


def get_handlers_in_instance(inst: Any) -> Tuple[List[Handler], List[Handler]]:
    """Get all handlers from the members of an instance.

    Args:
        inst: Instance to get handlers from.

    Returns:
        2-tuple containing the list of all registration and all subscription
        handlers.

    Raises:
        TypeError: If inst isn't an instance.
    """
    if inspect.isclass(inst):
        raise TypeError("expected instance, not class. "
                        "Please create an instance of your template class first")

    registrations = []
    subscriptions = []

    for _, value in inspect.getmembers(inst, callable):
        if inspect.ismethod(value):
            reg, sub = get_bound_handlers(value)
        else:
            reg, sub = get_handlers(value)

        if reg is not None:
            registrations.append(reg)

        if sub is not None:
            subscriptions.append(sub)

    return registrations, subscriptions


def _ensure_no_handlers(fn: Callable):
    """Make sure the function doesn't have any handlers already."""
    inv_handler = get_registration_handler(fn)
    if inv_handler:
        raise ValueError(f"{full_qualname(fn)} is already registered as a procedure {inv_handler.uri}")

    sub_handler = get_subscription_handler(fn)
    if sub_handler:
        raise ValueError(f"{full_qualname(fn)} is already registered as an event handler for {sub_handler.uri}")


def create_invocation_entry_point(fn: Callable) -> aiowamp.InvocationHandler:
    """Create an invocation handler for the given callable.

    Args:
        fn: Function to generate invocation handler for.

    Returns:
        A wrapper which acts like an entry point for the given function.
        It gets all arguments requested by the function's signature from the
        invocation and calls it.
    """
    return ProcedureEntryPoint.from_fn(fn).exec()


def create_procedure_uri(fn: Callable) -> str:
    """Generate a uri for the function."""
    fn = ensure_callable(fn)
    return fn.__name__.lower()


def create_registration_handler(uri: str, fn: Callable, options: Optional[aiowamp.WAMPDict]) -> Handler:
    """Create a new registration handler for the given function."""
    return Handler(uri, options, ensure_callable(fn), create_invocation_entry_point)


def create_subscription_entry_point(fn: Callable) -> aiowamp.SubscriptionHandler:
    """Create subscription handler for the given callable.

    Args:
        fn: Function to generate subscription handler for.

    Returns:
        A wrapper which acts like an entry point for the given function.
        It gets all arguments requested by the function's signature from the
        subscription event and calls it.
    """
    return EventEntryPoint.from_fn(fn).exec()


def create_subscription_handler(uri: str, fn: Callable, options: Optional[aiowamp.WAMPDict]) -> Handler:
    """Create a new subscription handler for the given function."""
    return Handler(uri, options, ensure_callable(fn), create_subscription_entry_point)
