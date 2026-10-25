# SPDX-License-Identifier: ISC
#
# Copyright (c) 2021, Timothée Mazzucotelli and contributors
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""Tests for the CLI."""

from __future__ import annotations

import io
import json
import os
from typing import TYPE_CHECKING

import pytest

from griffe._internal import debug
from griffe._internal.enumerations import ExplanationStyle
from griffe._internal.exceptions import GitError
from griffecli._internal import cli

if TYPE_CHECKING:
    from pathlib import Path


def test_main() -> None:
    """Basic CLI test."""
    assert cli.main(["dump", "griffe", "-s", "src", f"-o{os.devnull}"]) == 0


@pytest.mark.parametrize("flag", ["-P", "--prefer-stubs-docstrings"])
def test_prefer_stubs_docstrings(tmp_path: Path, flag: str) -> None:
    """Prefer docstrings from stubs when requested.

    Parameters:
        tmp_path: Pytest fixture providing a temporary directory.
        flag: Short or long spelling of the CLI flag.
    """
    package_path = tmp_path / "package"
    package_path.mkdir()
    package_path.joinpath("__init__.py").write_text('"""Source."""', encoding="utf8")
    package_path.joinpath("__init__.pyi").write_text('"""Stubs."""', encoding="utf8")
    output_path = tmp_path / "output.json"

    assert cli.main(["dump", str(package_path), flag, "-o", str(output_path)]) == 0

    output = json.loads(output_path.read_text(encoding="utf8"))
    assert output["package"]["docstring"]["value"] == "Stubs."


def test_show_help(capsys: pytest.CaptureFixture) -> None:
    """Show help.

    Parameters:
        capsys: Pytest fixture to capture output.
    """
    with pytest.raises(SystemExit):
        cli.main(["-h"])
    captured = capsys.readouterr()
    assert "griffe" in captured.out


def test_show_version(capsys: pytest.CaptureFixture) -> None:
    """Show version.

    Parameters:
        capsys: Pytest fixture to capture output.
    """
    with pytest.raises(SystemExit):
        cli.main(["-V"])
    captured = capsys.readouterr()
    assert debug._get_version() in captured.out


def test_show_debug_info(capsys: pytest.CaptureFixture) -> None:
    """Show debug information.

    Parameters:
        capsys: Pytest fixture to capture output.
    """
    with pytest.raises(SystemExit):
        cli.main(["--debug-info"])
    captured = capsys.readouterr().out.lower()
    assert "python" in captured
    assert "system" in captured
    assert "environment" in captured
    assert "packages" in captured


def test_print_data(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Test `_print_data` writing to stdout, file, and file stream."""
    cli._print_data('{"a": 1}', None)
    assert capsys.readouterr().out == '{"a": 1}\n'

    out_path = tmp_path / "out.json"
    cli._print_data('{"a": 1}', str(out_path))
    assert out_path.read_text(encoding="utf8") == '{"a": 1}\n'

    buf = io.StringIO()
    cli._print_data('{"a": 1}', buf)
    assert buf.getvalue() == '{"a": 1}\n'


def test_load_packages(tmp_path: Path) -> None:
    """Test `_load_packages` options including extensions, search paths, and errors."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import sub\nx = sub\n", encoding="utf8")
    (pkg / "sub.py").write_text("y = 1\n", encoding="utf8")

    bad_pkg = tmp_path / "badpkg"
    bad_pkg.mkdir()
    (bad_pkg / "__init__.py").write_bytes(b"\xff\xfe")

    from griffe._internal.extensions.base import load_extensions  # noqa: PLC0415
    from griffe._internal.loader import GriffeLoader  # noqa: PLC0415

    orig_load = GriffeLoader.load

    def custom_load(self: GriffeLoader, package: str | Path, *args: object, **kwargs: object) -> object:
        if package == "import_err_pkg":
            raise ImportError("cannot import")
        return orig_load(self, package, *args, **kwargs)  # ty:ignore[invalid-argument-type]

    GriffeLoader.load = custom_load  # ty:ignore[invalid-assignment]
    try:
        loader = cli._load_packages(
            ["", "mypkg", "nonexistent_pkg_xyz_123", "import_err_pkg"],
            extensions=load_extensions("dataclasses"),
            search_paths=[tmp_path],
            docstring_parser="auto",
            docstring_options={"default": "google"},
            resolve_aliases=True,
            resolve_implicit=True,
            resolve_external=True,
            allow_inspection=False,
            force_inspection=False,
            store_source=False,
            find_stubs_package=False,
            prefer_stubs_docs=False,
        )
    finally:
        GriffeLoader.load = orig_load
    assert "mypkg" in loader.modules_collection

    # Also test unresolved aliases branch
    pkg_unres = tmp_path / "pkg_unres"
    pkg_unres.mkdir()
    (pkg_unres / "__init__.py").write_text("from missing_external_xyz import something\n", encoding="utf8")
    loader_unres = cli._load_packages(
        ["pkg_unres"],
        search_paths=[tmp_path],
        resolve_aliases=True,
        resolve_implicit=True,
        resolve_external=False,
    )
    assert "pkg_unres" in loader_unres.modules_collection


def test_extensions_type() -> None:
    """Test `_extensions_type` helper."""
    assert cli._extensions_type('["dataclasses", {"unpack_typeddict": {}}]') == [
        "dataclasses",
        {"unpack_typeddict": {}},
    ]
    assert cli._extensions_type("dataclasses,unpack_typeddict") == ["dataclasses", "unpack_typeddict"]


def test_dump_command(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Test `dump` subcommand with various options."""
    pkg1 = tmp_path / "pkg1"
    pkg1.mkdir()
    (pkg1 / "__init__.py").write_text("a = 1\n", encoding="utf8")
    pkg2 = tmp_path / "pkg2"
    pkg2.mkdir()
    (pkg2 / "__init__.py").write_text("b = 2\n", encoding="utf8")

    # Extension error returns 1
    assert cli.dump(packages=["pkg1"], extensions=["nonexistent_ext_xyz"], search_paths=[tmp_path]) == 1

    # Multiple packages dumped to single file
    out_file = tmp_path / "dump.json"
    ret = cli.dump(
        packages=["pkg1", "pkg2"],
        output=str(out_file),
        full=False,
        docstring_parser=None,
        docstring_options={},
        extensions=[],
        resolve_aliases=False,
        resolve_implicit=False,
        resolve_external=None,
        allow_inspection=True,
        force_inspection=False,
        search_paths=[tmp_path],
        append_sys_path=True,
        find_stubs_package=False,
        stats=True,
    )
    assert ret == 0
    assert out_file.exists()

    # Multiple packages dumped to directory template
    out_dir = tmp_path / "dumps" / "{package}.json"
    (tmp_path / "dumps").mkdir()
    ret = cli.dump(
        packages=["pkg1", "pkg2"],
        output=str(out_dir),
        full=True,
        docstring_parser=None,
        docstring_options={},
        extensions=[],
        search_paths=[tmp_path],
    )
    assert ret == 0
    assert (tmp_path / "dumps" / "pkg1.json").exists()
    assert (tmp_path / "dumps" / "pkg2.json").exists()

    # Single package with error returns 1
    ret_err = cli.dump(
        packages=["nonexistent_pkg_xyz_999"],
        output=None,
        search_paths=[tmp_path],
    )
    assert ret_err == 1
    capsys.readouterr()


def test_check_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test `check` subcommand and error handling."""
    from griffe._internal import git as git_mod  # noqa: PLC0415
    from griffe._internal import loader as loader_mod  # noqa: PLC0415
    from griffe._internal.models import Attribute, Module  # noqa: PLC0415

    old_mod = Module("pkg", filepath=tmp_path / "pkg" / "__init__.py")
    old_mod["x"] = Attribute("x", value="1", lineno=1, endlineno=1, parent=old_mod)
    new_mod = Module("pkg", filepath=tmp_path / "pkg" / "__init__.py")

    monkeypatch.setattr(git_mod, "_get_repo_root", lambda *_a, **_kw: str(tmp_path))
    monkeypatch.setattr(git_mod, "_get_latest_tag", lambda *_a, **_kw: "v1.0")
    monkeypatch.setattr(loader_mod, "load_git", lambda *_a, **_kw: old_mod if _kw.get("ref") == "v1.0" else new_mod)
    monkeypatch.setattr(loader_mod, "load", lambda *_a, **_kw: new_mod)
    monkeypatch.setattr(loader_mod, "load_pypi", lambda *_a, **_kw: old_mod if _a[2] == "==1.0" else new_mod)

    # ExtensionError returns 1
    assert cli.check(package="pkg", extensions=["nonexistent_ext_xyz"]) == 1

    # PyPI against with base_ref
    monkeypatch.setenv("FORCE_COLOR", "true")
    assert cli.check(package="pkg", against="pkg==1.0", base_ref="pkg==2.0", color=None, verbose=True) == 1
    # PyPI against without base_ref
    assert cli.check(package="pkg", against="==1.0", base_ref=None, color=False, style="oneline") == 1
    # PyPI against with invalid base_ref
    with pytest.raises(ValueError, match="not a valid dependency specifier"):
        cli.check(package="pkg", against="==1.0", base_ref="invalid_ref")

    # Git against with base_ref -> returns 1 (breakages)
    assert cli.check(package="pkg", against="v1.0", base_ref="v2.0", append_sys_path=True) == 1

    # Git against without base_ref -> returns 1 (breakages)
    assert cli.check(package="pkg", against="v1.0", base_ref=None) == 1

    # No breakages -> returns 0
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setattr(loader_mod, "load", lambda *_a, **_kw: old_mod)
    assert cli.check(package="pkg", against="v1.0", base_ref=None, color=None, style=ExplanationStyle.VERBOSE) == 0

    # Empty against tag -> returns 0
    monkeypatch.setattr(git_mod, "_get_latest_tag", lambda *_a, **_kw: "")
    assert cli.check(package="pkg", against=None) == 0

    # GitError when against is None -> returns 2
    def raise_git_err(*_a: object, **_kw: object) -> str:
        raise GitError("git error")

    monkeypatch.setattr(git_mod, "_get_latest_tag", raise_git_err)
    assert cli.check(package="pkg", against=None) == 2


def test_main_check_and_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test `main` with subcommands, color envs, and log levels."""
    monkeypatch.setenv("FORCE_COLOR", "true")
    monkeypatch.setattr(cli, "check", lambda **_kw: 0)
    assert cli.main(["check", "griffe", "-a", "HEAD"]) == 0

    monkeypatch.setenv("FORCE_COLOR", "false")
    assert cli.main(["check", "griffe", "-a", "HEAD"]) == 0
    assert cli.main(["check", "griffe", "-a", "HEAD", "--color"]) == 0
    assert cli.main(["check", "griffe", "-a", "HEAD", "--no-color"]) == 0

    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert cli.main(["check", "griffe", "-a", "HEAD"]) == 0

    # Invalid log level
    orig_parse = cli.get_parser

    def mock_get_parser() -> object:
        p = orig_parse()
        orig_pa = p.parse_args

        def custom_pa(args: list[str] | None = None) -> object:
            ns = orig_pa(args)
            ns.log_level = "INVALID_LEVEL"
            return ns

        p.parse_args = custom_pa  # ty:ignore[invalid-assignment]
        return p

    monkeypatch.setattr(cli, "get_parser", mock_get_parser)
    assert cli.main(["check", "griffe"]) == 1
