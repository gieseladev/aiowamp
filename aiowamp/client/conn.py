"""Provides the logic for connecting to a router."""

from __future__ import annotations

import logging
import urllib.parse as urlparse
from typing import Union

import aiowamp
from aiowamp import AbortError, AuthError, CommonTransportConfig, Session, UnexpectedMessageError, connect_transport, \
    is_message_type, message_as_type
from aiowamp.msg import Abort as AbortMsg, Challenge as ChallengeMsg, Hello as HelloMsg, Welcome as WelcomeMsg
from aiowamp.uri import AUTHORIZATION_FAILED
from .client import Client
from .roles import CLIENT_ROLES

__all__ = ["connect", "join_realm"]

log = logging.getLogger(__name__)


def assert_welcome(msg: aiowamp.MessageABC) -> aiowamp.msg.Welcome:
    """Assert that the given message is a welcome message.

    Args:
        msg: Message to check.

    Returns:
        The same message that was passed in.
        This makes it possible to use it as a type guard.

    Raises:
        AbortError: If the message is an abort message.
        UnexpectedMessageError: If the message has any other type.
    """
    abort = message_as_type(msg, AbortMsg)
    if abort:
        raise AbortError(abort)

    welcome = message_as_type(msg, WelcomeMsg)
    if not welcome:
        raise UnexpectedMessageError(msg, WelcomeMsg)

    return welcome


async def _authenticate(transport: aiowamp.TransportABC, challenge: aiowamp.msg.Challenge, *,
                        keyring: aiowamp.AuthKeyringABC) -> aiowamp.msg.Welcome:
    try:
        method = keyring[challenge.auth_method]
    except KeyError:
        raise AuthError(f"challenged with auth method {challenge.auth_method}, "
                        f"but no such method in keyring: {keyring}") from None

    exc = None
    try:
        auth = await method.authenticate(challenge)
    except Exception as e:
        log.exception("authentication failed", e)
        exc = e
        auth = AbortMsg({"error": type(e).__qualname__}, AUTHORIZATION_FAILED)

    await transport.send(auth)

    if is_message_type(auth, AbortMsg):
        await transport.close()
        raise AuthError(f"authentication aborted: {auth!r}") from exc

    welcome = assert_welcome(await transport.recv())
    await method.check_welcome(welcome)

    return welcome


async def join_realm(transport: aiowamp.TransportABC, realm: str, *,
                     keyring: aiowamp.AuthKeyringABC = None,
                     roles: aiowamp.WAMPDict = None,
                     details: aiowamp.WAMPDict = None) -> aiowamp.Session:
    """Join a realm on a router.

    Args:
        transport: Transport to run the session over.
        realm: Realm to join.

        keyring: Authentication keyring to use for authentication.
        roles: Roles to announce with.
        details: Additional details to send with the hello message.

    Returns:
        Session running over the transport connected to the realm.

    Raises:
        AbortError: If the joining was aborted.
        AuthError: If the authentication failed.
    """
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

    await transport.send(HelloMsg(
        realm,
        details,
    ))

    msg = await transport.recv()

    challenge = message_as_type(msg, ChallengeMsg)
    if challenge:
        if not keyring:
            raise AuthError(f"received challenged with no keyring: {challenge!r}")

        welcome = await _authenticate(transport, challenge, keyring=keyring)
    else:
        welcome = assert_welcome(msg)

    return Session(transport, welcome.session_id, realm, welcome.details)


async def connect(url: Union[str, urlparse.ParseResult], *,
                  realm: str,
                  serializer: aiowamp.SerializerABC = None,
                  keyring: aiowamp.AuthKeyringABC = None) -> aiowamp.Client:
    """Connect to a router, join a realm, and create a client.

    Args:
        url: URL of the router to connect to.
        realm: Realm to join.

        serializer: Serializer to use for the transport.
        keyring: Authentication keyring.

    Returns:
        Client wrapping the established session.

    Raises:
        Exception: If the connection fails.

        AbortError: If the joining was aborted.
        AuthError: If the authentication failed.
    """
    if not isinstance(url, urlparse.ParseResult):
        url = urlparse.urlparse(url)

    log.info("connecting to %s", url)
    transport = await connect_transport(CommonTransportConfig(
        url,
        serializer=serializer,
    ))

    log.info("joining realm %s", realm)
    session = await join_realm(transport, realm,
                               keyring=keyring,
                               roles=CLIENT_ROLES)
    return Client(session)
