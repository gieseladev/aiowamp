from __future__ import annotations

import abc
import asyncio
import logging
from typing import Dict, Optional, Set

import aiobservable

import aiowamp

__all__ = ["SessionABC", "Session"]

log = logging.getLogger(__name__)


class SessionABC(abc.ABC):
    """Abstract session type.

    A Session is a transient conversation between two Peers attached to a Realm
    and running over a Transport.
    """
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {self.session_id}"

    @property
    @abc.abstractmethod
    def session_id(self) -> int:
        """Session ID."""
        ...

    @property
    @abc.abstractmethod
    def realm(self) -> str:
        """Name of the realm the session is attached to."""
        ...

    @property
    @abc.abstractmethod
    def details(self) -> aiowamp.WAMPDict:
        ...

    @property
    @abc.abstractmethod
    def goodbye(self) -> Optional[aiowamp.msg.Goodbye]:
        ...

    @property
    @abc.abstractmethod
    def roles(self) -> Set[str]:
        ...

    @property
    @abc.abstractmethod
    def message_handler(self) -> aiobservable.ObservableABC[aiowamp.MessageABC]:
        ...

    @abc.abstractmethod
    async def close(self, details: aiowamp.WAMPDict = None, *,
                    reason: aiowamp.URI = None) -> None:
        ...

    @abc.abstractmethod
    async def send(self, msg: aiowamp.MessageABC) -> None:
        """Send a message using the underlying transport."""
        ...

    @abc.abstractmethod
    def get_features(self, role: str) -> Set[str]:
        ...

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_feature(self, role: str, feature: str) -> bool:
        return feature in self.get_features(role)


class Session(SessionABC):
    __slots__ = ("transport",
                 "__session_id", "__realm", "__details",
                 "__roles",
                 "__goodbye_fut",
                 "__message_handler", "__receive_task")

    transport: aiowamp.TransportABC

    __session_id: int
    __realm: str
    __details: aiowamp.WAMPDict

    __roles: Dict[str, Set[str]]

    __goodbye_fut: Optional[asyncio.Future]

    __message_handler: Optional[aiobservable.Observable[aiowamp.MessageABC]]
    __receive_task: Optional[asyncio.Task]

    def __init__(self, transport: aiowamp.TransportABC, session_id: int, realm: str, details: aiowamp.WAMPDict) -> None:
        self.transport = transport

        self.__session_id = session_id
        self.__realm = realm
        self.__details = details

        self.__roles = get_role_map(details)

        self.__goodbye_fut = None

        self.__message_handler = None
        self.__receive_task = None

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.transport}, " \
               f"session_id={self.session_id!r}, realm={self.realm!r}, " \
               f"details={self.details!r})"

    @property
    def session_id(self) -> int:
        return self.__session_id

    @property
    def realm(self) -> str:
        return self.__realm

    @property
    def details(self) -> aiowamp.WAMPDict:
        return self.__details

    @property
    def goodbye(self) -> Optional[aiowamp.msg.Goodbye]:
        try:
            return self.__goodbye_fut.result()
        except Exception:
            return None

    @property
    def roles(self) -> Set[str]:
        return set(self.__roles)

    @property
    def message_handler(self) -> aiobservable.ObservableABC[aiowamp.MessageABC]:
        if self.__message_handler is None:
            self.start()

        return self.__message_handler

    def __receive_loop_running(self) -> bool:
        return bool(self.__receive_task and not self.__receive_task.done())

    def start(self) -> None:
        if self.__receive_loop_running():
            raise RuntimeError("receive loop already running.")

        self.__message_handler = aiobservable.Observable()
        self.__receive_task = asyncio.create_task(self.__receive_loop())

    def __get_goodbye_fut(self) -> asyncio.Future:
        if not self.__goodbye_fut:
            loop = asyncio.get_running_loop()
            self.__goodbye_fut = loop.create_future()

        return self.__goodbye_fut

    async def __handle_goodbye(self, goodbye: aiowamp.msg.Goodbye) -> None:
        # remote initiated goodbye
        if not self.__goodbye_fut:
            if goodbye.reason == aiowamp.uri.GOODBYE_AND_OUT:
                raise RuntimeError(f"received {goodbye} confirmation before closing.")

            await self.send(aiowamp.msg.Goodbye(
                {},
                aiowamp.uri.GOODBYE_AND_OUT,
            ))

        self.__get_goodbye_fut().set_result(goodbye)

    async def __receive_loop(self) -> None:
        assert self.__message_handler is not None

        log.debug("%s: starting receive loop", self)

        while True:
            msg = await self.transport.recv()
            _ = self.__message_handler.emit(msg)

            goodbye = aiowamp.message_as_type(msg, aiowamp.msg.Goodbye)
            if goodbye:
                await self.__handle_goodbye(goodbye)
                break

        log.debug("%s: exiting receive loop", self)

    async def send(self, msg: aiowamp.MessageABC) -> None:
        await self.transport.send(msg)

    async def close(self, details: aiowamp.WAMPDict = None, *,
                    reason: aiowamp.URI = None) -> None:
        if not self.__receive_loop_running():
            self.start()

        goodbye_fut = self.__get_goodbye_fut()

        await self.send(aiowamp.msg.Goodbye(
            details or {},
            reason or aiowamp.uri.CLOSE_NORMAL,
        ))

        await goodbye_fut
        await self.transport.close()

    def has_role(self, role: str) -> bool:
        # faster than `role in set(self.__roles)`
        return role in self.__roles

    def get_features(self, role: str) -> Set[str]:
        try:
            return self.__roles[role]
        except KeyError:
            return set()


def get_role_map(details: aiowamp.WAMPDict) -> Dict[str, Set[str]]:
    try:
        roles = details["roles"]
    except KeyError:
        return {}

    if not isinstance(roles, dict):
        return {}

    role_map: Dict[str, Set[str]] = {}
    for role, role_dict in roles.items():
        feature_set: Set[str] = set()
        role_map[role] = feature_set

        try:
            features = role_dict["features"]
        except KeyError:
            continue

        if not isinstance(features, dict):
            continue

        for feature, supported in features.items():
            if supported:
                feature_set.add(feature)

    return role_map
