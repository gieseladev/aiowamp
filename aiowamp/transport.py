import abc

import aiowamp.message

__all__ = ["TransportABC"]


class TransportABC(abc.ABC):
    """Abstract transport type.

    A Transport connects two WAMP Peers and provides a channel over which WAMP
    messages for a WAMP Session can flow in both directions.

    WAMP can run over any Transport which is message-based, bidirectional,
    reliable and ordered.
    """
    __slots__ = ()

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the transport."""
        ...

    @abc.abstractmethod
    async def send(self, msg: aiowamp.MessageABC) -> None:
        """Send a message.

        Args:
            msg: Message to send.
        """
        ...

    @abc.abstractmethod
    async def recv(self) -> aiowamp.MessageABC:
        """Receive a message.

        Returns:
            Received message.
        """
        ...
