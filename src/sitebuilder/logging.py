import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator, TypeAlias

Style: TypeAlias = Callable[[str], str]

_prefix = ContextVar("_prefix", default="")
_style: ContextVar[Style] = ContextVar("_style", default=str)


def log(message: str, exc: BaseException | None = None) -> None:
    if exc is not None:
        exception = ": " + "\n".join(traceback.format_exception_only(exc))
    else:
        exception = ""
    print(_style.get()(f"{_prefix.get()}{message}{exception}"), file=sys.stderr)


@contextmanager
def log_prefix(prefix: str, style: Style | None = None) -> Iterator[None]:
    prefix_token = _prefix.set(_prefix.get() + prefix)
    if style:
        style_token = _style.set(style)
    try:
        yield
    finally:
        _prefix.reset(prefix_token)
        if style:
            _style.reset(style_token)


def dim(s: str) -> str:
    return f"\x1b[2m{s}\x1b[22m"


def red(s: str) -> str:
    return f"\x1b[31m{s}\x1b[39m"


def green(s: str) -> str:
    return f"\x1b[32m{s}\x1b[39m"


def yellow(s: str) -> str:
    return f"\x1b[33m{s}\x1b[39m"
