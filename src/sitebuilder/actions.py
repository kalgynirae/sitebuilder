from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
from textwrap import dedent
from traceback import format_exception_only
from typing import Callable, ClassVar, override
import tomllib

from .logging import dim, green, red
from .resources import Resources
from .urls import UrlPath

META_DELIMITER = "---\n"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Result:
    success: bool
    warnings: list[str]
    src: str
    dest: str

    def __str__(self) -> str:
        ok = f"  {green('OK')}" if self.success else f"{red('FAIL')}"
        return f"{ok} {dim(self.src)} -> {dim(self.dest)}"


@dataclass(frozen=True)
class Action(metaclass=ABCMeta):
    source: Path | None

    def dest_path(self, path: Path) -> Path:
        return path

    @abstractmethod
    def run(self, srcdir: Path, destdir: Path, resources: Resources) -> Result: ...

    @abstractmethod
    def url(self, srcdir: Path) -> UrlPath: ...


@dataclass(frozen=True)
class Redirect(Action):
    old_url: str
    new_url: str

    REDIRECT_TEMPLATE: ClassVar[str] = dedent(
        """\
        <!DOCTYPE html>
        <html lang="en-us">
        <head>
          <meta charset="utf-8">
          <meta http-equiv="refresh" content="0; url={new_url}">
          <title>Redirect</title>
        </head>
        <body>
          <p>This page has moved: <a href="{new_url}">{new_url}</a></p>
        </body>
        </html>
        """
    )

    def __init__(self, old_url: str, new_url: str) -> None:
        super().__init__(source=None)
        object.__setattr__(self, "old_url", old_url)
        object.__setattr__(self, "new_url", new_url)

    @override
    def run(self, srcdir: Path, destdir: Path, resources: Resources) -> Result:
        old_relative = Path(self.old_url.removeprefix("/"))
        dest_relpath = (
            old_relative / "index.html" if self.old_url.endswith("/") else old_relative
        )
        dest = destdir / dest_relpath
        dest.write_text(self.REDIRECT_TEMPLATE.format(new_url=self.new_url))
        return Result(
            success=True,
            warnings=[],
            src="(generated-redirect)",
            dest=f"{destdir.name}/{dest_relpath}",
        )

    @override
    def url(self, srcdir: Path) -> UrlPath:
        return UrlPath(self.old_url)


@dataclass(frozen=True)
class SourceAction(Action):
    source: Path

    @abstractmethod
    def run_inner(self, dest: Path, resources: Resources) -> None: ...

    @override
    def run(self, srcdir: Path, destdir: Path, resources: Resources) -> Result:
        src_relpath = self.source.relative_to(srcdir)
        dest_relpath = self.dest_path(src_relpath)
        result = Result(
            success=True,
            warnings=[],
            src=f"{srcdir.name}/{src_relpath}",
            dest=f"{destdir.name}/{dest_relpath}",
        )
        dest = destdir / dest_relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.run_inner(dest, resources)
        except Exception as e:
            result = replace(result, success=False)
            logger.warning(
                "Caught exception while processing source %s", result.src, exc_info=True
            )
            result.warnings.append("".join(format_exception_only(e)).removesuffix("\n"))
        return result

    @override
    def url(self, srcdir: Path) -> UrlPath:
        return UrlPath("/" + str(self.dest_path(self.source.relative_to(srcdir))))


@dataclass(frozen=True)
class WithMeta(SourceAction):
    meta: dict[str, str] = field(init=False)
    contents: str = field(init=False)

    def __post_init__(self) -> None:
        meta_lines = []
        contents_lines = []
        with self.source.open() as f:
            for line in f:
                if line == META_DELIMITER:
                    break
                meta_lines.append(line)
            else:
                # No delimiter means no meta; all lines were contents
                contents_lines.extend(meta_lines)
                meta_lines.clear()
            contents_lines.extend(f)
        meta = tomllib.loads("".join(meta_lines))
        contents = "".join(contents_lines)
        object.__setattr__(self, "meta", meta)
        object.__setattr__(self, "contents", contents)


@dataclass(frozen=True)
class Copy(SourceAction):
    @override
    def run_inner(self, dest: Path, resources: Resources) -> None:
        dest.write_bytes(self.source.read_bytes())


def index_html_processor(
    processing_func: Callable[[str, dict[str, str], str, Resources], str],
) -> type[Action]:
    @dataclass(frozen=True)
    class IndexHtmlProcessor(WithMeta, SourceAction):
        @override
        def dest_path(self, path: Path) -> Path:
            return path.with_suffix("") / "index.html"

        @override
        def run_inner(self, dest: Path, resources: Resources) -> None:
            out = processing_func(self.source.name, self.meta, self.contents, resources)
            dest.write_text(out)

    return IndexHtmlProcessor
