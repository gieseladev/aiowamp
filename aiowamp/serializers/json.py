import base64
import json
from typing import Any, ByteString, Iterable, Optional, Tuple

import aiowamp

__all__ = ["JSONSerializer", "JSONDecoder", "JSONEncoder"]


class JSONSerializer(aiowamp.SerializerABC):
    """Serializer for the JSON format."""
    __slots__ = ("decoder", "encoder")

    decoder: json.JSONDecoder
    """JSON decoder used to decode incoming messages."""

    encoder: json.JSONEncoder
    """JSON encoder used to encode outgoing messages."""

    def __init__(self, *,
                 decoder: json.JSONDecoder = None,
                 encoder: json.JSONEncoder = None) -> None:
        """
        Args:
            decoder: Decoder to be used. Defaults to `JSONDecoder` which supports
                binary data in strings.

            encoder: Encoder to be used. Defaults to `JSONEncoder` which supports
                binary data in strings.
        """
        self.decoder = decoder or JSONDecoder()
        self.encoder = encoder or JSONEncoder(check_circular=False)

    def serialize(self, msg: aiowamp.MessageABC) -> bytes:
        return self.encoder.encode(msg.to_message_list()).encode()

    def deserialize(self, data: bytes) -> aiowamp.MessageABC:
        msg_list = self.decoder.decode(data.decode())
        return aiowamp.build_message_from_list(msg_list)


def is_encoded_bytes(s: str) -> bool:
    """Check if the given string contains encoded binary data.

    Args:
        s: String to check.

    Returns:
        Whether the given string holds encoded binary data.
    """
    return s.startswith("\0")


def encode_bytes(b: ByteString) -> str:
    """Encode the binary data to a string.

    Args:
        b: Binary data to encode.

    Returns:
        WAMP JSON string representation of the binary data.
    """
    e = b"\0" + base64.b64encode(b)
    return e.decode()


def decode_bytes(s: str) -> bytes:
    """Decode the bytes.

    Args:
        s: Encoded binary content.

    Returns:
        Decoded binary data.

    Raises:
        binascii.Error: If the data isn't valid.
    """
    return base64.b64decode(s[1:])


def _get_item_iter(v: Any) -> Optional[Iterable[Tuple[Any, Any]]]:
    """Get a key-value iterable for the given object.

    Args:
        v: Any JSON object.

    Returns:
        An iterable which yields 2-tuples where the first element is the index
        value and the second element is the value. `None`, if the given object
        isn't a container.
    """
    if isinstance(v, list):
        return enumerate(v)
    if isinstance(v, dict):
        return v.items()

    return None


def decode_bytes_in_json_obj(v: Any) -> Any:
    """Decode nested bytes in the given object.

    If the given object is a container type it WILL BE MUTATED DIRECTLY.

    Args:
        v: Any JSON object.

    Returns:
        Same object with binary data decoded.
    """
    if isinstance(v, str):
        if is_encoded_bytes(v):
            return decode_bytes(v)

        return v

    item_iter = _get_item_iter(v)
    if not item_iter:
        return v

    stack = [(v, item_iter)]
    while stack:
        container, item_iter = stack.pop()

        for key, value in item_iter:
            if isinstance(value, str):
                if is_encoded_bytes(value):
                    container[key] = decode_bytes(value)

                continue

            sub_item_iter = _get_item_iter(value)
            if sub_item_iter:
                stack.append((value, sub_item_iter))

    return v


class JSONDecoder(json.JSONDecoder):
    """JSONDecoder with support for binary data."""
    __slots__ = ()

    def raw_decode(self, s, idx=0) -> Tuple[Any, int]:
        decoded, end = super().raw_decode(s, idx)
        return decode_bytes_in_json_obj(decoded), end


class JSONEncoder(json.JSONEncoder):
    """JSONEncoder with support for binary data.

    Treats all `ByteString` types as binary data.
    """
    __slots__ = ()

    def default(self, o: Any) -> Any:
        if isinstance(o, ByteString):
            return encode_bytes(o)

        return super().default(o)
