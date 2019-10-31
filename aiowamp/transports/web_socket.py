import ssl
from typing import Dict, Sequence, Tuple, Type, Union

import websockets
from websockets.framing import OP_BINARY, OP_TEXT

import aiowamp


class WebSocketTransport(aiowamp.TransportABC):
    """WAMP Transport over web socket.

    Args:
        ws_client: Connected web socket client to use.
        serializer: Serializer to use.
        payload_text: Whether the serialised messages should be sent in a text
            frame. If `False`, binary frames are used.
    """
    __slots__ = ("ws_client", "serializer",
                 "__payload_opcode")

    ws_client: websockets.WebSocketClientProtocol
    """Underlying web socket client."""

    serializer: aiowamp.SerializerABC
    """Serializer used for the transport."""

    __payload_opcode: int

    def __init__(self, ws_client: websockets.WebSocketClientProtocol, serializer: aiowamp.SerializerABC, *,
                 payload_text: bool) -> None:
        self.ws_client = ws_client
        self.serializer = serializer

        self.__payload_opcode = OP_TEXT if payload_text else OP_BINARY

    async def close(self) -> None:
        await self.ws_client.close()

    async def send(self, msg: aiowamp.MessageABC) -> None:
        await self.ws_client.write_frame(True, self.__payload_opcode, self.serializer.serialize(msg))

    async def recv(self) -> aiowamp.MessageABC:
        return self.serializer.deserialize(await self.ws_client.recv())


async def connect(uri: str,
                  serializer: Union[aiowamp.SerializerABC, Sequence[aiowamp.SerializerABC]] = None,
                  *,
                  ssl_context: ssl.SSLContext = None) -> WebSocketTransport:
    """Connect to a router using web socket transport.

    Args:
        uri: URI to connect to.
        serializer: Serializer to use. Accepts a sequence of serializers in
            order of preference which will be used during negotiation.
            `None` or an empty sequence will accept all known serializers.
        ssl_context: Enforce custom SSL context options. If set, the uri must
            use a scheme supporting TLS.

    Returns:
        An open websocket transport.
    """
    if isinstance(serializer, aiowamp.SerializerABC):
        proto_map = build_protocol_map(serializer)
    elif not serializer:
        proto_map = build_all_protocol_map()
    else:
        proto_map = build_protocol_map(*serializer)

    client = await websockets.connect(
        uri,
        subprotocols=tuple(proto_map),
        ssl=ssl_context,
    )

    # get the chosen protocol
    serializer, is_text = proto_map[client.subprotocol]

    return WebSocketTransport(
        client, serializer,
        payload_text=is_text,
    )


# TODO improve this part

def build_protocol_map(*serializers: aiowamp.SerializerABC) \
        -> Dict[websockets.Subprotocol, Tuple[aiowamp.SerializerABC, bool]]:
    protocols = {}
    for serializer in serializers:
        proto, is_text = _get_serializer_sub_protocol(serializer)
        protocols[proto] = (serializer, is_text)

    return protocols


def build_all_protocol_map() -> Dict[websockets.Subprotocol, Tuple[aiowamp.SerializerABC, bool]]:
    return build_protocol_map(*(proto() for proto in _BUILTIN_PROTOCOLS))


ProtoTuple = Tuple[websockets.Subprotocol, bool]

_BUILTIN_PROTOCOLS: Dict[Type[aiowamp.SerializerABC], ProtoTuple] = {
    aiowamp.serializers.JSONSerializer: (websockets.Subprotocol("wamp.2.json"), True),
    aiowamp.serializers.MessagePackSerializer: (websockets.Subprotocol("wamp.2.msgpack"), False),
}


def _get_serializer_sub_protocol(serializer: aiowamp.SerializerABC) -> ProtoTuple:
    return _BUILTIN_PROTOCOLS[type(serializer)]
