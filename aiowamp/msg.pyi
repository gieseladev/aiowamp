from typing import Optional

import aiowamp

__all__ = ["Hello", "Welcome", "Abort", "Challenge", "Hello", "Welcome", "Abort", "Challenge", "Authenticate",
           "Goodbye", "Error", "Publish", "Published", "Subscribe", "Subscribed", "Unsubscribe", "Unsubscribed",
           "Event", "Call", "Cancel", "Result", "Register", "Registered", "Unregister", "Unregistered", "Invocation",
           "Interrupt", "Yield"]


class _StubMessage(aiowamp.MessageABC):

    def to_message_list(self):
        ...

    @classmethod
    def from_message_list(cls, msg_list):
        ...


class Hello(_StubMessage):
    realm: aiowamp.URI
    details: aiowamp.WAMPDict

    def __init__(self, realm: aiowamp.URI, details: aiowamp.WAMPDict) -> None:
        ...


class Welcome(_StubMessage):
    session_id: int
    details: aiowamp.WAMPDict

    def __init__(self, session_id: int, details: aiowamp.WAMPDict) -> None:
        ...


class Abort(_StubMessage):
    details: aiowamp.WAMPDict
    reason: aiowamp.URI

    def __init__(self, details: aiowamp.WAMPDict, reason: aiowamp.URI) -> None:
        ...


class Challenge(_StubMessage):
    auth_method: str
    extra: aiowamp.WAMPDict

    def __init__(self, auth_method: str, extra: aiowamp.WAMPDict) -> None:
        ...


class Authenticate(_StubMessage):
    signature: str
    extra: aiowamp.WAMPDict

    def __init__(self, signature: str, extra: aiowamp.WAMPDict) -> None:
        ...


class Goodbye(_StubMessage):
    details: aiowamp.WAMPDict
    reason: aiowamp.URI

    def __init__(self, details: aiowamp.WAMPDict, reason: aiowamp.URI) -> None:
        ...


class Error(_StubMessage):
    msg_type: int
    request_id: int
    details: aiowamp.WAMPDict
    error: aiowamp.URI
    args: Optional[aiowamp.WAMPList]
    kwargs: Optional[aiowamp.WAMPDict]

    def __init__(self, msg_type: int, request_id: int, details: aiowamp.WAMPDict, error: aiowamp.URI,
                 args: aiowamp.WAMPList = None, kwargs: aiowamp.WAMPDict = None) -> None:
        ...


class Publish(_StubMessage):
    request_id: int
    options: aiowamp.WAMPDict
    topic: aiowamp.URI
    args: Optional[aiowamp.WAMPList]
    kwargs: Optional[aiowamp.WAMPDict]

    def __init__(self, request_id: int, options: aiowamp.WAMPDict, topic: aiowamp.URI,
                 args: aiowamp.WAMPList = None, kwargs: aiowamp.WAMPDict = None) -> None:
        ...


class Published(_StubMessage):
    request_id: int
    publication_id: int

    def __init__(self, request_id: int, publication_id: int) -> None:
        ...


class Subscribe(_StubMessage):
    request_id: int
    options: aiowamp.WAMPDict
    topic: aiowamp.URI

    def __init__(self, request_id: int, options: aiowamp.WAMPDict, topic: aiowamp.URI) -> None:
        ...


class Subscribed(_StubMessage):
    request_id: int
    subscription_id: int

    def __init__(self, request_id: int, subscription_id: int) -> None:
        ...


class Unsubscribe(_StubMessage):
    request_id: int
    subscription_id: int

    def __init__(self, request_id: int, subscription_id: int) -> None:
        ...


class Unsubscribed(_StubMessage):
    request_id: int

    def __init__(self, request_id: int) -> None:
        ...


class Event(_StubMessage):
    subscription_id: int
    publication_id: int
    details: aiowamp.WAMPDict
    args: Optional[aiowamp.WAMPList]
    kwargs: Optional[aiowamp.WAMPDict]

    def __init__(self, subscription_id: int, publication_id: int, details: aiowamp.WAMPDict,
                 args: aiowamp.WAMPList = None, kwargs: aiowamp.WAMPDict = None) -> None:
        ...


class Call(_StubMessage):
    request_id: int
    options: aiowamp.WAMPDict
    procedure: aiowamp.URI
    args: Optional[aiowamp.WAMPList]
    kwargs: Optional[aiowamp.WAMPDict]

    def __init__(self, request_id: int, options: aiowamp.WAMPDict, procedure: aiowamp.URI,
                 args: aiowamp.WAMPList = None, kwargs: aiowamp.WAMPDict = None) -> None:
        ...


class Cancel(_StubMessage):
    request_id: int
    options: aiowamp.WAMPDict

    def __init__(self, request_id: int, options: aiowamp.WAMPDict) -> None:
        ...


class Result(_StubMessage):
    request_id: int
    details: aiowamp.WAMPDict
    args: Optional[aiowamp.WAMPList]
    kwargs: Optional[aiowamp.WAMPDict]

    def __init__(self, request_id: int, details: aiowamp.WAMPDict,
                 args: aiowamp.WAMPList = None, kwargs: aiowamp.WAMPDict = None) -> None:
        ...


class Register(_StubMessage):
    request_id: int
    options: aiowamp.WAMPDict
    procedure: aiowamp.URI

    def __init__(self, request_id: int, options: aiowamp.WAMPDict, procedure: aiowamp.URI) -> None:
        ...


class Registered(_StubMessage):
    request_id: int
    registration_id: int

    def __init__(self, request_id: int, registration_id: int) -> None:
        ...


class Unregister(_StubMessage):
    request_id: int
    registration_id: int

    def __init__(self, request_id: int, registration_id: int) -> None:
        ...


class Unregistered(_StubMessage):
    request_id: int

    def __init__(self, request_id: int) -> None:
        ...


class Invocation(_StubMessage):
    request_id: int
    registration_id: int
    details: aiowamp.WAMPDict
    args: Optional[aiowamp.WAMPList]
    kwargs: Optional[aiowamp.WAMPDict]

    def __init__(self, request_id: int, registration_id: int, details: aiowamp.WAMPDict,
                 args: aiowamp.WAMPList = None, kwargs: aiowamp.WAMPDict = None) -> None:
        ...


class Interrupt(_StubMessage):
    request_id: int
    options: aiowamp.WAMPDict

    def __init__(self, request_id: int, options: aiowamp.WAMPDict) -> None:
        ...


class Yield(_StubMessage):
    request_id: int
    options: aiowamp.WAMPDict
    args: Optional[aiowamp.WAMPList]
    kwargs: Optional[aiowamp.WAMPDict]

    def __init__(self, request_id: int, options: aiowamp.WAMPDict,
                 args: aiowamp.WAMPList = None, kwargs: aiowamp.WAMPDict = None) -> None:
        ...
