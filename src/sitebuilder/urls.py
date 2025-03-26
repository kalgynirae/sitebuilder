from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Self


@dataclass(frozen=True, order=True)
class UrlPath:
    path: str

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            raise ValueError(f"path must be absolute: {self.path!r}")


@dataclass(frozen=True)
class Urls:
    urls: set[UrlPath]

    FILE_HEADER: ClassVar[str] = "# sitebuilder URLs\n"

    @staticmethod
    def path(basedir: Path) -> Path:
        return basedir / "urls.txt"

    @classmethod
    def read(cls, basedir: Path) -> Self:
        path = cls.path(basedir)
        urls = set()
        with ExitStack() as stack:
            try:
                f = stack.enter_context(path.open())
            except FileNotFoundError:
                return cls(set())
            if next(f) != cls.FILE_HEADER:
                raise RuntimeError(f"{path} is not in the expected format")
            for line in f:
                url = UrlPath(line.removesuffix("\n"))
                if url in urls:
                    raise RuntimeError(f"Duplicate URL in urls file: {url!r}")
                urls.add(url)
        return cls(urls)

    def write(self, basedir: Path) -> None:
        dest = self.path(basedir)
        # If the file already exists, only overwrite it if it looks like a file we've
        # written.
        try:
            with dest.open() as f:
                line = f.readline()
            if line != self.FILE_HEADER:
                raise FileExistsError(f"Refusing to overwrite existing file {dest}")
        except FileNotFoundError:
            pass
        with dest.open("w") as f:
            f.write(self.FILE_HEADER)
            f.writelines(f"{url.path}\n" for url in sorted(self.urls))
