import asyncio
import types
import urllib.parse as urlparse
from typing import Any, Awaitable, Callable, Iterable, List, Optional, TypeVar, Union

import aiowamp
from .handler import Handler, create_registration_handler, create_subscription_handler, get_handlers_in_instance, \
    set_registration_handler, set_subscription_handler

__all__ = ["Template",
           "procedure", "event",
           "apply_template"]

FuncT = TypeVar("FuncT", bound=Union[Callable, types.MethodDescriptorType])
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

    def _iter_registration_handlers(self, uri: str) -> Iterable[Handler]:
        return (handler for handler in self.__registrations if handler.uri == uri)

    def __assert_invocation_policy(self, uri: str, policy: aiowamp.InvocationPolicy = None) \
            -> Optional[aiowamp.InvocationPolicy]:
        handlers = tuple(self._iter_registration_handlers(uri))
        if not handlers:
            return policy

        if policy is aiowamp.INVOKE_SINGLE:
            raise TypeError(f"there are multiple procedures for the uri {uri}. "
                            f"Invocation policy must something other than {aiowamp.INVOKE_SINGLE!r}")

        policies = tuple(handler.get_option("invoke")
                         for handler in handlers)

        if aiowamp.INVOKE_SINGLE in policies:
            raise ValueError(f"procedure with uri {uri} already exists and "
                             f"explicitly uses invocation policy {aiowamp.INVOKE_SINGLE!r}")

        if policy is None:
            policy = aiowamp.INVOKE_ROUND_ROBIN

        for handler, h_policy in zip(handlers, policy):
            if h_policy is None:
                handler.set_option("invoke", policy)

        return policy

    def procedure(self, uri: str = None, *,
                  disclose_caller: bool = None,
                  match_policy: aiowamp.MatchPolicy = None,
                  invocation_policy: aiowamp.InvocationPolicy = None,
                  options: aiowamp.WAMPDict = None) -> NoOpDecorator:
        if uri is not None:
            invocation_policy = self.__assert_invocation_policy(uri, invocation_policy or options.get("invoke"))

        options = build_options(options,
                                disclose_caller=disclose_caller,
                                match=match_policy,
                                invoke=invocation_policy)

        def decorator(fn):
            handler = create_registration_handler(uri, fn, options)
            self.__registrations.append(handler)
            return fn

        return decorator

    def event(self, uri: str, *,
              match_policy: aiowamp.MatchPolicy = None,
              options: aiowamp.WAMPDict = None) -> NoOpDecorator:
        options = build_options(options,
                                match=match_policy)

        def decorator(fn):
            handler = create_subscription_handler(uri, fn, options)
            self.__subscriptions.append(handler)
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
                            match=match_policy,
                            invoke=invocation_policy)

    def decorator(fn):
        handler = create_registration_handler(uri, fn, options)
        set_registration_handler(fn, handler)

        return fn

    return decorator


def event(uri: str, *,
          match_policy: aiowamp.MatchPolicy = None,
          options: aiowamp.WAMPDict = None) -> NoOpDecorator:
    options = build_options(options,
                            match=match_policy)

    def decorator(fn):
        handler = create_subscription_handler(uri, fn, options)
        set_subscription_handler(fn, handler)

        return fn

    return decorator


def __apply_registrations(client: aiowamp.ClientABC, handlers: Iterable[Handler], *,
                          uri_prefix: str = None) -> Iterable[Awaitable]:
    return (client.register(handler.uri_with_prefix(uri_prefix), handler.get_entry_point(), options=handler.options)
            for handler in handlers)


def __apply_subscriptions(client: aiowamp.ClientABC, handlers: Iterable[Handler]) -> Iterable[Awaitable]:
    return (client.subscribe(handler.uri, handler.get_entry_point(), options=handler.options)
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

    registrations, subscriptions = get_handlers_in_instance(template)

    await _apply_handlers(client, registrations, subscriptions, uri_prefix=uri_prefix)
