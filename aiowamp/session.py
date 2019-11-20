from __future__ import annotations

import abc
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Awaitable

import aiowamp
from .maybe_awaitable import MaybeAwaitable, call_async_fn_background
from .message import message_as_type
from .msg import Goodbye as GoodbyeMsg
from .uri import CLOSE_NORMAL, GOODBYE_AND_OUT

__all__ = ["MessageHandler",
           "SessionABC", "Session"]

log = logging.getLogger(__name__)

MessageHandler = Callable[["aiowamp.MessageABC"], MaybeAwaitable[Any]]


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
        """Goodbye message sent by the remote."""
        ...

    @property
    @abc.abstractmethod
    def roles(self) -> Set[str]:
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
    async def wait_until_done(self) -> Optional[aiowamp.msg.Goodbye]:
        ...

    @abc.abstractmethod
    def add_message_handler(self, handler: aiowamp.MessageHandler) -> None:
        ...

    @abc.abstractmethod
    def remove_message_handler(self, handler: aiowamp.MessageHandler = None) -> None:
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
                 "control_transport",
                 "__session_id", "__realm", "__details",
                 "__roles",
                 "__goodbye_fut",
                 "__msg_handlers", "__receive_task")

    transport: aiowamp.TransportABC
    """Transport used by the session."""

    control_transport: bool
    """Whether the session controls the underlying transport.
    
    If this is `True`, the session will close the transport when it 
    """

    __session_id: int
    __realm: str
    __details: aiowamp.WAMPDict

    __roles: Dict[str, Set[str]]

    __goodbye_fut: Optional[asyncio.Future]

    __msg_handlers: List["aiowamp.MessageHandler"]
    __receive_task: Optional[asyncio.Task]

    def __init__(self, transport: aiowamp.TransportABC, session_id: int, realm: str, details: aiowamp.WAMPDict, *,
                 control_transport: bool = True) -> None:
        if not transport.open:
            raise RuntimeError(f"transport {transport} must be open")

        self.transport = transport

        self.control_transport = control_transport

        self.__session_id = session_id
        self.__realm = realm
        self.__details = details

        self.__roles = get_role_map(details)

        self.__goodbye_fut = None

        self.__msg_handlers = []
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
        return set(self.__roles.keys())

    def __receive_loop_running(self) -> bool:
        return bool(self.__receive_task and not self.__receive_task.done())

    def start(self) -> None:
        if self.__receive_loop_running():
            raise RuntimeError("receive loop already running.")

        self.__receive_task = asyncio.create_task(self.__receive_loop())

    def __get_goodbye_fut(self) -> asyncio.Future:
        if not self.__goodbye_fut:
            loop = asyncio.get_running_loop()
            self.__goodbye_fut = loop.create_future()

        return self.__goodbye_fut

    async def __handle_goodbye(self, goodbye: aiowamp.msg.Goodbye) -> None:
        # remote initiated goodbye
        if not self.__goodbye_fut:
            if goodbye.reason == GOODBYE_AND_OUT:
                log.warning(f"received {goodbye} confirmation before closing.")

            await self.send(GoodbyeMsg(
                {},
                GOODBYE_AND_OUT,
            ))

        self.__get_goodbye_fut().set_result(goodbye)

    async def __receive_loop(self) -> None:
        log.debug("%s: starting receive loop", self)

        while True:
            msg = await self.transport.recv()

            goodbye = message_as_type(msg, GoodbyeMsg)
            if goodbye:
                await self.__handle_goodbye(goodbye)
                break

            # goodbye messages are not sent to handlers

            for handler in self.__msg_handlers:
                call_async_fn_background(handler, "message handler raised an exception",
                                         msg)

        log.debug("%s: exiting receive loop", self)

    async def send(self, msg: aiowamp.MessageABC) -> None:
        await self.transport.send(msg)

    async def close(self, details: aiowamp.WAMPDict = None, *,
                    reason: aiowamp.URI = None) -> None:
        _ = self.__get_goodbye_fut()

        await self.send(GoodbyeMsg(
            details or {},
            reason or CLOSE_NORMAL,
        ))

        try:
            await self.wait_until_done()
        except Exception:
            log.exception("receive loop raised exception")

    async def wait_until_done(self) -> Optional[aiowamp.msg.Goodbye]:
        if not self.__receive_loop_running():
            self.start()

        try:
            await self.__receive_task
        finally:
            if self.control_transport:
                await self.transport.close()

        return self.goodbye

    def add_message_handler(self, handler: aiowamp.MessageHandler) -> None:
        if handler in self.__msg_handlers:
            raise ValueError(f"{handler} already exists")

        self.__msg_handlers.append(handler)
        if not self.__receive_loop_running():
            self.start()

    def remove_message_handler(self, handler: aiowamp.MessageHandler = None) -> None:
        if handler is None:
            self.__msg_handlers.clear()
        else:
            try:
                self.__msg_handlers.remove(handler)
            except ValueError:
                raise ValueError(f"handler {handler} doesn't exist") from None

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
