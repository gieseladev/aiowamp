import textwrap
from typing import Iterable, List, Optional, Reversible, Type

import aiowamp
from .message import MessageABC, register_message_cls
from .uri import URI

__all__ = []

# The message types are generated dynamically from the following list.

MSGS = (
    ("Hello", 1, ("realm:URI", "details")),
    ("Welcome", 2, ("session_id", "details")),
    ("Abort", 3, ("details", "reason:URI")),
    ("Challenge", 4, ("auth_method", "extra")),
    ("Authenticate", 5, ("signature", "extra")),
    ("Goodbye", 6, ("details", "reason:URI")),
    ("Error", 8, ("msg_type", "request_id", "details", "error:URI"),
     ("args:list", "kwargs:dict")),

    ("Publish", 16, ("request_id", "options", "topic:URI"),
     ("args:list", "kwargs:dict")),
    ("Published", 17, ("request_id", "publication_id")),

    ("Subscribe", 32, ("request_id", "options", "topic:URI")),
    ("Subscribed", 33, ("request_id", "subscription_id")),
    ("Unsubscribe", 34, ("request_id", "subscription_id")),
    ("Unsubscribed", 35, ("request_id",)),
    ("Event", 36, ("subscription_id", "publication_id", "details"),
     ("args:list", "kwargs:dict")),

    ("Call", 48, ("request_id", "options", "procedure:URI"),
     ("args:list", "kwargs:dict")),
    ("Cancel", 49, ("request_id", "options")),
    ("Result", 50, ("request_id", "details"),
     ("args:list", "kwargs:dict")),

    ("Register", 64, ("request_id", "options", "procedure:URI")),
    ("Registered", 65, ("request_id", "registration_id")),
    ("Unregister", 66, ("request_id", "registration_id")),
    ("Unregistered", 67, ("request_id",)),
    ("Invocation", 68, ("request_id", "registration_id", "details"),
     ("args:list", "kwargs:dict")),
    ("Interrupt", 69, ("request_id", "options")),
    ("Yield", 70, ("request_id", "options"),
     ("args:list", "kwargs:dict")),
)


class Attr:
    name: str
    cls_name: Optional[str]
    cls: Optional[str]

    def __init__(self, name: str, cls: str = None) -> None:
        self.name = name
        if cls is None:
            self.cls_name = None
            self.cls = None
            return

        self.cls_name = cls

        if cls == "URI":
            self.cls = "URI"
        elif cls in ("list", "dict"):
            self.cls = cls
        else:
            raise ValueError(f"unknown cls: {cls!r}")

    @classmethod
    def parse(cls, s: str):
        parts = s.split(":", 1)
        return cls(*parts)

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.name!r}, cls={self.cls!r})"

    def __str__(self) -> str:
        if self.cls is None:
            return self.name

        return f"{self.name}:{self.cls}"

    def new(self) -> str:
        assert self.cls
        return f"{self.cls}()"

    def quoted(self) -> str:
        return f"\"{self.name}\""

    def convert(self, obj: str) -> str:
        if self.cls is not None:
            return f"{self.cls}({obj})"

        return obj

    def bound(self, obj: str = "self") -> str:
        return f"{obj}.{self.name}"

    def repr(self, obj: str = "self") -> str:
        return f"{self.name}={{{self.bound(obj)}!r}}"

    def bound_setter(self, obj: str = "self", arg: str = None) -> str:
        arg = arg or self.name
        return f"{self.bound(obj)} = {self.convert(arg)}"

    def bound_raw_setter(self, obj: str = "self", arg: str = None) -> str:
        arg = arg or self.name
        return f"{self.bound(obj)} = {arg}"


OPTIONAL_ATTR_TEMPLATE = """
if {bound_attr}:
    msg_list.insert({index}, {bound_attr})
    include = True
elif include:
    msg_list.insert({index}, {empty_value_factory})
"""


def _gen_optional_attr_code(attrs: Reversible[Attr], end_index: int) -> str:
    attr_parts: List[str] = []

    for attr in reversed(attrs):
        attr_parts.append(OPTIONAL_ATTR_TEMPLATE.format(
            index=end_index,
            bound_attr=attr.bound(),
            empty_value_factory=attr.new(),
        ))

    if not attr_parts:
        return ""

    return f"include=False\n" + "\n".join(attr_parts)


MSG_TEMPLATE = """
class {name}(MessageABC):
    __slots__ = ({quoted_attrs_list_str},)
    
    message_type = {message_type}

    def __init__(self, {init_sig_str}):
        {set_attr_lines}
    
    def __repr__(self):
        return f"{name}({repr_attrs_str})"

    def to_message_list(self):
{to_message_list_code}

    @classmethod
    def from_message_list(cls, msg_list):
        return cls(*msg_list)
"""


def _create_msg_cls(name: str, message_type: int,
                    attrs: Iterable[str],
                    optional_attrs: Iterable[str], *,
                    globalns: dict = None) -> Type["aiowamp.MessageABC"]:
    attrs, optional_attrs = list(map(Attr.parse, attrs)), list(map(Attr.parse, optional_attrs))
    all_attrs = [*attrs, *optional_attrs]

    indent = 8 * " "
    bound_attrs_str = f"{message_type!r}, " + ", ".join(attr.bound() for attr in attrs)
    if optional_attrs:
        to_message_list_code = textwrap.indent(
            (f"msg_list = [{bound_attrs_str}]\n" +
             _gen_optional_attr_code(optional_attrs, len(attrs) + 1) +
             "return msg_list"),
            indent,
        )
    else:
        to_message_list_code = f"{indent}return [{bound_attrs_str}]"

    init_sig_str = ", ".join(attr.name for attr in attrs) + ", " + \
                   ", ".join(f"{attr.name}=None" for attr in optional_attrs)

    set_attr_lines = ";".join(attr.bound_setter() for attr in attrs) + ";" + \
                     ";".join(attr.bound_raw_setter() for attr in optional_attrs)
    code = MSG_TEMPLATE.format(
        name=name,
        message_type=message_type,
        init_sig_str=init_sig_str,
        quoted_attrs_list_str=", ".join(attr.quoted() for attr in all_attrs),
        set_attr_lines=set_attr_lines,
        to_message_list_code=to_message_list_code,
        repr_attrs_str=", ".join(attr.repr() for attr in all_attrs),
    )

    loc = {}
    exec(code, globalns, loc)

    return loc[name]


def _create_msgs():
    globalns = {"MessageABC": MessageABC, "URI": URI}

    for msg in MSGS:
        if len(msg) == 3:
            name, message_type, attrs = msg
            optional_attrs = ()
        elif len(msg) == 4:
            name, message_type, attrs, optional_attrs = msg
        else:
            raise ValueError("Invalid amount of values")

        cls = _create_msg_cls(name, message_type, attrs, optional_attrs,
                              globalns=globalns)
        globals()[name] = cls
        __all__.append(name)

        register_message_cls(cls)


_create_msgs()

# clean the globals
# because key is defined here, it will be deleted by the code below
key = None
for key in tuple(globals()):
    if key == "__all__" or key in __all__:
        continue

    del globals()[key]
