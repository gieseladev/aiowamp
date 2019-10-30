import asyncio
from typing import Optional

import aiowamp

MAGIC_OCTET = 0x7F


class RawSocketTransport(aiowamp.TransportABC):
    __slots__ = ("reader", "writer", "serializer",
                 "_msg_queue", "_recv_limit",
                 "__send_limit")

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    serializer: aiowamp.SerializerABC

    _msg_queue: Optional[asyncio.Queue]
    _recv_limit: int

    __send_limit: int

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter,
                 serializer: aiowamp.SerializerABC) -> None:
        self.reader = reader
        self.writer = writer
        self.serializer = serializer

        self._msg_queue = None

    async def close(self) -> None:
        self.writer.close()

    async def send(self, msg: aiowamp.MessageABC) -> None:
        data = self.serializer.serialize(msg)
        if len(data) > self.__send_limit:
            # TODO raise
            raise Exception

        header = b"\00" + int_to_bytes(len(data))
        self.writer.write(header)
        self.writer.write(data)
        await self.writer.drain()

    async def __read_once(self) -> None:
        header = await self.reader.readexactly(4)
        length = bytes_to_int(header[1:])
        if length > self._recv_limit:
            await self.close()
            # TODO raise
            raise Exception

        t_type = header[0]
        # regular WAMP message
        if t_type == 0:
            # read message and add to queue
            data = await self.reader.readexactly(length)
            msg = self.serializer.deserialize(data)
            await self._msg_queue.put(msg)
        # PING
        elif t_type == 1:
            # send header with t_type = PONG
            self.writer.write(b"\02" + header[1:])
            # echo body
            self.writer.write(await self.reader.readexactly(length))
            await self.writer.drain()
        # PONG
        elif t_type == 2:
            # discard body
            await self.reader.readexactly(length)
        else:
            # TODO warning
            await self.reader.readexactly(length)

    async def __read_loop(self) -> None:
        self._msg_queue = asyncio.Queue()

        while True:
            await self.__read_once()

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
