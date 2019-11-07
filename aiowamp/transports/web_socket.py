import ssl
from typing import Dict, Sequence, Tuple, Type, Union, cast, overload

import websockets
from websockets.framing import OP_BINARY, OP_TEXT

import aiowamp

__all__ = ["WebSocketTransport", "connect_web_socket"]


class WebSocketTransport(aiowamp.TransportABC):
    """WAMP Transport over web socket.    """
    __slots__ = ("ws_client", "serializer",
                 "__payload_opcode")

    ws_client: websockets.WebSocketClientProtocol
    """Underlying web socket client."""

    serializer: aiowamp.SerializerABC
    """Serializer used for the transport."""

    __payload_opcode: int

    def __init__(self, ws_client: websockets.WebSocketClientProtocol, serializer: aiowamp.SerializerABC, *,
                 payload_text: bool) -> None:
        """
        Args:
            ws_client: Connected web socket client to use.
            serializer: Serializer to use.
            payload_text: Whether the serialised messages should be sent in a text
                frame. If `False`, binary frames are used.
        """
        self.ws_client = ws_client
        self.serializer = serializer

        self.__payload_opcode = OP_TEXT if payload_text else OP_BINARY

    async def close(self) -> None:
        await self.ws_client.close()

    async def send(self, msg: aiowamp.MessageABC) -> None:
        await self.ws_client.write_frame(True, self.__payload_opcode, self.serializer.serialize(msg))

    async def recv(self) -> aiowamp.MessageABC:
        msg = await self.ws_client.recv()
        if isinstance(msg, str):
            msg = msg.encode()

        return self.serializer.deserialize(msg)


async def _connect(uri: str,
                   serializer: Union[aiowamp.SerializerABC, Sequence[aiowamp.SerializerABC]] = None,
                   *,
                   ssl_context: ssl.SSLContext = None) -> WebSocketTransport:
    if isinstance(serializer, aiowamp.SerializerABC):
        proto_map = build_protocol_map(serializer)
    elif not serializer:
        proto_map = build_all_protocol_map()
    else:
        proto_map = build_protocol_map(*serializer)

    client = await websockets.connect(
        uri,
        subprotocols=cast(Tuple[websockets.Subprotocol], tuple(proto_map)),
        ssl=ssl_context,
    )

    assert client.subprotocol is not None

    # get the chosen protocol
    serializer, is_text = proto_map[client.subprotocol]

    return WebSocketTransport(
        client, serializer,
        payload_text=is_text,
    )


@aiowamp.register_transport_factory("ws", "wss", "http", "https")
async def _connect_config(config: aiowamp.CommonTransportConfig) -> WebSocketTransport:
    url = config.url
    # switch to corresponding ws
    if url.scheme.startswith("http"):
        url = url._replace(scheme="ws" + url.scheme[4:])

    return await _connect(str(url), config.serializer,
                          ssl_context=config.ssl_context)


@overload
async def connect_web_socket(config: aiowamp.CommonTransportConfig) -> WebSocketTransport:
    """Connect to a router using web socket transport.

    Args:
        config: The common transport config.

    Returns:
        An open websocket transport.
    """
    ...


@overload
async def connect_web_socket(uri: str,
                             serializer: Union[aiowamp.SerializerABC, Sequence[aiowamp.SerializerABC]] = None,
                             *,
                             ssl_context: ssl.SSLContext = None) -> WebSocketTransport:
    """Connect to a router using web socket transport.

    Args:
        uri: URI to connect_raw_socket to.
        serializer: Serializer to use. Accepts a sequence of serializers in
            order of preference which will be used during negotiation.
            `None` or an empty sequence will accept all known serializers.
        ssl_context: Enforce custom SSL context options. If set, the uri must
            use a scheme supporting TLS.

    Returns:
        An open websocket transport.
    """
    ...


async def connect_web_socket(*args, **kwargs) -> WebSocketTransport:
    if args and isinstance(args[0], aiowamp.CommonTransportConfig):
        return await _connect_config(*args, **kwargs)

    return await _connect(*args, **kwargs)


# TODO improve this part

def build_protocol_map(*serializers: aiowamp.SerializerABC) \
        -> Dict[str, Tuple[aiowamp.SerializerABC, bool]]:
    protocols = {}
    for serializer in serializers:
        proto, is_text = _get_serializer_sub_protocol(serializer)
        protocols[proto] = (serializer, is_text)

    return protocols


def build_all_protocol_map() -> Dict[str, Tuple[aiowamp.SerializerABC, bool]]:
    return build_protocol_map(*(proto() for proto in _BUILTIN_PROTOCOLS))


ProtoTuple = Tuple[str, bool]
"""Type of a protocol tuple.

2-tuple containing the sub protocol and a bool denoting whether the data should 
be sent over a web socket text frame.
"""

_BUILTIN_PROTOCOLS: Dict[Type[aiowamp.SerializerABC], ProtoTuple] = {
    aiowamp.serializers.JSONSerializer: ("wamp.2.json", True),
    aiowamp.serializers.MessagePackSerializer: ("wamp.2.msgpack", False),
}


def _get_serializer_sub_protocol(serializer: aiowamp.SerializerABC) -> ProtoTuple:
    return _BUILTIN_PROTOCOLS[type(serializer)]
