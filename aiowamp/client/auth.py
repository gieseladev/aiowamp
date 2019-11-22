"""Provides the built-in authentication methods."""

from __future__ import annotations

import abc
import base64
import hashlib
import hmac
import logging
from typing import ClassVar, Dict, Iterator, Mapping, Optional, Union

import aiowamp
from aiowamp.msg import Authenticate as AuthenticateMsg

__all__ = ["AuthMethodABC",
           "AuthKeyringABC", "AuthKeyring",
           "CRAuth", "TicketAuth"]

log = logging.getLogger(__name__)


class AuthMethodABC(abc.ABC):
    """Abstract auth method."""
    __slots__ = ()

    method_name: ClassVar[str]
    """Name of the auth method."""

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {self.method_name!r}"

    @property
    @abc.abstractmethod
    def requires_auth_id(self) -> bool:
        """Whether the auth method requires auth_id to be set."""
        ...

    @property
    @abc.abstractmethod
    def auth_extra(self) -> Optional[aiowamp.WAMPDict]:
        """Additional auth extras that need to be passed along.

        `None` indicates that no extras need to be passed.
        """
        ...

    @abc.abstractmethod
    async def authenticate(self, challenge: aiowamp.msg.Challenge) \
            -> Union[aiowamp.msg.Authenticate, aiowamp.msg.Abort]:
        """Generate an authenticate message for the challenge.

        Args:
            challenge: Challenge message to respond to.

        Returns:
            Either an authenticate message to send to the router or an abort
            message to indicate that the attempt should be aborted.

        Raises:
            Exception: When something goes wrong during authentication.
                Should be interpreted the same as an abort message.
        """
        ...

    async def check_welcome(self, welcome: aiowamp.msg.Welcome) -> None:
        """Check the welcome message sent by the router.

        Used to perform mutual authentication.

        Args:
            welcome: Welcome message sent by the router.

        Raises:
            aiowamp.AuthError:
        """
        pass


class AuthKeyringABC(Mapping[str, "aiowamp.AuthMethodABC"], abc.ABC):
    """Abstract keyring for auth methods."""
    __slots__ = ()

    def __str__(self) -> str:
        methods = ", ".join(self)
        return f"{type(self).__qualname__}({methods})"

    @abc.abstractmethod
    def __getitem__(self, method: str) -> aiowamp.AuthMethodABC:
        """Get the auth method with the given name.

        Args:
            method: Name of the method to get.

        Returns:
            Auth method stored in the keyring.

        Raises:
            KeyError: If no auth method with the given method exists in the
                keyring.
        """
        ...

    @abc.abstractmethod
    def __len__(self) -> int:
        """Get the amount of auth methods in the keyring."""
        ...

    @abc.abstractmethod
    def __iter__(self) -> Iterator[str]:
        """Get an iterator for the auth method names in the keyring."""
        ...

    @property
    @abc.abstractmethod
    def auth_id(self) -> Optional[str]:
        """Auth id to use during authentication.

        Because most authentication methods require an auth id, this is handled
        by the keyring.
        """
        ...

    @property
    @abc.abstractmethod
    def auth_extra(self) -> Optional[aiowamp.WAMPDict]:
        """Auth extras with all the auth extras from the underlying methods.

        `None` if no auth extras are required.
        """
        ...


class AuthKeyring(AuthKeyringABC):
    __slots__ = ("__auth_methods",
                 "__auth_id", "__auth_extra")

    __auth_methods: Dict[str, "aiowamp.AuthMethodABC"]

    __auth_id: Optional[str]
    __auth_extra: Optional[aiowamp.WAMPDict]

    def __init__(self, *methods: "aiowamp.AuthMethodABC",
                 auth_id: str = None) -> None:
        """Initialise the keyring.

        Args:
            *methods: Methods to initialise the keyring with.
            auth_id: Auth id to use. Defaults to `None`.

        Raises:
            ValueError:
                - The same auth method type was specified multiple times.
                - No auth id was specified but one of the methods requires it.
                - Multiple methods specify the same auth extra key with
                    differing values.
        """
        auth_methods = {}
        auth_extra = {}

        for method in methods:
            name = method.method_name
            if name in auth_methods:
                raise ValueError(f"received same auth method multiple times: {name}")

            if auth_id is None and method.requires_auth_id:
                raise ValueError(f"{method} requires auth_id!")

            auth_methods[name] = method

            m_auth_extra = method.auth_extra
            if not m_auth_extra:
                continue

            for key, value in m_auth_extra.items():
                try:
                    existing_value = auth_extra[key]
                except KeyError:
                    pass
                else:
                    if existing_value != value:
                        raise ValueError(f"{method} provides auth extra {key} = {value!r}, "
                                         f"but the key is already set by another method as {existing_value!r}")

                auth_extra[key] = value

        self.__auth_methods = auth_methods

        self.__auth_id = auth_id
        self.__auth_extra = auth_extra or None

    def __repr__(self) -> str:
        methods = ", ".join(map(repr, self.__auth_methods.values()))
        return f"{type(self).__qualname__}({methods})"

    def __getitem__(self, method: str) -> AuthMethodABC:
        return self.__auth_methods[method]

    def __len__(self) -> int:
        return len(self.__auth_methods)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__auth_methods)

    @property
    def auth_id(self) -> Optional[str]:
        return self.__auth_id

    @property
    def auth_extra(self) -> Optional[aiowamp.WAMPDict]:
        return self.__auth_extra


class CRAuth(AuthMethodABC):
    """Auth method for challenge response authentication.

    WAMP Challenge-Response ("WAMP-CRA") authentication is a simple, secure
    authentication mechanism using a shared secret. The client and the server
    share a secret. The secret never travels the wire, hence WAMP-CRA can be
    used via non-TLS connections. The actual pre-sharing of the secret is
    outside the scope of the authentication mechanism.
    """
    method_name = "wampcra"

    __slots__ = ("secret",)

    secret: str
    """Secret to use for authentication."""

    def __init__(self, secret: str) -> None:
        """Initialise the auth method.

        Args:
            secret: Secret to use.
        """
        self.secret = secret

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.secret!r})"

    @property
    def requires_auth_id(self) -> bool:
        return True

    @property
    def auth_extra(self) -> None:
        return None

    def pbkdf2_hmac(self, salt: str, key_len: int, iterations: int) -> bytes:
        """Derive the token using the pdkdf2 scheme.

        Args:
            salt: Salt
            key_len: Key length
            iterations: Amount of iterations

        Returns:
            Generated token bytes.
        """
        return hashlib.pbkdf2_hmac("sha256", self.secret, salt, iterations, key_len)

    async def authenticate(self, challenge: aiowamp.msg.Challenge) -> aiowamp.msg.Authenticate:
        extra = challenge.extra

        try:
            challenge_str: str = extra["challenge"]
        except KeyError:
            raise KeyError("challenge didn't provide 'challenge' string to sign") from None

        try:
            salt: str = extra["salt"]
            key_len: int = extra["keylen"]
            iterations: int = extra["iterations"]
        except KeyError:
            log.info("%s: using secret directly", self)
            secret = self.secret
        else:
            log.info("%s: deriving secret from salted password", self)
            secret = self.pbkdf2_hmac(salt, iterations, key_len)

        digest = hmac.digest(secret, challenge_str, hashlib.sha256)
        signature = base64.b64encode(digest).encode()
        return aiowamp.msg.Authenticate(signature, {})


class TicketAuth(AuthMethodABC):
    """Auth method for ticket-based authentication.

    With Ticket-based authentication, the client needs to present the server an
    authentication "ticket" - some magic value to authenticate itself to the
    server.

    This "ticket" could be a long-lived, pre-agreed secret
    (e.g. a user password) or a short-lived authentication token
    (like a Kerberos token). WAMP does not care or interpret the ticket
    presented by the client.

        Caution: This scheme is extremely simple and flexible, but the resulting
        security may be limited. E.g., the ticket value will be sent over the
        wire. If the transport WAMP is running over is not encrypted, a
        man-in-the-middle can sniff and possibly hijack the ticket. If the
        ticket value is reused, that might enable replay attacks.
    """
    method_name = "ticket"

    __slots__ = ("__ticket",)

    __ticket: str

    def __init__(self, ticket: str) -> None:
        self.__ticket = ticket

    @property
    def requires_auth_id(self) -> bool:
        return True

    @property
    def auth_extra(self) -> None:
        return None

    async def authenticate(self, challenge: aiowamp.msg.Challenge) -> aiowamp.msg.Authenticate:
        return AuthenticateMsg(self.__ticket, {})


class ScramAuth(AuthMethodABC):
    method_name = "wamp-scram"

    __slots__ = ()

    @property
    def requires_auth_id(self) -> bool:
        return True

    @property
    def auth_extra(self) -> aiowamp.WAMPDict:
        return {"nonce": "", "channel_binding": None}
