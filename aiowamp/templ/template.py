import asyncio
import inspect
import urllib.parse as urlparse
from typing import Any, Awaitable, Callable, Iterable, List, Optional, Tuple, TypeVar, Union

import aiowamp
from .handler import Handler, create_registration_handler, create_subscription_handler, get_handlers, \
    set_registration_handler, set_subscription_handler

__all__ = ["Template",
           "procedure", "event",
           "apply_template"]

FuncT = TypeVar("FuncT", bound=Callable)
NoOpDecorator = Callable[[FuncT], FuncT]


def build_options(options: Optional[aiowamp.WAMPDict], **kwargs: Optional[aiowamp.WAMPType]) \
        -> Optional[aiowamp.WAMPDict]:
    for key, value in kwargs.items():
        if value is None:
            continue

        if options is None:
            options = {}

        options[key] = value

    return options


class Template:
    __slots__ = ("_uri_prefix",
                 "__registrations", "__subscriptions")

    _uri_prefix: Optional[str]

    __registrations: List[Handler]
    __subscriptions: List[Handler]

    def __init__(self, *, uri_prefix: str = None) -> None:
        self.__registrations = []
        self.__subscriptions = []

        self._uri_prefix = uri_prefix if uri_prefix else None

    def _get_registration_handlers(self, uri: str) -> Tuple[Handler, ...]:
        return tuple(handler for handler in self.__registrations if handler.uri == uri)

    def procedure(self, uri: str = None, *,
                  disclose_caller: bool = None,
                  match_policy: aiowamp.MatchPolicy = None,
                  invocation_policy: aiowamp.InvocationPolicy = None,
                  options: aiowamp.WAMPDict = None) -> NoOpDecorator:
        options = build_options(options,
                                disclose_caller=disclose_caller,
                                match_policy=match_policy,
                                invocation_policy=invocation_policy)

        if uri is not None:
            existing_handlers = self._get_registration_handlers(uri)
            # TODO make sure handler is set to allow multiple registrations for the same URI
            #      automatically set them and raise an error if the values are explicitly disabled.

        def decorator(fn):
            handler = create_registration_handler(uri, fn, options)
            self.__registrations.append(handler)
            return fn

        return decorator

    def event(self, uri: str, *,
              match_policy: aiowamp.MatchPolicy = None,
              options: aiowamp.WAMPDict = None) -> NoOpDecorator:
        options = build_options(options,
                                match_policy=match_policy)

        def decorator(fn):
            handler = create_subscription_handler(uri, fn, options)
            self.__registrations.append(handler)
            return fn

        return decorator

    async def apply(self, client: aiowamp.ClientABC) -> None:
        await _apply_handlers(client, self.__registrations, self.__subscriptions,
                              uri_prefix=self._uri_prefix)

    async def create_client(self, url: Union[str, urlparse.ParseResult], *,
                            realm: str,
                            serializer: aiowamp.SerializerABC = None,
                            keyring: aiowamp.AuthKeyringABC = None) -> aiowamp.Client:
        client = await aiowamp.connect(url,
                                       realm=realm,
                                       serializer=serializer,
                                       keyring=keyring)
        await self.apply(client)

        return client


def procedure(uri: str = None, *,
              disclose_caller: bool = None,
              match_policy: aiowamp.MatchPolicy = None,
              invocation_policy: aiowamp.InvocationPolicy = None,
              options: aiowamp.WAMPDict = None) -> NoOpDecorator:
    options = build_options(options,
                            disclose_caller=disclose_caller,
                            match_policy=match_policy,
                            invocation_policy=invocation_policy)

    def decorator(fn):
        handler = create_registration_handler(uri, fn, options)
        set_registration_handler(fn, handler)

        return fn

    return decorator


def event(uri: str, *,
          match_policy: aiowamp.MatchPolicy = None,
          options: aiowamp.WAMPDict = None) -> NoOpDecorator:
    options = build_options(options,
                            match_policy=match_policy)

    def decorator(fn):
        handler = create_subscription_handler(uri, fn, options)
        set_subscription_handler(fn, handler)

        return fn

    return decorator


def __apply_registrations(client: aiowamp.ClientABC, handlers: Iterable[Handler], *,
                          uri_prefix: str = None) -> Iterable[Awaitable]:
    return (client.register(handler.uri_with_prefix(uri_prefix), handler.entry_point, options=handler.options)
            for handler in handlers)


def __apply_subscriptions(client: aiowamp.ClientABC, handlers: Iterable[Handler]) -> Iterable[Awaitable]:
    return (client.subscribe(handler.uri, handler.entry_point, options=handler.options)
            for handler in handlers)


async def _apply_handlers(client: aiowamp.ClientABC, registrations: Iterable[Handler],
                          subscriptions: Iterable[Handler], *,
                          uri_prefix: str = None) -> None:
    await asyncio.gather(*__apply_registrations(client, registrations, uri_prefix=uri_prefix),
                         *__apply_subscriptions(client, subscriptions))


async def apply_template(template: Any, client: aiowamp.ClientABC, *,
                         uri_prefix: str = None) -> None:
    if isinstance(template, Template):
        await template.apply(client)
        return

    registrations = []
    subscriptions = []

    for _, value in inspect.getmembers(template, inspect.ismethod):
        reg, sub = get_handlers(value)
        if reg is not None:
            registrations.append(reg)

        if sub is not None:
            subscriptions.append(sub)

    if not (registrations or subscriptions):
        raise TypeError(f"{template!r} doesn't have any procedures or event listeners")

    await _apply_handlers(client, registrations, subscriptions, uri_prefix=uri_prefix)
