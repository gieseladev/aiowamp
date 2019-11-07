import asyncio
import logging
import ssl
import urllib.parse as urlparse
from typing import Dict, Optional, Type, Union

import aiowamp

__all__ = ["RawSocketTransport", "connect_raw_socket"]

log = logging.getLogger(__name__)

MAGIC_OCTET = b"\x7F"
"""Magic bytes sent as the first octet of the handshake."""


class RawSocketTransport(aiowamp.TransportABC):
    """WAMP transport over raw sockets.

    Notes:
        The `start` method needs to be called before `recv` can read any messages.
        This is done as part of the `perform_client_handshake` procedure.
    """
    __slots__ = ("reader", "writer", "serializer",
                 "_msg_queue",
                 "__recv_limit", "__send_limit",
                 "__read_task")

    reader: asyncio.StreamReader
    """Reader for the underlying stream."""

    writer: asyncio.StreamWriter
    """Writer for the underlying transport."""

    serializer: aiowamp.SerializerABC
    """Serializer used to serialise messages."""

    _msg_queue: Optional[asyncio.Queue]

    __recv_limit: int
    __send_limit: int

    __read_task: Optional[asyncio.Task]

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter,
                 serializer: aiowamp.SerializerABC, *,
                 recv_limit: int,
                 send_limit: int) -> None:
        """
        Args:
            reader: Reader to read from.
            writer: Writer to write to.
            serializer: Serializer to use.
            recv_limit: Max amount of bytes willing to receive.
            send_limit: Max amount of bytes remote is willing to receive.

        See Also:
            The `connect_raw_socket` method for opening a connection.
        """
        self.reader = reader
        self.writer = writer
        self.serializer = serializer

        self._msg_queue = None

        self.__recv_limit = recv_limit
        self.__send_limit = send_limit

        self.__read_task = None

    def __repr__(self) -> str:
        return f"RawSocketTransport(reader={self.reader!r},writer={self.writer!r}," \
               f"serializer={self.serializer!r},recv_limit={self.__recv_limit!r}," \
               f"send_limit={self.__send_limit!r})"

    def start(self) -> None:
        if self.__read_task and not self.__read_task.done():
            raise RuntimeError("read loop already running!")

        self._msg_queue = asyncio.Queue()
        self.__read_task = asyncio.create_task(self.__read_loop())

    async def close(self) -> None:
        log.debug("%s: closing", self)
        self.writer.close()
        await self.writer.wait_closed()

    async def send(self, msg: aiowamp.MessageABC) -> None:
        log.debug("%s: sending: %r", self, msg)

        data = self.serializer.serialize(msg)
        if len(data) > self.__send_limit:
            raise aiowamp.TransportError("message longer than remote is willing to receive")

        header = b"\x00" + int_to_bytes(len(data))

        if log.isEnabledFor(logging.DEBUG):
            log.debug("%s: writing header: %s", self, header.hex())
            import binascii
            log.debug("%s: writing data: %s", self, binascii.b2a_base64(data))

        self.writer.write(header)
        self.writer.write(data)
        await self.writer.drain()

    async def __read_once(self) -> None:
        assert self._msg_queue

        try:
            header = await self.reader.readexactly(4)
        except asyncio.IncompleteReadError:
            return

        length = bytes_to_int(header[1:])
        if length > self.__recv_limit:
            await self.close()
            raise aiowamp.TransportError("received message bigger than receive limit")

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
        log.debug("%s: starting read loop", self)

        while not (self.reader.at_eof() or self.reader.exception()):
            try:
                await self.__read_once()
            except Exception:
                log.exception("%s: error while reading once", self)

        log.debug("%s: exiting read loop", self)

    async def recv(self) -> aiowamp.MessageABC:
        try:
            return await self._msg_queue.get()  # type: ignore
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


HANDSHAKE_ERRCODE_EXCEPTIONS = {
    0: aiowamp.TransportError("illegal error code"),
    1: aiowamp.TransportError("serializer unsupported"),
    2: aiowamp.TransportError("maximum message length unacceptable"),
    3: aiowamp.TransportError("use of reserved bits"),
    4: aiowamp.TransportError("maximum connection count reached"),
}


async def perform_client_handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                   recv_limit: int, protocol: int, *,
                                   serializer: aiowamp.SerializerABC,
                                   ) -> RawSocketTransport:
    """Perform the raw socket client handshake and establish the transport.

    Args:
        reader: Reader to read from.
        writer: Writer to write to.
        recv_limit: Receive limit in bytes.
        protocol: Serialization protocol to use.
        serializer: Serializer to use for the transport.

    Returns:
        Established raw socket transport.

    Raises:
        aiowamp.TransportError: When the handshake fails.
    """
    recv_byte_limit = size_to_byte_limit(recv_limit)

    handshake_data = bytearray(MAGIC_OCTET)
    handshake_data.append((recv_byte_limit & 0xf) << 4 | protocol)
    handshake_data.extend((0, 0))

    if log.isEnabledFor(logging.DEBUG):
        log.debug("sending handshake: %s", handshake_data.hex())

    writer.write(handshake_data)
    await writer.drain()

    try:
        resp = await reader.readexactly(4)
    except asyncio.IncompleteReadError as e:
        raise aiowamp.TransportError("remote closed connection during handshake") from e

    if log.isEnabledFor(logging.DEBUG):
        log.debug("received handshake response: %s", resp.hex())

    # use 1-slice to get bytes instead of int
    if resp[0:1] != MAGIC_OCTET:
        raise aiowamp.TransportError("received invalid magic octet while performing handshake. "
                                     f"Expected {MAGIC_OCTET!r}, got {resp[0]}")

    if resp[2:] != b"\x00\x00":
        raise aiowamp.TransportError("expected 3rd and 4th octet to be all zeroes (reserved). "
                                     f"Saw {resp[2:].hex()}")

    proto_echo = resp[1] & 0xf
    # if the first 4 bits are 0 it's an error response
    if proto_echo == 0:
        error_code = resp[1] >> 4
        try:
            exc = HANDSHAKE_ERRCODE_EXCEPTIONS[error_code]
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

    transport = RawSocketTransport(reader, writer, serializer,
                                   recv_limit=recv_limit, send_limit=send_limit)

    transport.start()
    return transport


def is_secure_scheme(scheme: str) -> bool:
    """Check if the given scheme is secure.

    Args:
        scheme: Scheme to check

    Returns:
        Whether the scheme is secure.
    """
    return scheme in {"tcps", "tcp4s", "tcp6s", "rss"}


async def _connect(url: Union[str, urlparse.ParseResult], serializer: aiowamp.SerializerABC, *,
                   ssl_context: Union[ssl.SSLContext, bool] = None,
                   recv_limit: int = 0) -> RawSocketTransport:
    """Connect to a WAMP router over raw socket.

    Args:
        url: URL of the router.
        serializer: Serializer to use.
        ssl_context: Set custom SSL context options.
        recv_limit: Receive limit in bytes.
            Defaults to the max size of 16mb.

    Returns:
        THe connected raw socket transport.
    """
    if not isinstance(url, urlparse.ParseResult):
        url = urlparse.urlparse(url)

    if is_secure_scheme(url.scheme):
        if not ssl_context:
            # create default ssl context
            ssl_context = True
    elif ssl_context:
        raise ValueError(f"SSL context specified for a uri which doesn't use TLS: {url.scheme!r}.")

    reader = asyncio.StreamReader()

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_connection(
        lambda: asyncio.StreamReaderProtocol(reader),
        host=url.hostname,
        port=url.port,
        ssl=ssl_context,
    )
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)

    log.debug("performing handshake")
    try:
        return await perform_client_handshake(
            reader, writer, recv_limit, get_serializer_protocol(serializer),
            serializer=serializer,
        )
    except Exception:
        # don't wait for the connection to close
        writer.close()
        raise


@aiowamp.register_transport_factory("tcp", "tcps",
                                    "tcp4", "tcp4s",
                                    "tcp6", "tcp6s",
                                    "rs", "rss")
async def _connect_config(config: aiowamp.CommonTransportConfig) -> RawSocketTransport:
    return await _connect(config.url, config.serializer or aiowamp.JSONSerializer(),
                          ssl_context=config.ssl_context)


async def connect_raw_socket(*args, **kwargs) -> RawSocketTransport:
    if args and isinstance(args[0], aiowamp.CommonTransportConfig):
        return await _connect_config(*args, **kwargs)

    return await _connect(*args, **kwargs)


_BUILTIN_PROTOCOLS: Dict[Type[aiowamp.SerializerABC], int] = {
    aiowamp.serializers.JSONSerializer: 1,
    aiowamp.serializers.MessagePackSerializer: 2,
}


def get_serializer_protocol(serializer: aiowamp.SerializerABC) -> int:
    return _BUILTIN_PROTOCOLS[type(serializer)]
