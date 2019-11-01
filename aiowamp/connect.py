from __future__ import annotations

import urllib.parse as urlparse
from typing import Callable, TypeVar, Union, overload

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

    msg = aiowamp.message_as_type(msg, aiowamp.msg.Welcome)
    if not msg:
        raise aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Welcome)

    return aiowamp.Session(transport, msg.session_id, realm, msg.details)


ClientT = TypeVar("ClientT", bound=aiowamp.ClientABC)
ClientFactory = Callable[[aiowamp.SessionABC], ClientT]


async def connect(url: Union[str, urlparse.ParseResult], *,
                  realm: str,
                  serializer: aiowamp.SerializerABC = None,
                  ) -> aiowamp.Client:
    if not isinstance(url, urlparse.ParseResult):
        url: urlparse.ParseResult = urlparse.urlparse(url)

    details = {
        "roles": aiowamp.client.CLIENT_ROLES,
    }

    transport = await aiowamp.connect_transport(aiowamp.CommonTransportConfig(
        url,
        serializer=serializer,
    ))

    session = await join_realm(transport, realm, details)
    return aiowamp.Client(session)
