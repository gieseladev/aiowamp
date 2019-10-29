import aiowamp

MAGIC_OCTET = 0x7F


class RawSocketTransport(aiowamp.TransportABC):
    __slots__ = ()
