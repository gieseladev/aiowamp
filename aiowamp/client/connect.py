from __future__ import annotations

import logging
import urllib.parse as urlparse
from typing import Union

import aiowamp

__all__ = ["connect", "join_realm"]

log = logging.getLogger(__name__)


def assert_welcome(msg: aiowamp.MessageABC) -> aiowamp.msg.Welcome:
    abort = aiowamp.message_as_type(msg, aiowamp.msg.Abort)
    if abort:
        raise aiowamp.AbortError(abort)

    welcome = aiowamp.message_as_type(msg, aiowamp.msg.Welcome)
    if not welcome:
        raise aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Welcome)

    return welcome


async def _authenticate(transport: aiowamp.TransportABC, challenge: aiowamp.msg.Challenge, *,
                        keyring: aiowamp.AuthKeyringABC) -> aiowamp.msg.Welcome:
    try:
        method = keyring[challenge.auth_method]
    except KeyError:
        raise aiowamp.AuthError(f"challenged with auth method {challenge.auth_method}, "
                                f"but no such method in keyring: {keyring}") from None

    exc = None
    try:
        auth = await method.authenticate(challenge)
    except Exception as e:
        log.exception("authentication failed", e)
        exc = e
        auth = aiowamp.msg.Abort({"error": type(e).__qualname__}, aiowamp.uri.AUTHORIZATION_FAILED)

    await transport.send(auth)

    if aiowamp.is_message_type(auth, aiowamp.msg.Abort):
        await transport.close()
        raise aiowamp.AuthError(f"authentication aborted: {auth!r}") from exc

    welcome = assert_welcome(await transport.recv())
    await method.check_welcome(welcome)

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
        aiowamp.URI.as_uri(realm),
        details,
    ))

    msg = await transport.recv()

    challenge = aiowamp.message_as_type(msg, aiowamp.msg.Challenge)
    if challenge:
        if not keyring:
            raise aiowamp.AuthError(f"received challenged with no keyring: {challenge!r}")

        welcome = await _authenticate(transport, challenge, keyring=keyring)
    else:
        welcome = assert_welcome(msg)

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
