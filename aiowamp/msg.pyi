from typing import Optional

from aiowamp import MessageABC, URI, WAMPDict, WAMPList

__all__ = ["Hello", "Welcome", "Abort", "Challenge", "Hello", "Welcome", "Abort", "Challenge", "Authenticate",
           "Goodbye", "Error", "Publish", "Published", "Subscribe", "Subscribed", "Unsubscribe", "Unsubscribed",
           "Event", "Call", "Cancel", "Result", "Register", "Registered", "Unregister", "Unregistered", "Invocation",
           "Interrupt", "Yield"]


class Hello(MessageABC):
    realm: URI
    details: WAMPDict

    def __init__(self, realm: URI, details: WAMPDict) -> None:
        ...


class Welcome(MessageABC):
    session_id: int
    details: WAMPDict

    def __init__(self, session_id: int, details: WAMPDict) -> None:
        ...


class Abort(MessageABC):
    details: WAMPDict
    reason: URI

    def __init__(self, details: WAMPDict, reason: URI) -> None:
        ...


class Challenge(MessageABC):
    auth_method: str
    extra: WAMPDict

    def __init__(self, auth_method: str, extra: WAMPDict) -> None:
        ...


class Authenticate(MessageABC):
    signature: str
    extra: WAMPDict

    def __init__(self, signature: str, extra: WAMPDict) -> None:
        ...


class Goodbye(MessageABC):
    details: WAMPDict
    reason: URI

    def __init__(self, details: WAMPDict, reason: URI) -> None:
        ...


class Error(MessageABC):
    msg_type: int
    request_id: int
    details: WAMPDict
    error: URI
    args: Optional[WAMPList]
    kwargs: Optional[WAMPDict]

    def __init__(self, msg_type: int, request_id: int, details: WAMPDict, error: URI,
                 args: WAMPList = None, kwargs: WAMPDict = None) -> None:
        ...


class Publish(MessageABC):
    request_id: int
    options: WAMPDict
    topic: URI
    args: Optional[WAMPList]
    kwargs: Optional[WAMPDict]

    def __init__(self, request_id: int, options: WAMPDict, topic: URI,
                 args: WAMPList = None, kwargs: WAMPDict = None) -> None:
        ...


class Published(MessageABC):
    request_id: int
    publication_id: int

    def __init__(self, request_id: int, publication_id: int) -> None:
        ...


class Subscribe(MessageABC):
    request_id: int
    options: WAMPDict
    topic: URI

    def __init__(self, request_id: int, options: WAMPDict, topic: URI) -> None:
        ...


class Subscribed(MessageABC):
    request_id: int
    subscription_id: int

    def __init__(self, request_id: int, subscription_id: int) -> None:
        ...


class Unsubscribe(MessageABC):
    request_id: int
    subscription_id: int

    def __init__(self, request_id: int, subscription_id: int) -> None:
        ...


class Unsubscribed(MessageABC):
    request_id: int

    def __init__(self, request_id: int) -> None:
        ...


class Event(MessageABC):
    subscription_id: int
    publication_id: int
    details: WAMPDict
    args: Optional[WAMPList]
    kwargs: Optional[WAMPDict]

    def __init__(self, subscription_id: int, publication_id: int, details: WAMPDict,
                 args: WAMPList = None, kwargs: WAMPDict = None) -> None:
        ...


class Call(MessageABC):
    request_id: int
    options: WAMPDict
    procedure: URI
    args: Optional[WAMPList]
    kwargs: Optional[WAMPDict]

    def __init__(self, request_id: int, options: WAMPDict, procedure: URI,
                 args: WAMPList = None, kwargs: WAMPDict = None) -> None:
        ...


class Cancel(MessageABC):
    request_id: int
    options: WAMPDict

    def __init__(self, request_id: int, options: WAMPDict) -> None:
        ...


class Result(MessageABC):
    request_id: int
    details: WAMPDict
    args: Optional[WAMPList]
    kwargs: Optional[WAMPDict]

    def __init__(self, request_id: int, details: WAMPDict,
                 args: WAMPList = None, kwargs: WAMPDict = None) -> None:
        ...


class Register(MessageABC):
    request_id: int
    options: WAMPDict
    procedure: URI

    def __init__(self, request_id: int, options: WAMPDict, procedure: URI) -> None:
        ...


class Registered(MessageABC):
    request_id: int
    registration_id: int

    def __init__(self, request_id: int, registration_id: int) -> None:
        ...


class Unregister(MessageABC):
    request_id: int
    registration_id: int

    def __init__(self, request_id: int, registration_id: int) -> None:
        ...


class Unregistered(MessageABC):
    request_id: int

    def __init__(self, request_id: int) -> None:
        ...


class Invocation(MessageABC):
    request_id: int
    registration_id: int
    details: WAMPDict
    args: Optional[WAMPList]
    kwargs: Optional[WAMPDict]

    def __init__(self, request_id: int, registration_id: int, details: WAMPDict,
                 args: WAMPList = None, kwargs: WAMPDict = None) -> None:
        ...


class Interrupt(MessageABC):
    request_id: int
    options: WAMPDict

    def __init__(self, request_id: int, options: WAMPDict) -> None:
        ...


class Yield(MessageABC):
    request_id: int
    options: WAMPDict
    args: Optional[WAMPList]
    kwargs: Optional[WAMPDict]

    def __init__(self, request_id: int, options: WAMPDict,
                 args: WAMPList = None, kwargs: WAMPDict = None) -> None:
        ...
