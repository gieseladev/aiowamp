import json

import aiowamp

__all__ = ["JSONSerializer"]


# TODO binary blob

class JSONSerializer(aiowamp.SerializerABC):
    __slots__ = ()

    def serialize(self, msg: aiowamp.MessageABC) -> bytes:
        return json.dumps(msg.to_message_list()).encode()

    def deserialize(self, data: bytes) -> aiowamp.MessageABC:
        msg_list = json.loads(data)
        return aiowamp.build_message_from_list(msg_list)
