import abc
from typing import ClassVar, Dict, List, Optional, Type, TypeVar, Union, cast

import aiowamp

__all__ = ["WAMPType", "WAMPList", "WAMPDict",
           "MessageABC",
           "is_message_type", "message_as_type",
           "register_message_cls", "get_message_cls", "build_message_from_list"]

WAMPType = Union[int, str, bool, "WAMPList", "WAMPDict"]
"""WAMP type.

Contains value types which SHOULD be supported by all serializers.
"""

WAMPList = List[WAMPType]
"""Type of a list containing WAMP types."""

WAMPDict = Dict[str, WAMPType]
"""Dict with string keys and WAMP type values."""

T = TypeVar("T")


class MessageABC(abc.ABC):
    """Base class for WAMP messages."""
    __slots__ = ()

    message_type: ClassVar[int]
    """Type code of the message."""

    def __str__(self) -> str:
        return f"{self.message_type} {type(self).__qualname__}"

    @abc.abstractmethod
    def to_message_list(self) -> WAMPList:
        """Convert the message to a list

        Returns:
            List containing the message including the message type.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def from_message_list(cls: Type[T], msg_list: WAMPList) -> T:
        """Build the message from msg_list.

        Args:
            msg_list: Message list without the message type.

        Returns:
            Instance of the message type.
        """
        ...


def is_message_type(msg: MessageABC, msg_type: Type[MessageABC]) -> bool:
    """Checks whether msg is of type msg_type.

    This should be preferred over `isinstance` checks as it supports duck typing.
    If, however, the built-in message class is overwritten with a custom one
    and you depend on a specific feature of said class then `isinstance` should
    be used.

    Args:
        msg: Message to check.
        msg_type: Message type to check against.
            IMPORTANT: The function doesn't actually cast to the type, it is
            assumed that if two message types share the same type code, they
            are interchangeable.

    Returns:
        Whether msg and msg_type have the same `aiowamp.MessageABC.message_type`.
    """
    return msg.message_type == msg_type.message_type


MsgT = TypeVar("MsgT", bound=MessageABC)


def message_as_type(msg: MessageABC, msg_type: Type[MsgT]) -> Optional[MsgT]:
    """Cast msg if it is of type msg_type.

    Uses `aiowamp.is_message_type` to check if msg is of type msg_type.

    Args:
        msg: Message to cast.
        msg_type: Message type to cast to.

    Returns:
        `None`, if msg is not of type msg_type, otherwise it returns msg.

    Examples:
        This function can be used as a type guard:

        >>> import aiowamp
        >>> msg: aiowamp.MessageABC = aiowamp.msg.Hello(aiowamp.URI(""), {})
        >>> # type of hello_msg is inferred as Optional[aiowamp.msg.Hello]
        >>> hello_msg = message_as_type(msg, aiowamp.msg.Hello)
        >>> hello_msg is msg
        True
    """
    if is_message_type(msg, msg_type):
        return cast(MsgT, msg)

    return None


MESSAGE_TYPE_MAP: Dict[int, Type[MessageABC]] = {}


def register_message_cls(*messages: Type[MessageABC], overwrite: bool = False) -> None:
    """Register the messages.

    Args:
        *messages: Message types to register.
        overwrite: If existing types should be overwritten.
            Defaults to `False` which makes overwriting an existing message type
            an error.

    Raises:
        ValueError: If the message type for a message is already registered by
            another type and overwrite is `False`.
    """
    for m in messages:
        try:
            mtyp = m.message_type
        except AttributeError:
            raise NotImplementedError(f"{m!r} does not overwrite the 'message_type' attribute.") from None

        if not overwrite and mtyp in MESSAGE_TYPE_MAP:
            raise ValueError(f"cannot register message {m!r} for code {mtyp}, "
                             f"already used by {MESSAGE_TYPE_MAP[mtyp]!r}")

        MESSAGE_TYPE_MAP[mtyp] = m


def get_message_cls(msg_type: int) -> Type[MessageABC]:
    """Returns the message type registered for msg_type.

    Args:
        msg_type: Message type to look for.

    Returns:
        Message type registered for msg_type.

    Raises:
        KeyError: If no message type is registered for msg_type.
    """
    try:
        return MESSAGE_TYPE_MAP[msg_type]
    except KeyError:
        raise KeyError(f"no message type registered for type: {msg_type}") from None


def build_message_from_list(msg_list: WAMPList) -> MessageABC:
    """Create a message from msg_list.

    Uses the registered message type.

    Args:
        msg_list: Message list containing the message type as the first element.

    Returns:
        Built message.
    """
    try:
        msg_type = msg_list[0]
    except IndexError:
        raise aiowamp.InvalidMessage("received message without message type") from None

    if not isinstance(msg_type, int):
        raise aiowamp.InvalidMessage("received message without integer message type")

    msg_cls = get_message_cls(msg_type)

    try:
        return msg_cls.from_message_list(msg_list[1:])
    except Exception as e:
        raise aiowamp.InvalidMessage(f"failed to build message type {msg_cls!r} from message list") from e
