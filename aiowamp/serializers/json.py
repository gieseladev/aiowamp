import aiowamp
import json


# TODO binary blob

class JSONSerializer(aiowamp.SerializerABC):
    def serialize(self, msg: aiowamp.MessageABC) -> bytes:
        return json.dumps(msg.to_message_list()).encode()

    def deserialize(self, data: bytes) -> aiowamp.MessageABC:
        msg_list = json.loads(data)
        msg_type = msg_list.pop(0)
        return aiowamp.get_message_type(msg_type).from_message_list(msg_list)
