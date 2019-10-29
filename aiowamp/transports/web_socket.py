import websockets

import aiowamp


class WebSocketTransport(aiowamp.TransportABC):
    __slots__ = ("ws_client", "serializer")

    ws_client: websockets.WebSocketClientProtocol
    serializer: aiowamp.SerializerABC

    async def close(self) -> None:
        await self.ws_client.close()

    async def send(self, msg: aiowamp.MessageABC) -> None:
        await self.ws_client.send(self.serializer.serialize(msg))

    async def recv(self) -> aiowamp.MessageABC:
        return self.serializer.deserialize(await self.ws_client.recv())
