import abc
import dataclasses
import inspect
import itertools
import warnings
from typing import Any, Callable, List, Mapping, Optional, Type

from .code import Code, indent

__all__ = ["CommonArg",
           "PosArg", "VarPosArg", "KWArg", "PosOrKWArg", "VarKWArg",
           "GetterArg",
           "args_from_signature"]


# TODO don't raise for subscription events

@dataclasses.dataclass()
class CommonArg(Code, abc.ABC):
    name: str
    annotation: type
    has_default: bool
    default: Any

    @property
    def arg_name(self) -> str:
        return f"arg_{self.name}"

    @property
    def default_value_var_name(self) -> str:
        return f"{self.arg_name.upper()}_DEFAULT"

    def update_globals(self, globalns: dict) -> None:
        if self.has_default:
            key = self.default_value_var_name
            assert key not in globalns
            globalns[key] = self.default

    @abc.abstractmethod
    def get_value_code(self) -> str:
        ...

    @abc.abstractmethod
    def call_sig_line(self) -> str:
        ...

    def missing_err_args(self) -> tuple:
        return f"missing required argument {self.name!r}",

    def missing_err_kwargs(self) -> dict:
        return {"parameter": self.name}

    def handle_missing_code(self) -> str:
        if self.has_default:
            return f"{self.arg_name} = {self.default_value_var_name}"

        args_str = ",".join(map(repr, self.missing_err_args()))
        return f"raise aiowamp.InvocationError(" \
               f"aiowamp.uri.INVALID_ARGUMENT, " \
               f"{args_str}, " \
               f"kwargs={self.missing_err_kwargs()!r}" \
               f")"

    def code(self) -> str:
        return f"""
try:
{indent(1, self.get_value_code())}
except LookupError:
{indent(1, self.handle_missing_code())}
        """.strip()


@dataclasses.dataclass()
class PosArg(CommonArg):
    index: int

    def get_value_code(self) -> str:
        return f"{self.arg_name} = args[{self.index}]"

    def call_sig_line(self) -> str:
        return self.arg_name

    def missing_err_kwargs(self) -> dict:
        d = super().missing_err_kwargs()
        d["index"] = self.index
        return d


class VarPosArg(PosArg):
    def update_globals(self, globalns: dict) -> None:
        super().update_globals(globalns)
        globalns["itertools"] = itertools

    def get_value_code(self) -> str:
        return ""

    def call_sig_line(self) -> str:
        return f"*itertools.islice(args, {self.index}, None)"

    def code(self) -> str:
        return ""


class KWArg(CommonArg):
    has_var_kwargs: bool = False

    def get_value_code(self) -> str:
        if self.has_var_kwargs:
            return f"{self.arg_name} = kwargs.pop({self.name!r})"
        return f"{self.arg_name} = kwargs[{self.name!r}]"

    def call_sig_line(self) -> str:
        return f"{self.name}={self.arg_name}"


class PosOrKWArg(PosArg, KWArg):
    def duplicate_err_kwargs(self) -> dict:
        return {
            "index": self.index,
            "keyword": self.name,
        }

    def duplicate_err_line(self) -> str:
        return f"aiowamp.InvocationError(" \
               f"aiowamp.uri.INVALID_ARGUMENT," \
               f"\"multiple values for argument {self.name!r}\"," \
               f"kwargs={self.duplicate_err_kwargs()!r}" \
               f")"

    def handle_in_kwargs_code(self) -> str:
        return f"""
if {self.arg_name} == kwargs[{self.name!r}]:
    del kwargs[{self.name!r}]
else:
    raise {self.duplicate_err_line()}
        """.strip()

    def ensure_not_in_kwargs_code(self) -> str:
        return f"""
if "{self.name}" in kwargs:
{indent(1, self.handle_in_kwargs_code())}
        """.strip()

    def get_value_code(self) -> str:
        code = f"""
try:
{indent(1, PosArg.get_value_code(self))}
except LookupError:
{indent(1, KWArg.get_value_code(self))}
        """.strip()

        if self.has_var_kwargs:
            code += f"\nelse:\n{indent(1, self.ensure_not_in_kwargs_code())}"

        return code


class VarKWArg(CommonArg):
    def get_value_code(self) -> str:
        return ""

    def call_sig_line(self) -> str:
        return f"**kwargs"

    def code(self) -> str:
        return ""


@dataclasses.dataclass()
class GetterArg(CommonArg):
    getter: str

    def get_value_code(self) -> str:
        return ""

    def call_sig_line(self) -> str:
        return self.getter

    def code(self) -> str:
        return ""


class SelfArg(GetterArg):
    getter = "self"


PARAM_KIND = inspect.Parameter


def arg_from_parameter(param: inspect.Parameter, index: int, *,
                       resolved_type: Any,
                       resolve_special: Callable[[Any], Optional[str]],
                       allow_special: bool) -> CommonArg:
    has_default = param.default is not PARAM_KIND.empty

    args = [param.name, resolved_type, has_default, param.default]

    special_getter = resolve_special(resolved_type)
    if special_getter:
        if allow_special:
            if has_default:
                warnings.warn(f"special parameter {resolved_type.__qualname__} should not have a default value",
                              SyntaxWarning,
                              stacklevel=3)

            return GetterArg(*args, special_getter)
        else:
            warnings.warn(f"special parameter {resolved_type.__qualname__} will be treated like a normal parameter.",
                          SyntaxWarning,
                          stacklevel=3)

    cls: Type[CommonArg]
    if param.kind == PARAM_KIND.POSITIONAL_ONLY:
        cls = PosArg
        args.append(index)
    elif param.kind == PARAM_KIND.POSITIONAL_OR_KEYWORD:
        cls = PosOrKWArg
        args.append(index)
    elif param.kind == PARAM_KIND.VAR_POSITIONAL:
        cls = VarPosArg
        args.append(index)
    elif param.kind == PARAM_KIND.KEYWORD_ONLY:
        cls = KWArg
    elif param.kind == PARAM_KIND.VAR_KEYWORD:
        cls = VarKWArg
    else:
        raise TypeError(f"unknown parameter kind for parameter {param.name}: {param.kind}")

    # noinspection PyArgumentList
    return cls(*args)


def args_from_signature(sig: inspect.Signature, *,
                        resolve_special: Callable[[Any], Optional[str]],
                        type_hints: Mapping[str, Any]) -> List[CommonArg]:
    args: List[CommonArg] = []

    allow_special = True
    index = 0
    for param in sig.parameters.values():
        try:
            resolved_type = type_hints[param.name]
        except KeyError:
            resolved_type = Any

        arg = arg_from_parameter(param, index,
                                 resolved_type=resolved_type,
                                 resolve_special=resolve_special,
                                 allow_special=allow_special)
        if not isinstance(arg, GetterArg):
            allow_special = False
            index += 1

        args.append(arg)

    return args
