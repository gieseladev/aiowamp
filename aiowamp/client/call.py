from __future__ import annotations

import asyncio
import logging
from typing import Optional, Type, Union

import aiowamp
from .abstract import CallABC
from .utils import call_async_fn_background, check_message_response

__all__ = ["Call"]

log = logging.getLogger(__name__)


class Call(CallABC):
    __slots__ = ("session",
                 "_call_msg", "_call_sent",
                 "__cancel_mode",
                 "__result_fut", "__progress_queue", "__progress_handler")

    session: aiowamp.SessionABC
    _call_msg: aiowamp.msg.Call
    _call_sent: bool

    __cancel_mode: aiowamp.CancelMode

    __result_fut: asyncio.Future
    __progress_queue: Optional[asyncio.Queue]
    __progress_handler: Optional[aiowamp.ProgressHandler]

    def __init__(self, session: aiowamp.SessionABC, call: aiowamp.msg.Call, *,
                 cancel_mode: aiowamp.CancelMode) -> None:
        self.session = session
        self._call_msg = call
        self._call_sent = False

        self.__cancel_mode = cancel_mode

        loop = asyncio.get_running_loop()

        self.__result_fut = loop.create_future()
        self.__progress_queue = None
        self.__progress_handler = None

    def __repr__(self) -> str:
        return f"Call({self.session!r}, {self._call_msg!r})"

    @property
    def request_id(self) -> int:
        return self._call_msg.request_id

    @property
    def done(self) -> bool:
        return self.__result_fut.done()

    @property
    def cancelled(self) -> bool:
        return self.__result_fut.cancelled()

    def on_progress(self, handler: aiowamp.ProgressHandler) -> None:
        if self.done:
            raise RuntimeError("call is already complete. Progress handler should be added first"
                               "(i.e. before awaiting)")
        if self.__progress_handler:
            raise RuntimeError("progress handler already set")

        self.__ensure_receive_progress()
        self.__progress_handler = handler

    def kill(self, e: Exception) -> None:
        if self.done:
            return

        self.__result_fut.set_exception(e)
        if self.__progress_queue is not None:
            self.__progress_queue.put_nowait(None)

    def __ensure_receive_progress(self) -> None:
        try:
            receive_progress = self._call_msg.options["receive_progress"]
        except KeyError:
            if self._call_sent:
                raise RuntimeError(
                    "call already sent, please either specify receive_progress "
                    "in the call, or add progress handlers before starting it") from None

            self._call_msg.options["receive_progress"] = True
            return

        if not receive_progress:
            raise RuntimeError("call is explicitly unwilling to receive progress")

    def __handle_progress(self, progress_msg: aiowamp.msg.Result) -> None:
        if self.__progress_handler is None and self.__progress_queue is None:
            # Probably best not to use a warning because one might want to ignore
            # the progress results, but still, we should inform the user somehow.
            log.info("%s: received progress but has no handler", self)
            return

        progress = _create_invocation_result(progress_msg.args, progress_msg.kwargs, progress_msg.details,
                                             cls=aiowamp.InvocationProgress)

        if self.__progress_handler is not None:
            call_async_fn_background(self.__progress_handler,
                                     "progress handler raised exception",
                                     progress)

        if self.__progress_queue is not None:
            self.__progress_queue.put_nowait(progress)

    def handle_response(self, msg: aiowamp.MessageABC) -> bool:
        if self.done:
            # already done, no need to handle message
            return True

        result = aiowamp.message_as_type(msg, aiowamp.msg.Result)
        if result and result.details.get("progress"):
            self.__handle_progress(result)
            return False

        if result or aiowamp.is_message_type(msg, aiowamp.msg.Error):
            self.__result_fut.set_result(msg)
        else:
            self.__result_fut.set_exception(aiowamp.UnexpectedMessageError(msg, aiowamp.msg.Result))

        if self.__progress_queue is not None:
            # add none to wake up
            self.__progress_queue.put_nowait(None)

        return True

    async def __send_call(self) -> None:
        if self.done:
            raise self.__result_fut.exception()

        self._call_sent = True

        try:
            await self.session.send(self._call_msg)
        except Exception as e:
            self.__result_fut.set_exception(e)

    async def __next_final(self) -> Union[aiowamp.msg.Result, aiowamp.msg.Error]:
        if not self._call_sent:
            await self.__send_call()

        return await self.__result_fut

    async def result(self) -> aiowamp.InvocationResult:
        try:
            msg = await self.__next_final()
        except asyncio.CancelledError:
            if not self.cancelled:
                await self.cancel()

            raise

        # TODO raise specific RPCError exception types depending on the error URI
        result_msg = check_message_response(msg, aiowamp.msg.Result)
        return _create_invocation_result(result_msg.args, result_msg.kwargs, result_msg.details)

    async def next_progress(self) -> Optional[aiowamp.InvocationProgress]:
        self.__ensure_receive_progress()

        if not self._call_sent:
            await self.__send_call()

        if self.__progress_queue is None:
            self.__progress_queue = asyncio.Queue()

        if self.__progress_queue.empty() and self.done:
            return None

        # this depends on the fact that None is pushed to the queue.
        # it would be nicer to use asyncio.wait, but this way is
        # "cheaper"
        return await self.__progress_queue.get()

    async def cancel(self, cancel_mode: aiowamp.CancelMode = None, *,
                     options: aiowamp.WAMPDict = None) -> None:
        self.__result_fut.cancel()

        if not self._call_sent:
            log.debug("%s: cancelled before call was sent", self)
            return

        if not cancel_mode:
            cancel_mode = self.__cancel_mode

        options = options or {}
        options["mode"] = cancel_mode

        await self.session.send(aiowamp.msg.Cancel(self._call_msg.request_id, options))
        try:
            await self.__next_final()
        except Exception:
            pass


def _create_invocation_result(args: Optional[aiowamp.WAMPList], kwargs: Optional[aiowamp.WAMPDict],
                              details: aiowamp.WAMPDict, *,
                              cls: Type[aiowamp.InvocationResult] = None) -> aiowamp.InvocationResult:
    cls = cls or aiowamp.InvocationResult
    instance = cls(*(args or ()), **(kwargs or {}))
    instance.details = details

    return instance
