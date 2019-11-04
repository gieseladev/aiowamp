from __future__ import annotations

import asyncio
import logging
from typing import Optional, Union

import aiowamp
from .abstract import CallABC
from .utils import check_message_response

__all__ = ["Call"]

log = logging.getLogger(__name__)


class Call(CallABC):
    __slots__ = ("session",
                 "_call_msg", "_call_sent",
                 "__cancel_mode",
                 "__result_fut", "__progress_queue")

    session: aiowamp.SessionABC
    _call_msg: aiowamp.msg.Call
    _call_sent: bool

    __cancel_mode: aiowamp.CancelMode

    __result_fut: asyncio.Future
    __progress_queue: Optional[asyncio.Queue]

    def __init__(self, session: aiowamp.SessionABC, call: aiowamp.msg.Call, *,
                 cancel_mode: aiowamp.CancelMode) -> None:
        self.session = session
        self._call_msg = call
        self._call_sent = False

        self.__cancel_mode = cancel_mode

        loop = asyncio.get_event_loop()
        assert loop.is_running(), "loop isn't running"

        self.__result_fut = loop.create_future()
        self.__progress_queue = None

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

    def kill(self, e: Exception) -> None:
        if self.done:
            return

        self.__result_fut.set_exception(e)
        if self.__progress_queue is not None:
            self.__progress_queue.put_nowait(None)

    def handle_response(self, msg: aiowamp.MessageABC) -> bool:
        result = aiowamp.message_as_type(msg, aiowamp.msg.Result)
        if result and result.details.get("progress"):
            if self.__progress_queue is not None:
                self.__progress_queue.put_nowait(result)

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
        self.__progress_queue = asyncio.Queue()

        try:
            await self.session.send(self._call_msg)
        except Exception as e:
            self.__result_fut.set_exception(e)

    async def __next_final(self) -> Union[aiowamp.msg.Result, aiowamp.msg.Error]:
        if not self._call_sent:
            await self.__send_call()

        return await self.__result_fut

    async def __next_progress(self) -> Optional[aiowamp.msg.Result]:
        if not self._call_sent:
            await self.__send_call()

        if self.__progress_queue.empty() and self.done:
            return None

        # this depends on the fact that None is pushed to the queue.
        # it would be nicer to use asyncio.wait, but this way is
        # "cheaper"
        return await self.__progress_queue.get()

    async def result(self) -> aiowamp.msg.Result:
        try:
            msg = await self.__next_final()
        except asyncio.CancelledError:
            if not self.cancelled:
                await self.cancel()

            raise

        # TODO raise proper exception
        check_message_response(msg, aiowamp.msg.Result)

        return msg

    async def next_progress(self) -> Optional[aiowamp.msg.Result]:
        return await self.__next_progress()

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
