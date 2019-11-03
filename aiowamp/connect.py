from __future__ import annotations

import urllib.parse as urlparse
from typing import Callable, TypeVar, Union

import aiowamp

__all__ = ["join_realm", "connect"]

SessionT = TypeVar("SessionT", bound=aiowamp.SessionABC)
SessionFactory = Callable[[str, aiowamp.msg.Welcome], SessionT]


async def join_realm(transport: aiowamp.TransportABC, realm: str, details: aiowamp.WAMPDict) -> aiowamp.Session:
    await transport.send(aiowamp.msg.Hello(
        aiowamp.URI(realm),
        details,
    ))

    msg = await transport.recv()

    # TODO challenge

    welcome = aiowamp.message_as_type(msg, aiowamp.msg.Welcome)
    if not welcome:
        raise aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Welcome)

    return aiowamp.Session(transport, welcome.session_id, realm, welcome.details)


ClientT = TypeVar("ClientT", bound=aiowamp.ClientABC)
ClientFactory = Callable[[aiowamp.SessionABC], ClientT]


async def connect(url: Union[str, urlparse.ParseResult], *,
                  realm: str,
                  serializer: aiowamp.SerializerABC = None,
                  ) -> aiowamp.Client:
    if not isinstance(url, urlparse.ParseResult):
        url = urlparse.urlparse(url)

    details = {
        "roles": aiowamp.client.CLIENT_ROLES,
    }

    transport = await aiowamp.connect_transport(aiowamp.CommonTransportConfig(
        url,
        serializer=serializer,
    ))

    session = await join_realm(transport, realm, details)
    return aiowamp.Client(session)
