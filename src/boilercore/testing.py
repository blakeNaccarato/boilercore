"""Helper functions for testing boiler code."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from re import compile
from shutil import copy, copytree

import pytest
from nbqa.__main__ import _get_nb_to_tmp_mapping, _save_code_sources  # type: ignore


def change_workdir_and_prepend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Change directory and prepend test directory root to `sys.path`.

    Returns the original working directory."""
    orig = Path.cwd()
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(tmp_path)
    return orig


@contextmanager
def get_tmp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    try:
        data = Path("data")
        test_data = Path("tests") / data
        copytree(test_data, tmp_path / data, dirs_exist_ok=True)
        params = "params.yaml"
        copy(test_data / params, tmp_path / params)
        yield test_data
    finally:
        change_workdir_and_prepend(tmp_path, monkeypatch)


def make_tmp_nbs_content(nbs: list[Path], tmp_path: Path):
    """Copy notebook contents to importable scripts in the test directory root."""
    for nb in nbs:
        (tmp_path / nb.with_suffix(".py").name).write_text(
            encoding="utf-8", data=get_nb_content(nb)
        )


def get_nb_content(nb: Path) -> str:
    """Get the contents of a notebook."""
    _, (newlinesbefore, _) = _save_code_sources(
        _get_nb_to_tmp_mapping(
            [str(nb)],
            None,
            None,
            False,
        ),
        [],
        [],
        False,
        "abc",
    )
    script = next(Path(script) for script in list(newlinesbefore.keys()))
    contents = script.read_text(encoding="utf-8")
    script.unlink()
    return contents


def walk_modules(package: Path, top: Path) -> Iterable[str]:
    """Walk modules from a given submodule path and the top level library directory."""
    for directory in (
        package,
        *[
            path
            for path in package.iterdir()
            if path.is_dir() and "__" not in str(path.relative_to(top.parent))
        ],
    ):
        for example in sorted(directory.glob("[!__]*.py")):
            yield (get_module(example, top))


def get_module(submodule: Path, library: Path) -> str:
    """Get module name given the submodule path and the top level library directory."""
    return (
        str(submodule.relative_to(library.parent).with_suffix(""))
        .replace("\\", ".")
        .replace("/", ".")
    )


def get_module_rel(module: str, relative: str) -> str:
    """Get module name relative to another module."""
    return compile(rf".*{relative}\.").sub(repl="", string=module)
