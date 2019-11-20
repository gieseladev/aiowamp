import abc
import inspect
from typing import Any, Callable, Iterable, List, Optional, get_type_hints

import aiowamp
from aiowamp import InvocationABC, SubscriptionEventABC
from aiowamp.client.procedure_runner import ProcedureRunnerABC, get_fn_runner_cls, get_obj_runner_cls
from .args import CommonArg, KWArg, VarKWArg, args_from_signature
from .code import Code, indent

__all__ = ["CommonEntryPoint",
           "ProcedureEntryPoint", "EventEntryPoint"]


def class_and_subclass(cls, o) -> bool:
    return inspect.isclass(cls) and issubclass(cls, o)


WRAPPED_FUNC_NAME = "FN_WRAPPED"


class CommonEntryPoint(Code):
    fn: Callable
    args: List[CommonArg]

    _has_kwargs: bool

    def __init__(self, fn: Callable, args: Iterable[CommonArg]) -> None:
        self.fn = fn

        self.args = list(args)

        if any(isinstance(arg, VarKWArg) for arg in self.args):
            self._has_kwargs = True
            for arg in self.args:
                if isinstance(arg, KWArg):
                    arg.has_var_kwargs = True
        else:
            self._has_kwargs = False

    @classmethod
    @abc.abstractmethod
    def resolve_special(cls, value: Any) -> Optional[str]:
        ...

    @classmethod
    def from_fn(cls, fn: Callable):
        args = args_from_signature(inspect.signature(fn),
                                   resolve_special=cls.resolve_special,
                                   type_hints=get_type_hints(fn))
        return cls(fn, args)

    @property
    def entry_point_fn_name(self) -> str:
        try:
            name: str = self.fn.__name__
        except AttributeError:
            name = WRAPPED_FUNC_NAME

        if not name.isidentifier():
            name = "anonymous"

        return f"{name}_entry_point"

    def update_globals(self, globalns: dict) -> None:
        globalns["aiowamp"] = aiowamp

        for arg in self.args:
            arg.update_globals(globalns)

        globalns[WRAPPED_FUNC_NAME] = self.fn

    def prepare_args_code(self) -> str:
        return "\n\n".join(filter(None, (arg.code() for arg in self.args)))

    def fn_call_line(self) -> str:
        args_sig = ", ".join(arg.call_sig_line() for arg in self.args)
        return f"{WRAPPED_FUNC_NAME}({args_sig})"

    @abc.abstractmethod
    def run_fn_code(self) -> str:
        ...

    def kwargs_code(self) -> str:
        s = f"kwargs = args_mixin.kwargs"
        if self._has_kwargs:
            s += ".copy()"

        return s

    def code(self) -> str:
        return f"""
async def {self.entry_point_fn_name}(args_mixin):
    args = args_mixin.args
{indent(1, self.kwargs_code())}

{indent(1, self.prepare_args_code())}

{indent(1, self.run_fn_code())}
        """.strip()

    def exec(self, globalns: dict = None, localns: dict = None) -> Callable:
        globalns = globalns or {}
        localns = localns or {}
        self.update_globals(globalns)
        exec(self.code(), globalns, localns)

        return localns[self.entry_point_fn_name]


class ProcedureEntryPoint(CommonEntryPoint):
    @classmethod
    def resolve_special(cls, value: Any) -> Optional[str]:
        if class_and_subclass(value, InvocationABC):
            return "args_mixin"

        return None

    @property
    def runner(self) -> Any:
        return get_fn_runner_cls(self.fn) or get_obj_runner_cls

    @property
    def runner_cls_var_name(self) -> str:
        return self.runner.__name__

    def update_globals(self, globalns: dict) -> None:
        super().update_globals(globalns)
        globalns[self.runner_cls_var_name] = self.runner

    def run_fn_code(self) -> str:
        runner = self.runner
        if issubclass(runner, ProcedureRunnerABC):
            return f"await {self.runner_cls_var_name}(args_mixin, {self.fn_call_line()})"

        return f"""
    res = {self.fn_call_line()}
    runner = {self.runner_cls_var_name}(res)
    await runner(args_mixin, res)
            """.strip()


class EventEntryPoint(CommonEntryPoint):
    @classmethod
    def resolve_special(cls, value: Any) -> Optional[str]:
        if class_and_subclass(value, SubscriptionEventABC):
            return "args_mixin"

        return None

    def run_fn_code(self) -> str:
        return f"await {self.fn_call_line()}"
