from __future__ import annotations

import abc
from typing import Generic, Optional, Tuple, TypeVar

import aiowamp
from aiowamp import URI
from aiowamp.args_mixin import ArgsMixin

__all__ = ["SubscriptionEventABC", "SubscriptionEvent"]

ClientT = TypeVar("ClientT", bound="aiowamp.ClientABC")


class SubscriptionEventABC(ArgsMixin, abc.ABC, Generic[ClientT]):
    __slots__ = ()

    def __str__(self) -> str:
        return f"{type(self).__qualname__} {self.publication_id}"

    @property
    @abc.abstractmethod
    def client(self) -> ClientT:
        ...

    @property
    @abc.abstractmethod
    def publication_id(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def subscribed_topic(self) -> aiowamp.URI:
        ...

    @property
    def topic(self) -> aiowamp.URI:
        """Concrete topic that caused the event.

        This will be the same as `subscribed_topic` unless the handler
        subscribed with a pattern-based matching policy.
        """
        try:
            return URI(self.details["topic"])
        except KeyError:
            return self.subscribed_topic

    @property
    @abc.abstractmethod
    def args(self) -> Tuple[aiowamp.WAMPType, ...]:
        ...

    @property
    @abc.abstractmethod
    def kwargs(self) -> aiowamp.WAMPDict:
        ...

    @property
    @abc.abstractmethod
    def details(self) -> aiowamp.WAMPDict:
        ...

    @property
    def publisher_id(self) -> Optional[int]:
        """Get the publisher's id.

        Returns:
            WAMP id of the caller, or `None` if not disclosed.
        """
        return self.details.get("caller")

    @property
    def trust_level(self) -> Optional[int]:
        """Get the router assigned trust level.

        The trust level 0 means lowest trust, and higher integers represent
        (application-defined) higher levels of trust.

        Returns:
            The trust level, or `None` if not specified.
        """
        return self.details.get("trustlevel")

    @abc.abstractmethod
    async def unsubscribe(self) -> None:
        ...


class SubscriptionEvent(SubscriptionEventABC[ClientT], Generic[ClientT]):
    __slots__ = ("__client",
                 "__topic", "__publication_id",
                 "__args", "__kwargs", "__details")

    __client: ClientT

    __topic: aiowamp.URI
    __publication_id: int

    __args: Tuple[aiowamp.WAMPType, ...]
    __kwargs: aiowamp.WAMPDict
    __details: aiowamp.WAMPDict

    def __init__(self, client: ClientT, msg: aiowamp.msg.Event, *,
                 topic: aiowamp.URI) -> None:
        """Create a new SubscriptionEven instance.

        There shouldn't be a need to create these yourself, unless you're
        creating your own `aiowamp.ClientABC`.
        Unlike `aiowamp.Invocation` it doesn't require to be managed though.

        Args:
            client: Client used to unsubscribe.
            msg: Event message.
            topic: Registered topic URI.
        """
        self.__client = client

        self.__topic = topic
        self.__publication_id = msg.publication_id

        self.__args = tuple(msg.args) if msg.args else ()
        self.__kwargs = msg.kwargs or {}
        self.__details = msg.details

    @property
    def client(self) -> ClientT:
        return self.__client

    @property
    def publication_id(self) -> int:
        return self.__publication_id

    @property
    def subscribed_topic(self) -> aiowamp.URI:
        return self.__topic

    @property
    def args(self) -> Tuple[aiowamp.WAMPType, ...]:
        return self.__args

    @property
    def kwargs(self) -> aiowamp.WAMPDict:
        return self.__kwargs

    @property
    def details(self) -> aiowamp.WAMPDict:
        return self.__details

    async def unsubscribe(self) -> None:
        await self.__client.unsubscribe(self.__topic)
