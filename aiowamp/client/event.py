from typing import Tuple

import aiowamp
from .abstract import SubscriptionEventABC

__all__ = ["SubscriptionEvent"]


class SubscriptionEvent(SubscriptionEventABC):
    __slots__ = ("__client",
                 "__topic", "__publication_id",
                 "__args", "__kwargs", "__details")

    __client: aiowamp.ClientABC

    __topic: aiowamp.URI
    __publication_id: int

    __args: Tuple[aiowamp.WAMPType, ...]
    __kwargs: aiowamp.WAMPDict
    __details: aiowamp.WAMPDict

    def __init__(self, client: aiowamp.ClientABC, msg: aiowamp.msg.Event, *,
                 topic: aiowamp.URI) -> None:
        self.__client = client

        self.__topic = topic
        self.__publication_id = msg.publication_id

        self.__args = tuple(msg.args) if msg.args else ()
        self.__kwargs = msg.kwargs or {}
        self.__details = msg.details

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
