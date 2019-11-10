from __future__ import annotations

import logging
import urllib.parse as urlparse
from typing import Iterable, Union

import aiowamp

__all__ = ["KeyringType",
           "connect", "join_realm"]

log = logging.getLogger(__name__)

KeyringType = Union[aiowamp.AuthKeyringABC, Iterable[aiowamp.AuthMethodABC]]


async def _authenticate(transport: aiowamp.TransportABC, challenge: aiowamp.msg.Challenge, *,
                        keyring: aiowamp.AuthKeyringABC) -> None:
    # TODO handle KeyError
    method = keyring[challenge.auth_method]
    auth = await method.authenticate(challenge)
    await transport.send(auth)


async def join_realm(transport: aiowamp.TransportABC, realm: str, *,
                     keyring: KeyringType = None,
                     roles: aiowamp.WAMPDict = None,
                     details: aiowamp.WAMPDict = None) -> aiowamp.Session:
    if keyring is not None:
        keyring = _get_keyring(keyring)

    details = details or {}
    if keyring:
        log.debug("using %s", keyring)
        details["authmethods"] = list(keyring)
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

        await _authenticate(transport, challenge, keyring=keyring)
        msg = await transport.recv()

    welcome = aiowamp.message_as_type(msg, aiowamp.msg.Welcome)
    if not welcome:
        raise aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Welcome)

    return aiowamp.Session(transport, welcome.session_id, realm, welcome.details)


async def connect(url: Union[str, urlparse.ParseResult], *,
                  realm: str,
                  serializer: aiowamp.SerializerABC = None,
                  keyring: KeyringType = None) -> aiowamp.Client:
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


def _get_keyring(keyring: KeyringType) -> aiowamp.AuthKeyringABC:
    if isinstance(keyring, aiowamp.AuthKeyringABC):
        return keyring

    return aiowamp.AuthKeyring(*keyring)
