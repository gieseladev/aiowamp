import asyncio
from typing import Any, List

import aiowamp

CLOSE_SENTINEL = object()


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

    @property
    def open(self) -> bool:
        return not self._closed

    async def close(self) -> None:
        assert not self._closed, "already closed"
        self._closed = True
        self.receive_queue.put_nowait(CLOSE_SENTINEL)

    async def send(self, msg: aiowamp.MessageABC) -> None:
        assert not self._closed, "already closed"
        self.sent_messages.append(msg)
        self.send_queue.put_nowait(msg)

    def mock_receive(self, *msgs: aiowamp.MessageABC) -> None:
        for msg in msgs:
            self.receive_queue.put_nowait(msg)

    async def recv(self) -> aiowamp.MessageABC:
        assert not self._closed, "already closed"
        msg = await self.receive_queue.get()
        if msg is CLOSE_SENTINEL:
            raise Exception("closed")

        return msg


def make_dummy_session(details: aiowamp.WAMPDict = None) -> aiowamp.Session:
    return aiowamp.Session(DummyTransport(), 0, "dummy", details or {})


def get_transport_from_session(s: aiowamp.SessionABC) -> DummyTransport:
    assert isinstance(s, aiowamp.Session), "invalid session type"

    transport = s.transport
    assert isinstance(transport, DummyTransport), "invalid transport"

    return transport


def make_dummy_client(session: aiowamp.SessionABC = None, *,
                      session_details: aiowamp.WAMPDict = None) -> aiowamp.Client:
    session = session or make_dummy_session(session_details)
    c = aiowamp.Client(session)
    # we don't want to clean up!
    session._Session__receive_task.cancel()

    return c


def get_transport_from_client(c: aiowamp.ClientABC) -> DummyTransport:
    assert isinstance(c, aiowamp.Client), "invalid client type"
    return get_transport_from_session(c.session)


def make_dummy_invocation(msg: aiowamp.msg.Invocation = None, procedure: str = "test_procedure", *,
                          progress: bool = True,
                          details: aiowamp.WAMPDict = None,
                          args: aiowamp.WAMPList = None,
                          kwargs: aiowamp.WAMPDict = None,
                          session_details: aiowamp.WAMPDict = None,
                          session: aiowamp.SessionABC = None) -> aiowamp.Invocation:
    details = details or {"receive_progress": progress}
    msg = msg or aiowamp.msg.Invocation(0, 0, details, args, kwargs)

    client = make_dummy_client(session, session_details=session_details)
    return aiowamp.Invocation(client.session, client, msg,
                              procedure=aiowamp.URI.cast(procedure))


def get_transport_from_invocation(i: aiowamp.InvocationABC) -> DummyTransport:
    assert isinstance(i, aiowamp.Invocation)
    return get_transport_from_session(i.session)


def make_dummy_subscription_event(msg: aiowamp.msg.Invocation = None, topic: str = "test_procedure", *,
                                  details: aiowamp.WAMPDict = None,
                                  args: aiowamp.WAMPList = None,
                                  kwargs: aiowamp.WAMPDict = None,
                                  session_details: aiowamp.WAMPDict = None,
                                  session: aiowamp.SessionABC = None) -> aiowamp.SubscriptionEvent:
    details = details or {}
    msg = msg or aiowamp.msg.Event(0, 0, details, args, kwargs)

    return aiowamp.SubscriptionEvent(make_dummy_client(session, session_details=session_details), msg,
                                     topic=aiowamp.URI.cast(topic))


def get_transport_from_subscription_event(e: aiowamp.SubscriptionEventABC) -> DummyTransport:
    assert isinstance(e, aiowamp.SubscriptionEvent)
    return get_transport_from_client(e.client)


def get_transport(o: Any) -> DummyTransport:
    if isinstance(o, DummyTransport): return o
    if isinstance(o, aiowamp.SessionABC): return get_transport_from_session(o)
    if isinstance(o, aiowamp.ClientABC): return get_transport_from_client(o)
    if isinstance(o, aiowamp.InvocationABC): return get_transport_from_invocation(o)
    if isinstance(o, aiowamp.SubscriptionEventABC): return get_transport_from_subscription_event(o)

    raise TypeError("can't get dummy transport", o)


def mock_receive_message(o: Any, *msgs: aiowamp.MessageABC):
    get_transport(o).mock_receive(*msgs)


def get_messages(o: Any) -> List[aiowamp.MessageABC]:
    return get_transport(o).sent_messages


async def get_next_message(o: Any) -> aiowamp.MessageABC:
    return await get_transport(o).send_queue.get()
