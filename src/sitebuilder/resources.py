from dataclasses import dataclass
from pathlib import Path
from typing import Self


@dataclass(frozen=True)
class Resources:
    templates: dict[str, str]

    @classmethod
    def load(cls, basedir: Path) -> Self:
        templates = {}
        for path in (basedir / "templates").iterdir():
            templates[path.name] = path.read_text()
        return cls(
            templates=templates,
        )
