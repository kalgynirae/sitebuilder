import shlex
import shutil
from asyncio import create_subprocess_exec, gather, get_running_loop
from asyncio.subprocess import PIPE
from collections import ChainMap
from dataclasses import dataclass
from pathlib import Path
from typing import Type, cast

import tomllib

from .actions import SCSS, Action, Copy, Redirect
from .logging import dim, log, log_prefix, red, yellow
from .resources import Resources
from .urls import UrlPath, Urls

SITEBUILDER_DEST_MARKER_FILENAME = ".sitebuilder-dest-dir"


@dataclass(frozen=True)
class Args:
    args: list[str]

    def __str__(self) -> str:
        return dim(f"«{shlex.join(self.args)}»")


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str


async def run(args: list[str]) -> RunResult:
    log(f"Running {Args(args)}")
    proc = await create_subprocess_exec(*args, stdout=PIPE, stderr=PIPE)
    stdoutb, stderrb = await proc.communicate()
    stdout = stdoutb.decode()
    stderr = stderrb.decode()
    with log_prefix("  :stderr: ", dim):
        for line in stderr.splitlines():
            log(line)
    return RunResult(cast(int, proc.returncode), stdout)


def log_walk_error(e: OSError) -> None:
    log(f"Error while walking {e.filename!r}", exc=e)


DEFAULT_ACTIONS: dict[str, Type[Action]] = {
    ".scss": SCSS,
}


async def build(
    *, action_config: dict[str, Type[Action]] | None = None, basedir: Path | None = None
) -> int:
    combined_actions = ChainMap(action_config or {}, DEFAULT_ACTIONS)
    if basedir is None:
        revparse_result = await run(["git", "rev-parse", "--show-toplevel"])
        basedir = Path(revparse_result.stdout.removesuffix("\n"))
    old_urls = Urls.read(basedir)

    srcdir = basedir / "src"
    destdir = basedir / "build"

    # Load actions from srcdir
    actions = []
    for dirpath, _dirnames, filenames in srcdir.walk(on_error=log_walk_error):
        for filename in filenames:
            path = dirpath / filename
            if (action_class := combined_actions.get(path.suffix)) is not None:
                actions.append(action_class(source=path))
            else:
                actions.append(Copy(source=path))

    # Load redirects
    with (basedir / "redirects.toml").open("rb") as f:
        redirects = tomllib.load(f)
    for old_url, new_url in redirects.items():
        actions.append(Redirect(old_url, new_url))

    # Load resources
    resources = Resources.load(basedir)

    # Gather the complete set of URLs that will be produced
    url_actions: dict[UrlPath, list[str]] = {}
    for action in actions:
        url_actions.setdefault(action.url(srcdir), []).append(str(action))

    # Check for conflicting outputs
    for url, action_names in url_actions.items():
        if len(action_names) > 1:
            log(f"Multiple actions produce {red(url.path)}: {', '.join(action_names)}")
            return 1

    # Clear out the dest dir
    if destdir.exists(follow_symlinks=False):
        if destdir.is_dir():
            if not (destdir / SITEBUILDER_DEST_MARKER_FILENAME).exists():
                log(
                    "dest dir doesn't contain the marker file; refusing to overwrite it"
                )
                return 1
            shutil.rmtree(destdir)
        else:
            raise FileExistsError(
                f"dest dir exists and is not a directory: {destdir!r}"
            )
    destdir.mkdir()
    (destdir / SITEBUILDER_DEST_MARKER_FILENAME).touch()

    # Actually do the things
    loop = get_running_loop()
    futures = []
    for action in actions:
        futures.append(
            loop.run_in_executor(None, action.run, srcdir, destdir, resources)
        )
    for result in await gather(*futures):
        log(f"{result}")
        for warning in result.warnings:
            with log_prefix("     ↪ ", style=yellow):
                log(warning)

    # Check for forgotten URLs and either fail or update the URLs file
    new_urls = set(url_actions.keys())
    forgotten_urls = old_urls.urls - new_urls
    if forgotten_urls:
        for url in sorted(forgotten_urls):
            log(f"Forgotten URL: {red(url.path)}")
        return 1
    else:
        Urls(new_urls).write(basedir)
    return 0
