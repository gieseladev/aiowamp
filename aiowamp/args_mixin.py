from __future__ import annotations

from typing import Any, Iterator, Mapping, Optional, Sequence, TypeVar, Union, overload

import aiowamp

__all__ = ["ArgsMixin"]

T = TypeVar("T")


class ArgsMixin:
    """Helper class which provides useful methods for types with args and kwargs.

    The args and kwargs attributes ARE NOT part of this class, they are expected
    to exist.
    """
    __slots__ = ()

    args: Sequence[aiowamp.WAMPType]
    kwargs: Mapping[str, aiowamp.WAMPType]

    def __repr__(self) -> str:
        arg_str = ", ".join(map(repr, self.args))
        kwarg_str = ", ".join(f"{key} = {value!r}" for key, value in self.kwargs.items())
        if kwarg_str and arg_str:
            join_str = ", "
        else:
            join_str = ""

        return f"{type(self).__qualname__}({arg_str}{join_str}{kwarg_str})"

    def __len__(self) -> int:
        return len(self.args)

    def __iter__(self) -> Iterator[aiowamp.WAMPType]:
        return iter(self.args)

    def __reversed__(self) -> Iterator[aiowamp.WAMPType]:
        return reversed(self.args)

    def __getitem__(self, key: Union[int, str]) -> aiowamp.WAMPType:
        if isinstance(key, str):
            return self.kwargs[key]

        return self.args[key]

    def __contains__(self, key: Any) -> bool:
        return key in self.kwargs

    @overload
    def get(self, key: Union[int, str]) -> Optional[aiowamp.WAMPType]:
        ...

    @overload
    def get(self, key: Union[int, str], default: T) -> Union[aiowamp.WAMPType, T]:
        ...

    def get(self, key: Union[int, str], default: T = None) -> Union[aiowamp.WAMPType, T, None]:
        """Get the value assigned to the given key.

        If the key is a string it is looked-up in the keyword arguments.
        If it's an integer it is treated as an index for the arguments.

        Args:
            key: Index or keyword to get value for.
            default: Default value to return. Defaults to `None`.

        Returns:
            The value assigned to the key or the default value if not found.
        """
        try:
            return self[key]
        except LookupError:
            return default
