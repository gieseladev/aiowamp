import abc
import dataclasses
import ssl
import urllib.parse as urlparse
from typing import Awaitable, Callable, Dict, Optional

import aiowamp.message

__all__ = ["TransportABC",
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


@dataclasses.dataclass()
class CommonTransportConfig:
    url: urlparse.ParseResult
    serializer: Optional[aiowamp.SerializerABC] = None
    ssl_context: Optional[ssl.SSLContext] = None


TransportFactory = Callable[[CommonTransportConfig], Awaitable[TransportABC]]

SCHEME_TRANSPORT_MAP: Dict[str, TransportFactory] = {}


def register_transport_factory(*schemes: str, overwrite: bool = False):
    def decorator(fn: TransportFactory):
        for scheme in schemes:
            if not overwrite and scheme in SCHEME_TRANSPORT_MAP:
                raise ValueError(f"cannot register scheme {scheme!r} for {fn!r}. "
                                 f"Already registered by {SCHEME_TRANSPORT_MAP[scheme]}")

            SCHEME_TRANSPORT_MAP[scheme] = fn

        return fn

    return decorator


def get_transport_factory(scheme: str) -> TransportFactory:
    try:
        return SCHEME_TRANSPORT_MAP[scheme]
    except KeyError:
        raise KeyError(f"no transport registered for scheme {scheme!r}") from None


async def connect_transport(config: CommonTransportConfig) -> TransportABC:
    connect = get_transport_factory(config.url.scheme)
    return await connect(config)
