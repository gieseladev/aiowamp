from __future__ import annotations

import abc
import dataclasses
import ssl
import urllib.parse as urlparse
from typing import Awaitable, Callable, Dict, Optional

import aiowamp

__all__ = ["TransportABC",
           "SerializerABC",
           "CommonTransportConfig", "TransportFactory",
           "register_transport_factory",
           "get_transport_factory", "connect_transport"]


class TransportABC(abc.ABC):
    """Abstract transport type.

    A Transport connects two WAMP Peers and provides a channel over which WAMP
    messages for a WAMP Session can flow in both directions.

    WAMP can run over any Transport which is message-based, bidirectional,
    reliable and ordered.
    """
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {id(self):x}"

    @property
    @abc.abstractmethod
    def open(self) -> bool:
        """Whether the transport is open and usable."""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the transport."""
        ...

    @abc.abstractmethod
    async def send(self, msg: aiowamp.MessageABC) -> None:
        """Send a message.

        Args:
            msg: Message to send.
        """
        ...

    @abc.abstractmethod
    async def recv(self) -> aiowamp.MessageABC:
        """Receive a message.

        Returns:
            Received message.
        """
        ...


class SerializerABC(abc.ABC):
    """Serializer for messages.

    Normally an `aiowamp.TransportABC` keeps a serializer which it uses.

    Deliberately doesn't adhere to Python's dump / load interface because the
    objects in question are always `aiowamp.MessageABC` and the serialized
    format is always `bytes`.
    """
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {id(self):x}"

    @abc.abstractmethod
    def serialize(self, msg: aiowamp.MessageABC) -> bytes:
        """Serialise a message.

        Args:
            msg: Message to serialise.

        Returns:
            `bytes` representation of the message.

        Raises:
            Exception: If the message couldn't be serialised.
        """
        ...

    @abc.abstractmethod
    def deserialize(self, data: bytes) -> aiowamp.MessageABC:
        """Deserialise the `bytes` representation of a message.

        Args:
            data: `bytes` representation of a message.

        Returns:
            Deserialised message.

        Raises:
            aiowamp.InvalidMessage: If the deserialised data isn't a message.
            Exception: If the message couldn't be deserialised.
        """
        ...


@dataclasses.dataclass()
class CommonTransportConfig:
    """Transport configuration used by transport factories."""

    url: urlparse.ParseResult
    """URL to connect to."""

    serializer: Optional["aiowamp.SerializerABC"] = None
    """Serializer to use. 
    
    If `None` a sensible default will be used.
    """

    ssl_context: Optional[ssl.SSLContext] = None
    """SSL options.
    
    If `None`, TLS will still be used if the `.url` specifies a secure scheme 
    (ex: "wss").
    """


TransportFactory = Callable[[CommonTransportConfig], Awaitable[TransportABC]]
"""Callable creating a transport from a config."""

SCHEME_TRANSPORT_MAP: Dict[str, TransportFactory] = {}


def register_transport_factory(*schemes: str, overwrite: bool = False):
    """Decorator for registering transport factories.

    Registered transport factories can be retrieved by
    `aiowamp.get_transport_factory`.

    Args:
        *schemes: Schemes to register to the given transport factory.
        overwrite: Whether to overwrite existing registrations for a scheme.
            Defaults to `False`.

    Raises:
        ValueError: If a scheme is already registered to another factory and
            overwrite is `False`.
    """

    def decorator(fn: TransportFactory):
        for scheme in schemes:
            if not overwrite and scheme in SCHEME_TRANSPORT_MAP:
                raise ValueError(f"cannot register scheme {scheme!r} for {fn!r}. "
                                 f"Already registered by {SCHEME_TRANSPORT_MAP[scheme]!r}")

            SCHEME_TRANSPORT_MAP[scheme] = fn

        return fn

    return decorator


def get_transport_factory(scheme: str) -> TransportFactory:
    """Get the registered transport factory for the scheme.

    Args:
        scheme: URL scheme to get factory for.

    Returns:
        A transport factory callable.

    Raises:
        KeyError: If no transport is registered for the given scheme.
    """
    try:
        return SCHEME_TRANSPORT_MAP[scheme]
    except KeyError:
        raise KeyError(f"no transport registered for scheme {scheme!r}") from None


async def connect_transport(config: CommonTransportConfig) -> TransportABC:
    """Connect a transport based on the config.

    Args:
        config: Config to create the transport with.

    Returns:
        A connected transport.

    Raises:
        KeyError: If no transport factory could be found for the config's url.
        Exception: If the connection fails.

    Notes:
        Uses `aiowamp.get_transport_factory` to get the transport factory from
        which the transport is created.
    """
    connect = get_transport_factory(config.url.scheme)
    return await connect(config)
