import asyncio
from typing import Any, List

import aiowamp


class DummyTransport(aiowamp.TransportABC):
    receive_queue: asyncio.Queue
    send_queue: asyncio.Queue

    sent_messages: List[aiowamp.MessageABC]
    _closed: bool

    def __init__(self) -> None:
        self._closed = False
        self.receive_queue = asyncio.Queue()
        self.send_queue = asyncio.Queue()

        self.sent_messages = []

    async def close(self) -> None:
        assert not self._closed, "already closed"
        self._closed = True

    async def send(self, msg: aiowamp.MessageABC) -> None:
        assert not self._closed, "already closed"
        self.sent_messages.append(msg)
        self.send_queue.put_nowait(msg)

    def mock_receive(self, *msgs: aiowamp.MessageABC) -> None:
        for msg in msgs:
            self.receive_queue.put_nowait(msg)

    async def recv(self) -> aiowamp.MessageABC:
        assert not self._closed, "already closed"
        return await self.receive_queue.get()


def make_dummy_session(details: aiowamp.WAMPDict = None) -> aiowamp.Session:
    return aiowamp.Session(DummyTransport(), 0, "dummy", details or {})


def get_transport_from_session(s: aiowamp.SessionABC) -> DummyTransport:
    assert isinstance(s, aiowamp.Session), "invalid session type"

    transport = s.transport
    assert isinstance(transport, DummyTransport), "invalid transport"

    return transport


def make_dummy_client(session: aiowamp.SessionABC = None, *,
                      session_details: aiowamp.WAMPDict = None) -> aiowamp.Client:
    return aiowamp.Client(session or make_dummy_session(session_details))


def get_transport_from_client(c: aiowamp.ClientABC) -> DummyTransport:
    assert isinstance(c, aiowamp.Client), "invalid client type"
    return get_transport_from_session(c.session)


def make_dummy_invocation(msg: aiowamp.msg.Invocation = None, *,
                          progress: bool = True,
                          details: aiowamp.WAMPDict = None,
                          args: aiowamp.WAMPList = None,
                          kwargs: aiowamp.WAMPDict = None,
                          session_details: aiowamp.WAMPDict = None,
                          session: aiowamp.SessionABC = None) -> aiowamp.Invocation:
    details = details or {"receive_progress": progress}
    msg = msg or aiowamp.msg.Invocation(0, 0, details, args, kwargs)
    return aiowamp.Invocation(session or make_dummy_session(session_details), msg)


def get_transport_from_invocation(i: aiowamp.InvocationABC) -> DummyTransport:
    assert isinstance(i, aiowamp.Invocation)
    return get_transport_from_session(i.session)


def get_transport(o: Any) -> DummyTransport:
    if isinstance(o, DummyTransport): return o
    if isinstance(o, aiowamp.SessionABC): return get_transport_from_session(o)
    if isinstance(o, aiowamp.ClientABC): return get_transport_from_client(o)
    if isinstance(o, aiowamp.InvocationABC): return get_transport_from_invocation(o)

    raise TypeError("can't get dummy transport", o)


def send_message(o: Any, *msgs: aiowamp.MessageABC):
    get_transport(o).mock_receive(*msgs)


def get_messages(o: Any) -> List[aiowamp.MessageABC]:
    return get_transport(o).sent_messages


async def get_next_message(o: Any) -> aiowamp.MessageABC:
    return await get_transport(o).send_queue.get()
