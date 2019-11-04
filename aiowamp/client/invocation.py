import contextlib
from typing import Tuple

import aiowamp
from .abstract import InvocationABC

__all__ = ["Invocation"]


class Invocation(InvocationABC):
    __slots__ = ("session",
                 "_done",
                 "__request_id",
                 "__args", "__kwargs", "__details")

    session: aiowamp.SessionABC
    _done: bool

    __request_id: int

    __args: Tuple[aiowamp.WAMPType, ...]
    __kwargs: aiowamp.WAMPDict
    __details: aiowamp.WAMPDict

    def __init__(self, session: aiowamp.SessionABC, msg: aiowamp.msg.Invocation) -> None:
        self.session = session
        self._done = False

        self.__request_id = msg.request_id
        self.__args = tuple(msg.args)
        self.__kwargs = msg.kwargs
        self.__details = msg.details

    @property
    def request_id(self) -> int:
        return self.__request_id

    @property
    def args(self) -> Tuple[aiowamp.WAMPType, ...]:
        return self.__args

    @property
    def kwargs(self) -> aiowamp.WAMPDict:
        return self.__kwargs

    @property
    def details(self) -> aiowamp.WAMPDict:
        return self.__details

    def __assert_not_done(self) -> None:
        if self._done:
            raise RuntimeError(f"{self}: already completed")

    def __mark_done(self) -> None:
        self.__assert_not_done()
        self._done = True

    async def send_progress(self, *args: aiowamp.WAMPType,
                            kwargs: aiowamp.WAMPDict = None,
                            options: aiowamp.WAMPDict = None) -> None:
        self.__assert_not_done()

        if not self.may_send_progress:
            raise RuntimeError(f"{self}: caller is unwilling to receive progress")

        options = options or {}
        options["progress"] = True

        await self.session.send(aiowamp.msg.Yield(
            self.__request_id,
            options,
            list(args) or None,
            kwargs,
        ))

    async def send_result(self, *args: aiowamp.WAMPType,
                          kwargs: aiowamp.WAMPDict = None,
                          options: aiowamp.WAMPDict = None) -> None:
        self.__mark_done()

        if options:
            # make sure we're not accidentally sending a result with progress=True
            with contextlib.suppress(KeyError):
                del options["progress"]
        else:
            options = {}

        await self.session.send(aiowamp.msg.Yield(
            self.__request_id,
            options,
            list(args) or None,
            kwargs,
        ))

    async def send_error(self, error: str, *args: aiowamp.WAMPType,
                         kwargs: aiowamp.WAMPDict = None,
                         details: aiowamp.WAMPDict = None) -> None:
        self.__mark_done()

        await self.session.send(aiowamp.msg.Error(
            aiowamp.msg.Invocation.message_type,
            self.__request_id,
            details or {},
            aiowamp.URI(error),
            list(args) or None,
            kwargs,
        ))
