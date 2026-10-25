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

# Tests for creating a griffe Module from specific commits in a git repository.

from __future__ import annotations

import shutil
from subprocess import run
from typing import TYPE_CHECKING

import pytest

from griffe import Module, load_git
from tests import FIXTURES_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_gitconfig import GitConfig

REPO_NAME = "my-repo"
REPO_SOURCE = FIXTURES_DIR / "_repo"
MODULE_NAME = "my_module"


def _copy_contents(src: Path, dst: Path) -> None:
    """Copy *contents* of src into dst.

    Parameters:
        src: the folder whose contents will be copied to dst
        dst: the destination folder
    """
    dst.mkdir(exist_ok=True, parents=True)
    for src_path in src.iterdir():
        dst_path = dst / src_path.name
        if src_path.is_dir():
            _copy_contents(src_path, dst_path)
        else:
            shutil.copy(src_path, dst_path)


@pytest.fixture
def git_repo(tmp_path: Path, gitconfig: GitConfig) -> Path:  # noqa: ARG001
    """Fixture that creates a git repo with multiple tagged versions.

    For each directory in `tests/test_git/_repo/`

        - the contents of the directory will be copied into the temporary repo
        - all files will be added and commited
        - the commit will be tagged with the name of the directory

    To add to these tests (i.e. to simulate change over time), either modify one of
    the files in the existing `v0.1.0`, `v0.2.0` folders, or continue adding new
    version folders following the same pattern.

    Parameters:
        tmp_path: temporary directory fixture

    Returns:
        Path: path to temporary repo.
    """
    repo_path = tmp_path / REPO_NAME
    repo_path.mkdir()
    run(["git", "-C", str(repo_path), "init"], check=True)
    for tagdir in REPO_SOURCE.iterdir():
        ver = tagdir.name
        _copy_contents(tagdir, repo_path)
        run(["git", "-C", str(repo_path), "add", "."], check=True)
        run(["git", "-C", str(repo_path), "commit", "-m", f"feat: {ver} stuff"], check=True)
        run(["git", "-C", str(repo_path), "tag", ver], check=True)
    return repo_path


def test_load_git(git_repo: Path) -> None:
    """Test that we can load modules from different commits from a git repo.

    Parameters:
        git_repo: temporary git repo
    """
    v1 = load_git(MODULE_NAME, ref="v0.1.0", repo=git_repo)
    v2 = load_git(MODULE_NAME, ref="v0.2.0", repo=git_repo)
    assert isinstance(v1, Module)
    assert isinstance(v2, Module)
    assert v1.attributes["__version__"].value == "'0.1.0'"
    assert v2.attributes["__version__"].value == "'0.2.0'"


def test_load_git_errors(git_repo: Path) -> None:
    """Test that we get informative errors for various invalid inputs.

    Parameters:
        git_repo: temporary git repo
    """
    with pytest.raises(OSError, match="Not a git repository"):
        load_git(MODULE_NAME, ref="v0.2.0", repo="not-a-repo")

    with pytest.raises(RuntimeError, match="Could not create git worktree"):
        load_git(MODULE_NAME, ref="invalid-tag", repo=git_repo)

    with pytest.raises(ImportError, match="ModuleNotFoundError: No module named 'not_a_real_module'"):
        load_git("not_a_real_module", ref="v0.2.0", repo=git_repo)


def test_git_failures(tmp_path: Path) -> None:
    """Test failures to use Git."""
    pytest.importorskip("griffecli")
    from griffe import check  # noqa: PLC0415

    assert check(tmp_path) == 2


def test_git_utilities_and_git_info(git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test GitInfo, remote URL parsing, service detection, and tag helpers."""
    from pathlib import Path  # noqa: PLC0415

    from griffe._internal import git as git_mod  # noqa: PLC0415
    from griffe._internal.exceptions import GitError  # noqa: PLC0415

    # Test _copy_contents with nested subdirectory
    src_dir = tmp_path / "src_copy"
    (src_dir / "nested").mkdir(parents=True)
    (src_dir / "nested" / "file.txt").write_text("hi", encoding="utf8")
    dst_dir = tmp_path / "dst_copy"
    _copy_contents(src_dir, dst_dir)
    assert (dst_dir / "nested" / "file.txt").read_text(encoding="utf8") == "hi"

    # _assert_git_repo when git is missing
    monkeypatch.setattr(git_mod.shutil, "which", lambda _cmd: None)
    with pytest.raises(RuntimeError, match="Could not find git executable"):
        git_mod._assert_git_repo(git_repo)
    monkeypatch.undo()

    # _get_latest_tag with file path, string path, and GitError
    assert git_mod._get_latest_tag(str(git_repo / "README.md"))
    assert git_mod._get_latest_tag(git_repo)

    def raise_git_err(*_a: object, **_kw: object) -> str:
        raise GitError("failed")

    monkeypatch.setattr(git_mod, "_git", raise_git_err)
    with pytest.raises(GitError, match="Cannot list Git tags"):
        git_mod._get_latest_tag(git_repo)
    monkeypatch.undo()

    # _get_repo_root with file path
    assert git_mod._get_repo_root(str(git_repo / "README.md")) == git_repo.resolve()

    # _get_git_remote_url variations
    monkeypatch.setenv("GRIFFE_GIT_REMOTE_URL", "https://custom.example.com/repo")
    assert git_mod._get_git_remote_url(git_repo) == "https://custom.example.com/repo"
    monkeypatch.delenv("GRIFFE_GIT_REMOTE_URL")

    monkeypatch.setattr(git_mod, "_git", lambda *_a, **_kw: "git@github.com:user/repo.git")
    assert git_mod._get_git_remote_url(git_repo) == "https://github.com/user/repo"

    monkeypatch.setattr(git_mod, "_git", lambda *_a, **_kw: "https://user:token@gitlab.com/user/repo.git")
    assert git_mod._get_git_remote_url(git_repo) == "https://gitlab.com/user/repo"

    monkeypatch.setattr(git_mod, "_git", lambda *_a, **_kw: "rad://z4M5XTPDD4Wh1sm8iPCenF85J3z8Z")
    assert git_mod._get_git_remote_url(git_repo) == "rad://z4M5XTPDD4Wh1sm8iPCenF85J3z8Z"
    monkeypatch.undo()

    # _get_git_known_service variations
    monkeypatch.setenv("GRIFFE_GIT_SERVICE", "invalid_service")
    assert git_mod._get_git_known_service("https://github.com/user/repo") is None
    monkeypatch.setenv("GRIFFE_GIT_SERVICE", "github")
    assert git_mod._get_git_known_service("https://custom.local/user/repo") == "github"
    monkeypatch.delenv("GRIFFE_GIT_SERVICE")
    assert git_mod._get_git_known_service("https://github.com/user/repo") == "github"
    assert git_mod._get_git_known_service("https://unknown.host.xyz/user/repo") is None

    # _get_radicle_url and _get_source_link for all services
    assert "rad:z123" in git_mod._get_radicle_url("rad://z123", "abc", "a.py", 1, 5)
    assert git_mod._get_radicle_url("https://custom", "abc", "a.py", 1, 5) == "https://custom/tree/abc/a.py#L1"
    for svc in git_mod._service_to_url:
        assert git_mod._get_source_link(
            service=svc,  # ty:ignore[invalid-argument-type]
            remote_url="https://example.com/u/r",
            commit_hash="deadbeef",
            filepath=Path("a/b.py"),
            lineno=1,
            endlineno=2,
        )
        assert git_mod._get_source_link(
            service=svc,  # ty:ignore[invalid-argument-type]
            remote_url="https://example.com/u/r",
            commit_hash="deadbeef",
            filepath="a/b.py",
            lineno=1,
            endlineno=2,
        )

    # _get_git_commit_hash with env var and git call
    monkeypatch.setenv("GRIFFE_GIT_COMMIT_HASH", "1234567")
    assert git_mod._get_git_commit_hash(git_repo) == "1234567"
    monkeypatch.delenv("GRIFFE_GIT_COMMIT_HASH")
    assert git_mod._get_git_commit_hash(git_repo)

    # GitInfo.from_package edge cases
    mod_builtin = Module("b", filepath=None)
    assert git_mod.GitInfo.from_package(mod_builtin) is None

    mod_outside = Module("out", filepath=tmp_path / "outside.py")
    assert git_mod.GitInfo.from_package(mod_outside) is None

    # Ignored file in git_repo
    (git_repo / ".gitignore").write_text("ignored.py\n", encoding="utf8")
    ignored_file = git_repo / "ignored.py"
    ignored_file.write_text("x = 1\n", encoding="utf8")
    mod_ignored = Module("ign", filepath=ignored_file)
    assert git_mod.GitInfo.from_package(mod_ignored) is None

    # Tracked file in git_repo without remote URL -> None
    tracked_file = git_repo / MODULE_NAME / "__init__.py"
    mod_tracked = Module("tr", filepath=[tracked_file])
    assert git_mod.GitInfo.from_package(mod_tracked) is None

    # Tracked file with valid remote URL -> GitInfo instance
    monkeypatch.setenv("GRIFFE_GIT_REMOTE_URL", "https://github.com/user/repo")
    info = git_mod.GitInfo.from_package(mod_tracked)
    assert info is not None
    assert info.get_source_link(Path("a.py"), 1, 10)
