"""Provides utilities for the client package."""

from __future__ import annotations

from typing import Type, TypeVar

import aiowamp
from aiowamp import UnexpectedMessageError, error_to_exception, message_as_type
from aiowamp.msg import Error as ErrorMsg

__all__ = ["check_message_response"]

MsgT = TypeVar("MsgT", bound="aiowamp.MessageABC")


def check_message_response(msg: aiowamp.MessageABC, ok_type: Type[MsgT]) -> MsgT:
    """Assert that a message has a given type.

    Args:
        msg: Message to check.
        ok_type: Message type to check against.

    Returns:
        The message that was passed to the function. This makes it so that it
        can be used as a type guard.

    Raises:
        UnexpectedMessageError: If the message doesn't have the expected
            message type.
        Exception: If the message is an `aiowamp.msg.Error`.
    """
    ok = message_as_type(msg, ok_type)
    if ok:
        return ok

    error = message_as_type(msg, ErrorMsg)
    if error:
        raise error_to_exception(error)

    raise UnexpectedMessageError(msg, ok_type)
