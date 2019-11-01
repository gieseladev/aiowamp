import msgpack

import aiowamp

__all__ = ["MessagePackSerializer"]


class MessagePackSerializer(aiowamp.SerializerABC):
    __slots__ = ()

    def serialize(self, msg: aiowamp.MessageABC) -> bytes:
        return msgpack.packb(msg.to_message_list())

    def deserialize(self, data: bytes) -> aiowamp.MessageABC:
        msg_list = msgpack.unpackb(data)
        return aiowamp.build_message_from_list(msg_list)
