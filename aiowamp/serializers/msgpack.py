import msgpack

import aiowamp
from aiowamp import SerializerABC, build_message_from_list

__all__ = ["MessagePackSerializer"]


class MessagePackSerializer(SerializerABC):
    __slots__ = ()

    def serialize(self, msg: aiowamp.MessageABC) -> bytes:
        return msgpack.packb(msg.to_message_list())

    def deserialize(self, data: bytes) -> aiowamp.MessageABC:
        msg_list = msgpack.unpackb(data)
        return build_message_from_list(msg_list)
