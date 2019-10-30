from __future__ import annotations

import urllib.parse
from typing import Callable, TypeVar, Union, overload

import aiowamp

__all__ = ["join_realm", "create_client_session", "connect"]


async def join_realm(transport: aiowamp.TransportABC, realm: str,
                     details: aiowamp.WAMPDict) -> aiowamp.msg.Welcome:
    await transport.send(aiowamp.msg.Hello(
        aiowamp.URI(realm),
        details,
    ))

    msg = await transport.recv()

    # TODO challenge

    msg = aiowamp.message_as_type(msg, aiowamp.msg.Welcome)
    if not msg:
        raise aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Welcome)

    return msg


SessionT = TypeVar("SessionT", bound=aiowamp.SessionABC)
SessionFactory = Callable[[str, aiowamp.msg.Welcome], SessionT]


@overload
async def create_client_session(transport: aiowamp.TransportABC, realm: str) -> aiowamp.Session: ...


@overload
async def create_client_session(transport: aiowamp.TransportABC, realm: str, *,
                                session_factory: SessionFactory) -> SessionT: ...


async def create_client_session(transport: aiowamp.TransportABC, realm: str, *,
                                session_factory: SessionFactory = aiowamp.Session) -> SessionT:
    welcome = await join_realm(transport, realm, {})
    return session_factory(realm, welcome)


ClientT = TypeVar("ClientT", bound=aiowamp.ClientABC)
ClientFactory = Callable[[aiowamp.SessionABC], ClientT]


@overload
async def connect(url: Union[str, urllib.parse.ParseResult], *,
                  session_factory: SessionFactory = None,
                  ) -> aiowamp.Client: ...


@overload
async def connect(url: Union[str, urllib.parse.ParseResult], *,
                  session_factory: SessionFactory = None,
                  client_factory: ClientFactory,
                  ) -> ClientT: ...


async def connect(url: Union[str, urllib.parse.ParseResult], *,
                  session_factory: SessionFactory = aiowamp.Session,
                  client_factory: ClientFactory = aiowamp.Client,
                  ) -> ClientT:
    if not isinstance(url, urllib.parse.ParseResult):
        url = urllib.parse.urlparse(url)

    realm = ""
    details = {}
    transport = aiowamp.TransportABC()

    session = await create_client_session(transport, realm, session_factory=session_factory)
    return client_factory(session)
