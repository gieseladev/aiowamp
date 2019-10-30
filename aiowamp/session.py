from __future__ import annotations

import abc

import aiowamp

__all__ = ["SessionABC", "Session"]


class SessionABC(abc.ABC):
    """Abstract session type.

    A Session is a transient conversation between two Peers attached to a Realm
    and running over a Transport.
    """
    __slots__ = ()

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

    @abc.abstractmethod
    async def send(self, msg: aiowamp.MessageABC) -> None:
        """Send a message using the underlying transport."""
        ...


class Session(SessionABC):
    __slots__ = ("__session_id", "__realm", "__details",
                 "transport")

    transport: aiowamp.TransportABC

    __session_id: int
    __realm: str
    __details: aiowamp.WAMPDict

    def __init__(self, transport: aiowamp.TransportABC, session_id: int, realm: str, details: aiowamp.WAMPDict) -> None:
        self.transport = transport
        self.__session_id = session_id
        self.__realm = realm
        self.__details = details

    @property
    def session_id(self) -> int:
        return self.__session_id

    @property
    def realm(self) -> str:
        return self.__realm

    @property
    def details(self) -> aiowamp.WAMPDict:
        return self.__details

    async def send(self, msg: aiowamp.MessageABC) -> None:
        await self.transport.send(msg)
