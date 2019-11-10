import abc
import base64
import hashlib
import hmac
import logging
from typing import ClassVar, Dict, Iterator, Mapping

import aiowamp

__all__ = ["AuthMethodABC",
           "AuthKeyringABC", "AuthKeyring"]

log = logging.getLogger(__name__)


class AuthMethodABC(abc.ABC):
    __slots__ = ()

    method_name: ClassVar[str]

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {self.method_name!r}"

    @abc.abstractmethod
    async def authenticate(self, challenge: aiowamp.msg.Challenge) -> aiowamp.msg.Authenticate:
        ...


class AuthKeyringABC(Mapping[str, AuthMethodABC], abc.ABC):
    __slots__ = ()

    def __str__(self) -> str:
        methods = ", ".join(self)
        return f"{type(self).__qualname__}({methods})"

    @abc.abstractmethod
    def __getitem__(self, method: str) -> AuthMethodABC:
        ...

    @abc.abstractmethod
    def __len__(self) -> int:
        ...

    @abc.abstractmethod
    def __iter__(self) -> Iterator[str]:
        ...


class AuthKeyring(AuthKeyringABC):
    __slots__ = ("__auth_methods",)

    __auth_methods: Dict[str, AuthMethodABC]

    def __init__(self, *methods: AuthMethodABC) -> None:
        self.__auth_methods = {method.method_name: method for method in methods}

    def __repr__(self) -> str:
        methods = ", ".join(map(repr, self.__auth_methods.values()))
        return f"{type(self).__qualname__}({methods})"

    def __getitem__(self, method: str) -> AuthMethodABC:
        return self.__auth_methods[method]

    def __len__(self) -> int:
        return len(self.__auth_methods)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__auth_methods)


class CRAuth(AuthMethodABC):
    method_name = "wampcra"

    __slots__ = ("secret",)

    secret: str

    def __init__(self, secret: str) -> None:
        self.secret = secret

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.secret!r})"

    def pbkdf2_hmac(self, salt: str, key_len: int, iterations: int) -> bytes:
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
        return aiowamp.msg.Authenticate(signature, {}, )


class TicketAuth(AuthMethodABC):
    method_name = "ticket"

    __slots__ = ("__ticket",)

    __ticket: str

    def __init__(self, ticket: str) -> None:
        self.__ticket = ticket

    async def authenticate(self, challenge: aiowamp.msg.Challenge) -> aiowamp.msg.Authenticate:
        return aiowamp.msg.Authenticate(self.__ticket, {})


class ScramAuth(AuthMethodABC):
    method_name = "wamp-scram"

    __slots__ = ()
