import textwrap
from typing import Iterable, List, Reversible, Tuple, Type

import aiowamp

__all__ = []

# The message types are generated dynamically from the following list.

MSGS = (
    ("Hello", 1, ("realm", "details")),
    ("Welcome", 2, ("session_id", "details")),
    ("Abort", 3, ("details", "reason")),
    ("Challenge", 4, ("auth_method", "extra")),
    ("Authenticate", 5, ("signature", "extra")),
    ("Goodbye", 6, ("details", "reason")),
    ("Error", 8, ("msg_type", "request_id", "details", "error"),
     (("args", "list()"), ("kwargs", "dict()"))),

    ("Publish", 16, ("request_id", "options", "topic"),
     (("args", "list()"), ("kwargs", "dict()"))),
    ("Published", 17, ("request_id", "publication_id")),

    ("Subscribe", 32, ("request_id", "options", "topic")),
    ("Subscribed", 33, ("request_id", "subscription_id")),
    ("Unsubscribe", 34, ("request_id", "subscription_id")),
    ("Unsubscribed", 35, ("request_id",)),
    ("Event", 36, ("subscription_id", "publication_id", "details"),
     (("args", "list()"), ("kwargs", "dict()"))),

    ("Call", 48, ("request_id", "options", "procedure"),
     (("args", "list()"), ("kwargs", "dict()"))),
    ("Cancel", 49, ("request_id", "options")),
    ("Result", 50, ("request_id", "details"),
     (("args", "list()"), ("kwargs", "dict()"))),

    ("Register", 64, ("request_id", "options", "procedure")),
    ("Registered", 65, ("request_id", "registration_id")),
    ("Unregister", 66, ("request_id", "registration_id")),
    ("Unregistered", 67, ("request_id",)),
    ("Invocation", 68, ("request_id", "registration_id", "details"),
     (("args", "list()"), ("kwargs", "dict()"))),
    ("Interrupt", 69, ("request_id", "options")),
    ("Yield", 70, ("request_id", "options"),
     (("args", "list()"), ("kwargs", "dict()"))),
)

OPTIONAL_ATTR_TEMPLATE = """
if {bound_attr}:
    msg_list.insert({index}, {bound_attr})
    include = True
elif include:
    msg_list.insert({index}, {empty_value_factory})
"""


# TODO convert string to URI when required


def _gen_optional_attr_code(attrs: Reversible[Tuple[str, str]], end_index: int) -> str:
    attr_parts: List[str] = []

    for (attr, factory) in reversed(attrs):
        attr_parts.append(OPTIONAL_ATTR_TEMPLATE.format(
            index=end_index,
            bound_attr=f"self.{attr}",
            empty_value_factory=factory,
        ))

    if not attr_parts:
        return ""

    return f"include = False\n" + "\n".join(attr_parts)


MSG_TEMPLATE = """
class {name}(aiowamp.MessageABC):
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
                    optional_attrs: Iterable[Tuple[str, str]]) -> Type[aiowamp.MessageABC]:
    attrs, optional_attrs = list(attrs), list(optional_attrs)
    all_attrs = [*attrs, *(attr for attr, _ in optional_attrs)]

    indent = 8 * " "
    bound_attrs_str = "self.message_type," + ",".join(f"self.{attr}" for attr in attrs)
    if optional_attrs:
        to_message_list_code = textwrap.indent(
            (f"msg_list = [{bound_attrs_str}]\n" +
             _gen_optional_attr_code(optional_attrs, len(attrs) + 1) +
             "return msg_list"),
            indent,
        )
    else:
        to_message_list_code = f"{indent}return [{bound_attrs_str}]"

    code = MSG_TEMPLATE.format(
        name=name,
        message_type=message_type,
        init_sig_str=", ".join(attrs) + "," + ",".join(f"{attr} = None" for attr, _ in optional_attrs),
        quoted_attrs_list_str=", ".join(map(repr, all_attrs)),
        set_attr_lines=";".join(f"self.{attr} = {attr}" for attr in all_attrs),
        to_message_list_code=to_message_list_code,
        repr_attrs_str=",".join(f"{attr}={{self.{attr}!r}}" for attr in all_attrs),
    )

    loc = {}
    exec(code, globals(), loc)

    return loc[name]


def _create_msgs():
    for msg in MSGS:
        if len(msg) == 3:
            name, message_type, attrs = msg
            optional_attrs = ()
        elif len(msg) == 4:
            name, message_type, attrs, optional_attrs = msg
        else:
            raise ValueError("Invalid amount of values")

        cls = _create_msg_cls(name, message_type, attrs, optional_attrs)
        globals()[name] = cls
        __all__.append(name)

        aiowamp.register_message_cls(cls)


_create_msgs()

# clean the globals

# because key is defined here, it will be deleted by the code below
key = None
for key in tuple(globals()):
    if key == "__all__" or key in __all__:
        continue

    del globals()[key]
