import aiowamp


# TODO maybe build a transport which interacts with the console

class MyTransport(aiowamp.TransportABC):
    @property
    def open(self) -> bool:
        return True

    async def close(self) -> None:
        ...

    async def send(self, msg: aiowamp.MessageABC) -> None:
        ...

    async def recv(self) -> aiowamp.MessageABC:
        ...


@aiowamp.register_transport_factory()
async def connect(config: aiowamp.CommonTransportConfig) -> MyTransport:
    return MyTransport()
