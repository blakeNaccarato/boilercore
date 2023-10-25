"""Paths and modules."""

from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from os import walk
from pathlib import Path
from re import NOFLAG, VERBOSE, compile
from shlex import quote
from types import ModuleType

from dulwich.porcelain import status, submodule_list
from dulwich.repo import Repo


def get_package_dir(package: ModuleType) -> Path:
    return Path(next(iter(package.__path__)))


DEFAULT_SUFFIXES = [".py"]


def map_stages(package: Path, suffixes=DEFAULT_SUFFIXES) -> dict[str, Path]:
    """Map stage module names to their paths."""
    modules: dict[str, Path] = {}
    for path in walk_module_paths(package, suffixes):
        module = get_module_rel(get_module(path, package), package.name)
        if module == ".":
            continue
        modules[module.replace(".", "_")] = path
    return modules


def get_module_rel(module: str, relative: str) -> str:
    """Get module name relative to another module."""
    if relative not in module:
        raise ValueError(f"{module} not relative to {relative}.")
    return (
        "."
        if module == relative
        else compile(rf"^.*{relative}\.").sub(repl="", string=module)
    )


def walk_modules(
    package: Path, suffixes: list[str] = DEFAULT_SUFFIXES
) -> Iterable[str]:
    """Walk modules from a given submodule path and the top level library directory."""
    for module in walk_module_paths(package, suffixes=suffixes):
        yield get_module(module, package)


def get_module(module: Path, package: Path) -> str:
    """Get module name given the submodule path and the top level library directory."""
    module = module.parent if module.stem == "__main__" else module
    return (
        str(module.relative_to(package.parent).with_suffix(""))
        .replace("\\", ".")
        .replace("/", ".")
    )


def walk_module_paths(
    package: Path, suffixes: list[str] = DEFAULT_SUFFIXES
) -> Iterable[Path]:
    """Walk the paths of a Python package."""
    yield from (
        match
        for match in walk_matches(
            package,
            regex=rf"""^
                 [^\.]*  # Match file stem
                 {get_suffixes_re(suffixes)}  # Match suffixes
                 $""",
            root_regex=r"^(?!__).*$",  # Exclude dunder folders
            flags=VERBOSE,
        )
        if match.stem != "__init__"
    )


def get_suffixes_re(suffixes: list[str]) -> str:
    """Get the regex pattern string for file suffixes."""
    suffixes_re = f"({get_suffix_re(suffixes[0])}"
    for suffix in suffixes[1:]:
        suffixes_re += f"|{get_suffix_re(suffix)}"
    suffixes_re += ")"
    return suffixes_re


def get_suffix_re(suffix: str) -> str:
    """Get the regex pattern string for a file suffix."""
    suffix = suffix.replace(r"\.", ".")
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return suffix.replace(".", r"\.")


def walk_matches(
    path: Path,
    glob: str | None = None,
    regex: str | None = None,
    root_regex: str | None = None,
    flags=NOFLAG,
) -> Iterable[Path]:
    """Walk a directory returning regex or glob matches."""
    glob = glob or "*"
    path_re = compile(regex or "^.*$", flags=flags)
    root_re = compile(root_regex or "^.*$", flags=flags)
    for root, _dirs, files in walk(path):
        if not root_re.match(Path(root).name):
            continue
        files = [Path(root) / file for file in files]
        for path in Path(root).glob(glob):
            if path in files and path_re.match(path.name):
                yield path


def fold(path: Path) -> str:
    """Resolve and normalize a path to a POSIX string path with forward slashes."""
    return quote(str(path.resolve()).replace("\\", "/"))


def modified(nb: str) -> bool:
    """Check whether notebook is modified."""
    return Path(nb) in (change.resolve() for change in get_changes())


def get_changes() -> list[Path]:
    """Get pending changes."""
    staged, unstaged, _ = status(untracked_files="no")
    changes = {
        # Many dulwich functions return bytes for legacy reasons
        Path(path.decode("utf-8")) if isinstance(path, bytes) else path
        for change in (*staged.values(), unstaged)
        for path in change
    }
    # Exclude submodules from the changeset (submodules are considered always changed)
    return sorted(
        change
        for change in changes
        if change not in {submodule.path for submodule in get_submodules()}
    )


@dataclass
class Submodule:
    """Represents a git submodule."""

    _path: str | bytes
    """Submodule path as reported by the submodule source."""
    commit: str
    """Commit hash currently tracked by the submodule."""
    path: Path = Path()
    """Submodule path."""
    name: str = ""
    """Submodule name."""

    def __post_init__(self):
        """Handle byte strings reported by some submodule sources, like dulwich."""
        # Many dulwich functions return bytes for legacy reasons
        self.path = Path(
            self._path.decode("utf-8") if isinstance(self._path, bytes) else self._path
        )
        self.name = self.path.name


def get_submodules() -> list[Submodule]:
    """Get the special template and typings submodules, as well as the rest."""
    with closing(repo := Repo(str(Path.cwd()))):
        return [Submodule(*item) for item in list(submodule_list(repo))]
