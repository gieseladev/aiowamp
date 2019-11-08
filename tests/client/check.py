import itertools
from typing import Any, Iterable, Type, Union

import aiowamp
from aiowamp.client.invocation import get_return_values
from tests import mock


def assert_msg(msg: Any, typ: Type[aiowamp.MessageABC] = None) -> None:
    assert isinstance(msg, aiowamp.MessageABC)
    if typ is not None:
        assert aiowamp.is_message_type(msg, typ)


def assert_progress_yield(msg: Any) -> None:
    assert_msg(msg, aiowamp.msg.Yield)

    return msg.options.get("progress", False)


def check_args_kwargs(msg: Any, args, kwargs) -> None:
    assert_msg(msg, aiowamp.msg.Yield)

    assert msg.args == list(args)
    assert msg.kwargs == kwargs


def check_error(a: Any, b: Any) -> None:
    assert_msg(a, aiowamp.msg.Error)
    assert_msg(b, aiowamp.msg.Error)

    assert a.error == b.error
    assert a.args == b.args
    assert a.kwargs == b.kwargs


def check_invocation(invocation: aiowamp.InvocationABC,
                     progress: Iterable[aiowamp.InvocationHandlerResult],
                     final: aiowamp.InvocationHandlerResult = None, *,
                     error: Union[aiowamp.msg.Error, bool] = None) -> None:
    sent_messages = mock.get_messages(invocation)
    print("\nSENT:", sent_messages)
    final_msg = sent_messages.pop()

    for expected, msg in itertools.zip_longest(progress, sent_messages):
        assert expected is not None, ("got unexpected progress", msg)
        assert msg is not None, ("missing progress", expected)

        assert assert_progress_yield(msg), "not a progress message"

        args, kwargs = get_return_values(expected)
        check_args_kwargs(msg, args, kwargs)

    if final is not None or error is not None:
        assert final_msg is not None, "no final message"

    if final is not None:
        assert aiowamp.is_message_type(final_msg, aiowamp.msg.Yield), "invocation didn't send a final result"
        assert not assert_progress_yield(final_msg), "final msg is progress yield"

        args, kwargs = get_return_values(final)
        check_args_kwargs(final_msg, args, kwargs)
    elif error is not None:
        assert aiowamp.is_message_type(final_msg, aiowamp.msg.Error), "invocation didn't send an error"
        if error is not True:
            check_error(final_msg, error)
    else:
        assert final_msg is None, "expected no final message"
