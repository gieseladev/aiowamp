from __future__ import annotations

import logging
import urllib.parse as urlparse
from typing import Union

import aiowamp

__all__ = ["connect", "join_realm"]

log = logging.getLogger(__name__)


# TODO raise aborterror for ABORT instead of unexpected message.

async def _authenticate(transport: aiowamp.TransportABC, challenge: aiowamp.msg.Challenge, *,
                        keyring: aiowamp.AuthKeyringABC) -> aiowamp.msg.Welcome:
    # TODO handle KeyError
    method = keyring[challenge.auth_method]
    auth = await method.authenticate(challenge)
    await transport.send(auth)

    msg = await transport.recv()

    welcome = aiowamp.message_as_type(msg, aiowamp.msg.Welcome)
    if not welcome:
        raise aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Welcome)

    # TODO SCRAM wants to analyze the welcome, so need another method

    return welcome


async def join_realm(transport: aiowamp.TransportABC, realm: str, *,
                     keyring: aiowamp.AuthKeyringABC = None,
                     roles: aiowamp.WAMPDict = None,
                     details: aiowamp.WAMPDict = None) -> aiowamp.Session:
    details = details or {}
    if keyring:
        log.debug("using %s", keyring)
        details["authmethods"] = list(keyring)

        auth_id = keyring.auth_id
        if auth_id is not None:
            details["authid"] = auth_id

        auth_extra = keyring.auth_extra
        if auth_extra is not None:
            details["authextra"] = auth_extra

    if roles is not None:
        details["roles"] = roles

    await transport.send(aiowamp.msg.Hello(
        aiowamp.URI(realm),
        details,
    ))

    msg = await transport.recv()

    challenge = aiowamp.message_as_type(msg, aiowamp.msg.Challenge)
    if challenge:
        if not keyring:
            # TODO raise auth error
            raise aiowamp.Error

        welcome = await _authenticate(transport, challenge, keyring=keyring)
    else:
        welcome = aiowamp.message_as_type(msg, aiowamp.msg.Welcome)
        if not welcome:
            raise aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Welcome)

    return aiowamp.Session(transport, welcome.session_id, realm, welcome.details)


async def connect(url: Union[str, urlparse.ParseResult], *,
                  realm: str,
                  serializer: aiowamp.SerializerABC = None,
                  keyring: aiowamp.AuthKeyringABC = None) -> aiowamp.Client:
    if not isinstance(url, urlparse.ParseResult):
        url = urlparse.urlparse(url)

    log.info("connecting to %s", url)
    transport = await aiowamp.connect_transport(aiowamp.CommonTransportConfig(
        url,
        serializer=serializer,
    ))

    log.info("joining realm %s", realm)
    session = await join_realm(transport, realm,
                               keyring=keyring,
                               roles=aiowamp.CLIENT_ROLES)
    return aiowamp.Client(session)
