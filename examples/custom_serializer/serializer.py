import aiowamp
import ast


class MySerializer(aiowamp.SerializerABC):
    """This is my beautiful serializer.

    It converts the messages to (hopefully) executable python code.
    """

    def serialize(self, msg: aiowamp.MessageABC) -> bytes:
        return repr(msg.to_message_list()).encode()

    def deserialize(self, data: bytes) -> aiowamp.MessageABC:
        # of course this entire serializer is ridiculous, but at least using
        # literal_eval over eval makes it safe
        raw = ast.literal_eval(data.decode())

        # let aiowamp do the rest.
        return aiowamp.build_message_from_list(raw)
