import asyncio
import logging
from typing import Callable, Optional

import aiowamp

log = logging.getLogger(__name__)

MAGIC_OCTET = b"\x7F"


class RawSocketTransport(aiowamp.TransportABC):
    __slots__ = ("reader", "writer", "serializer",
                 "_msg_queue",
                 "__recv_limit", "__send_limit",
                 "__read_task")

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    serializer: aiowamp.SerializerABC

    _msg_queue: Optional[asyncio.Queue]

    __recv_limit: int
    __send_limit: int

    __read_task: Optional[asyncio.Task]

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter,
                 serializer: aiowamp.SerializerABC, *,
                 recv_limit: int,
                 send_limit: int) -> None:
        self.reader = reader
        self.writer = writer
        self.serializer = serializer

        self._msg_queue = None

        self.__recv_limit = recv_limit
        self.__send_limit = send_limit

        self.__read_task = None

    def start(self) -> None:
        if self.__read_task and not self.__read_task.done():
            raise RuntimeError("read loop already running!")

        loop = asyncio.get_event_loop()
        if not loop.is_running():
            raise RuntimeError("cannot start read loop. Event loop isn't running")

        self.__read_task = loop.create_task(self.__read_loop())

    async def close(self) -> None:
        log.debug("%s: closing", self)
        self.writer.close()
        await self.writer.wait_closed()

    async def send(self, msg: aiowamp.MessageABC) -> None:
        data = self.serializer.serialize(msg)
        if len(data) > self.__send_limit:
            # TODO raise
            raise Exception

        header = b"\x00" + int_to_bytes(len(data))
        if log.isEnabledFor(logging.DEBUG):
            log.debug("%s writing header: %s", header.hex())

        self.writer.write(header)
        self.writer.write(data)
        await self.writer.drain()

    async def __read_once(self) -> None:
        header = await self.reader.readexactly(4)
        length = bytes_to_int(header[1:])
        if length > self.__recv_limit:
            await self.close()
            # TODO raise
            raise Exception

        t_type = header[0]
        # regular WAMP message
        if t_type == 0:
            # read message and add to queue
            data = await self.reader.readexactly(length)
            msg = self.serializer.deserialize(data)
            log.debug("%s: received message: %r", self, msg)
            await self._msg_queue.put(msg)
        # PING
        elif t_type == 1:
            log.debug("%s: received PING, sending PONG", self)
            # send header with t_type = PONG
            self.writer.write(b"\02" + header[1:])
            # echo body
            self.writer.write(await self.reader.readexactly(length))
            await self.writer.drain()
        # PONG
        elif t_type == 2:
            log.debug("%s: received PONG", self)
            # discard body
            await self.reader.readexactly(length)
        else:
            log.warning("%s: received header with unknown op code: %s", self, t_type)
            await self.reader.readexactly(length)

    async def __read_loop(self) -> None:
        self._msg_queue = asyncio.Queue()

        while not (self.reader.at_eof() or self.reader.exception()):
            try:
                await self.__read_once()
            except Exception:
                log.exception("%s: error while reading once", self)

    async def recv(self) -> aiowamp.MessageABC:
        try:
            return await self._msg_queue.get()
        except AttributeError:
            raise RuntimeError("cannot receive message before message loop is started.") from None


def int_to_bytes(i: int) -> bytes:
    """Convert an integer to its WAMP bytes representation.

    Args:
        i: Integer to convert.

    Returns:
        Byte representation.
    """
    return i.to_bytes(3, "big", signed=False)


def bytes_to_int(d: bytes) -> int:
    """Convert the WAMP byte representation to an int.

    Args:
        d: Bytes to convert.

    Returns:
        Integer value.
    """
    return int.from_bytes(d, "big", signed=False)


def byte_limit_to_size(limit: int) -> int:
    return 1 << (limit + 9)


def size_to_byte_limit(recv_limit: int) -> int:
    if recv_limit > 0:
        for l in range(0xf + 1):
            if byte_limit_to_size(l) >= recv_limit:
                return l

    return 0xf


HANDSHAKE_ERROR_CODE_EXCEPTION_MAP = {
    0: aiowamp.TransportError("illegal error code"),
    1: aiowamp.TransportError("serializer unsupported"),
    2: aiowamp.TransportError("maximum message length unacceptable"),
    3: aiowamp.TransportError("use of reserved bits"),
    4: aiowamp.TransportError("maximum connection count reached"),
}

SerializerFactory = Callable[[int], aiowamp.SerializerABC]


async def perform_client_handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                   recv_limit: int, protocol: int, *,
                                   serializer_factory: SerializerFactory,
                                   ) -> RawSocketTransport:
    recv_byte_limit = size_to_byte_limit(recv_limit)

    handshake_data = bytearray(MAGIC_OCTET)
    handshake_data.append((recv_byte_limit & 0xf) << 4 | protocol)
    handshake_data.extend((0, 0))

    writer.write(handshake_data)
    await writer.drain()

    resp = await reader.readexactly(4)
    # use 1-slice to get bytes instead of int
    if resp[0:1] != MAGIC_OCTET:
        raise aiowamp.TransportError("received invalid magic octet while performing handshake. "
                                     f"Expected {MAGIC_OCTET}, got {resp[0]}")

    if resp[2:] != b"\x00\x00":
        raise aiowamp.TransportError("expected 3rd and 4th octet to be all zeroes (reserved). "
                                     f"Saw {resp[2:].hex()}")

    proto_echo = resp[1] & 0xf
    # if the first 4 bits are 0
    if proto_echo == 0:
        error_code = resp[1] >> 4
        try:
            exc = HANDSHAKE_ERROR_CODE_EXCEPTION_MAP[error_code]
        except KeyError:
            raise aiowamp.TransportError(f"unknown error code: {error_code}") from None
        else:
            raise exc
    # router must echo the protocol
    elif proto_echo != protocol:
        raise aiowamp.TransportError("router didn't echo protocol. "
                                     f"Expected {protocol}, got {proto_echo}")

    recv_limit = byte_limit_to_size(recv_byte_limit)
    send_limit = byte_limit_to_size(resp[1] >> 4)

    transport = RawSocketTransport(reader, writer, serializer_factory(protocol),
                                   recv_limit=recv_limit, send_limit=send_limit)

    transport.start()
    return transport


async def connect(serializer: aiowamp.SerializerABC, *,
                  recv_limit: int = 0) -> RawSocketTransport:
    loop = asyncio.get_event_loop()

    reader = asyncio.StreamReader()
    transport, protocol = await loop.create_connection(
        lambda: asyncio.StreamReaderProtocol(reader),
    )
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)

    return await perform_client_handshake(reader, writer, recv_limit, )
