from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Dict, Iterator, Optional

import aiowamp
from .abstract import AuthKeyringABC, AuthMethodABC

__all__ = ["AuthKeyring",
           # "register_auth_method", "get_auth_method", "load_auth_method",
           "CRAuth", "TicketAuth", "ScramAuth"]

log = logging.getLogger(__name__)


class AuthKeyring(AuthKeyringABC):
    __slots__ = ("__auth_methods",
                 "__auth_id", "__auth_extra")

    __auth_methods: Dict[str, aiowamp.AuthMethodABC]

    __auth_id: Optional[str]
    __auth_extra: Optional[aiowamp.WAMPDict]

    def __init__(self, *methods: aiowamp.AuthMethodABC,
                 auth_id: str = None) -> None:
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


# AUTH_METHODS: Dict[str, Type[SerializableAuthMethodABC]] = {}
#
#
# def register_auth_method(*, overwrite: bool = False):
#     def decorator(cls: Type[SerializableAuthMethodABC]):
#         try:
#             method_name = cls.method_name
#         except AttributeError:
#             raise NotImplementedError(f"Auth method {cls.__qualname__} does not specify a method_name") from None
#
#         if not overwrite and method_name in AUTH_METHODS:
#             raise ValueError(
#                 f"method with name {method_name} already defined by {AUTH_METHODS[method_name].__qualname__}."
#                 f"Use overwrite=True to overwrite.")
#
#         AUTH_METHODS[method_name] = cls
#
#         return cls
#
#     return decorator
#
#
# def get_auth_method(method_name: str) -> Type[SerializableAuthMethodABC]:
#     try:
#         return AUTH_METHODS[method_name]
#     except KeyError:
#         raise KeyError(f"no auth method with name {method_name!r}") from None
#
#
# def load_auth_method(data: aiowamp.WAMPDict) -> SerializableAuthMethodABC:
#     try:
#         method_name = data["method"]
#     except KeyError:
#         raise TypeError(f"data doesn't contain method name: {data!r}") from None
#
#     return get_auth_method(method_name).load(data)


class CRAuth(AuthMethodABC):
    method_name = "wampcra"

    __slots__ = ("secret",)

    secret: str

    def __init__(self, secret: str) -> None:
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
        return aiowamp.msg.Authenticate(self.__ticket, {})


class ScramAuth(AuthMethodABC):
    method_name = "wamp-scram"

    __slots__ = ()

    @property
    def requires_auth_id(self) -> bool:
        return True

    @property
    def auth_extra(self) -> aiowamp.WAMPDict:
        return {"nonce": "", "channel_binding": None}

# def _get_value(d: Mapping, key: str, *,
#                typ: type = None,
#                default: Any = None) -> Any:
#     try:
#         value = d[key]
#     except KeyError:
#         if default is not None:
#             return default
#
#         raise TypeError(f"expected {key!r} to be present in {d}") from None
#
#     if not isinstance(value, typ):
#         raise TypeError(f"expected value of {key!r} to be {typ.__qualname__}, "
#                         f"got {type(value).__qualname__}")
#
#     return value
