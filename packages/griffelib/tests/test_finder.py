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

# Tests for the `finder` module.

from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

import pytest

from griffe import Module, ModuleFinder, NamespacePackage, Package, temporary_pypackage
from griffe._internal.finder import _handle_editable_module, _handle_pth_file


@pytest.mark.parametrize(
    ("pypackage", "module", "add_to_search_path", "expected_top_name", "expected_top_path"),
    [
        (("a", ["b.py"]), "a/b.py", True, "a", "a/__init__.py"),
        (("a", ["b.py"]), "a/b.py", False, "a", "a/__init__.py"),
        (("a/b", ["c.py"]), "a/b/c.py", True, "a", "a"),
        (("a/b", ["c.py"]), "a/b/c.py", False, "b", "a/b/__init__.py"),
    ],
)
def test_find_module_with_path(
    pypackage: tuple[str, list[str]],
    module: str,
    add_to_search_path: bool,
    expected_top_name: str,
    expected_top_path: str,
) -> None:
    """Check that the finder can find modules using strings and Paths.

    Parameters:
        pypackage: A temporary package (metadata) on the file system (parametrized).
        module: The module path to load (parametrized).
        add_to_search_path: Whether to add the temporary package parent path to the finder search paths (parametrized).
        expected_top_name: Expected top module name (parametrized).
        expected_top_path: Expected top module path (parametrized).
    """
    with temporary_pypackage(*pypackage) as tmp_package:
        finder = ModuleFinder(search_paths=[tmp_package.tmpdir] if add_to_search_path else None)
        _, package = finder.find_spec(tmp_package.tmpdir / module)
        assert package.name == expected_top_name
        if isinstance(package, NamespacePackage):
            assert package.path == [tmp_package.tmpdir / expected_top_path]
        else:
            assert package.path == tmp_package.tmpdir / expected_top_path


@pytest.mark.parametrize(
    "statement",
    [
        "__import__('pkg_resources').declare_namespace(__name__)",
        "__path__ = __import__('pkgutil').extend_path(__path__, __name__)",
    ],
)
def test_find_pkg_style_namespace_packages(statement: str) -> None:
    """Check that the finder can find pkg-style namespace packages.

    Parameters:
        statement: The statement in the `__init__` module allowing to mark the package as namespace.
    """
    with (
        temporary_pypackage("namespace/package1") as tmp_package1,
        temporary_pypackage("namespace/package2") as tmp_package2,
    ):
        tmp_package1.path.parent.joinpath("__init__.py").write_text(statement, encoding="utf8")
        tmp_package2.path.parent.joinpath("__init__.py").write_text(statement, encoding="utf8")
        finder = ModuleFinder(search_paths=[tmp_package1.tmpdir, tmp_package2.tmpdir])
        _, package = finder.find_spec("namespace")
        assert package.name == "namespace"
        assert isinstance(package, NamespacePackage)
        assert package.path == [tmp_package1.path.parent, tmp_package2.path.parent]


@pytest.mark.skipif(not Path("packages").exists(), reason="not running from monorepo root")
def test_pth_file_handling(tmp_path: Path) -> None:
    """Assert .pth files are correctly handled.

    Parameters:
        tmp_path: Pytest fixture.
    """
    pth_file = tmp_path / "hello.pth"
    pth_file.write_text(
        dedent(
            """
            # comment

            import thing
            import\tthing
            /doesnotexist
            packages/griffelib/tests
            """,
        ),
        encoding="utf8",
    )
    paths = [sp.path for sp in _handle_pth_file(pth_file)]
    assert paths == [Path("packages/griffelib/tests")]


@pytest.mark.skipif(not Path("packages").exists(), reason="not running from monorepo root")
def test_pth_file_handling_with_semi_colon(tmp_path: Path) -> None:
    """Assert .pth files are correctly handled.

    Parameters:
        tmp_path: Pytest fixture.
    """
    pth_file = tmp_path / "hello.pth"
    pth_file.write_text(
        dedent(
            """
            # comment
            import thing; import\tthing; /doesnotexist; packages/griffelib/tests
            """,
        ),
        encoding="utf8",
    )
    paths = [sp.path for sp in _handle_pth_file(pth_file)]
    assert paths == [Path("packages/griffelib/tests")]


@pytest.mark.parametrize("editable_file_name", ["__editables_whatever.py", "_editable_impl_whatever.py"])
def test_editables_file_handling(tmp_path: Path, editable_file_name: str) -> None:
    """Assert editable modules by `editables` are handled.

    Parameters:
        tmp_path: Pytest fixture.
    """
    pth_file = tmp_path / editable_file_name
    pth_file.write_text("hello\nF.map_module('griffe', 'packages/griffelib/src/griffe/__init__.py')", encoding="utf8")
    paths = [sp.path for sp in _handle_editable_module(pth_file)]
    assert paths == [Path("packages/griffelib/src")]


@pytest.mark.parametrize("annotation", ["", ": dict[str, str]"])
def test_setuptools_file_handling(tmp_path: Path, annotation: str) -> None:
    """Assert editable modules by `setuptools` are handled.

    Parameters:
        tmp_path: Pytest fixture.
        annotation: The type annotation of the MAPPING variable.
    """
    pth_file = tmp_path / "__editable__whatever.py"
    pth_file.write_text(f"hello\nMAPPING{annotation} = {{'griffe': 'src/griffe'}}", encoding="utf8")
    paths = [sp.path for sp in _handle_editable_module(pth_file)]
    assert paths == [Path("src")]


@pytest.mark.parametrize("annotation", ["", ": dict[str, str]"])
def test_setuptools_file_handling_multiple_paths(tmp_path: Path, annotation: str) -> None:
    """Assert editable modules by `setuptools` are handled when multiple packages are installed in the same editable.

    Parameters:
        tmp_path: Pytest fixture.
        annotation: The type annotation of the MAPPING variable.
    """
    pth_file = tmp_path / "__editable__whatever.py"
    pth_file.write_text(
        "hello=1\n"
        f"MAPPING{annotation} = {{\n'griffe':\n 'src1/griffe', 'briffe':'src2/briffe'}}\n"
        "def printer():\n  print(hello)",
        encoding="utf8",
    )
    paths = [sp.path for sp in _handle_editable_module(pth_file)]
    assert paths == [Path("src1"), Path("src2")]


def test_scikit_build_core_file_handling(tmp_path: Path) -> None:
    """Assert editable modules by `scikit-build-core` are handled.

    Parameters:
        tmp_path: Pytest fixture.
    """
    pth_file = tmp_path / "_whatever_editable.py"
    pth_file.write_text(
        "hello=1\ninstall({'whatever': '/path/to/whatever'}, {'whatever.else': '/else'}, None, False, True)",
        encoding="utf8",
    )
    # The second dict is not handled: scikit-build-core puts these files
    # in a location that Griffe won't be able to discover anyway
    # (they don't respect standard package or namespace package layouts,
    # and rely on dynamic meta path finder stuff).
    paths = [sp.path for sp in _handle_editable_module(pth_file)]
    assert paths == [Path("/path/to/whatever")]


@pytest.mark.skipif(not Path("packages").exists(), reason="not running from monorepo root")
def test_meson_python_file_handling(tmp_path: Path) -> None:
    """Assert editable modules by `meson-python` are handled.

    Parameters:
        tmp_path: Pytest fixture.
    """
    pth_file = tmp_path / "_whatever_editable_loader.py"
    pth_file.write_text(
        # The path in argument 2 suffixed with src must exist, so we pass `packages/griffelib`.
        "hello=1\ninstall({'griffe', 'hello'}, 'packages/griffelib', ['/tmp/ninja'], False)",
        encoding="utf8",
    )
    search_paths = _handle_editable_module(pth_file)
    assert all(sp.always_scan_for == "griffe" for sp in search_paths)
    paths = [sp.path for sp in search_paths]
    assert paths == [Path("packages/griffelib/src")]


@pytest.mark.parametrize(
    ("first", "second", "find_stubs", "expect"),
    [
        ("package", "stubs", True, "both"),
        ("stubs", "package", True, "both"),
        ("package", None, True, "package"),
        (None, "package", True, "package"),
        ("stubs", None, True, "stubs"),
        (None, "stubs", True, "stubs"),
        (None, None, True, "none"),
        ("package", "stubs", False, "package"),
        ("stubs", "package", False, "package"),
        ("package", None, False, "package"),
        (None, "package", False, "package"),
        ("stubs", None, False, "none"),
        (None, "stubs", False, "none"),
        (None, None, False, "none"),
    ],
)
def test_finding_stubs_packages(
    tmp_path: Path,
    first: str | None,
    second: str | None,
    find_stubs: bool,
    expect: str,
) -> None:
    """Find stubs-only packages.

    Parameters:
        tmp_path: Pytest fixture.
    """
    search_path1 = tmp_path / "sp1"
    search_path2 = tmp_path / "sp2"
    search_path1.mkdir()
    search_path2.mkdir()

    if first == "package":
        package = search_path1 / "package"
        package.mkdir()
        package.joinpath("__init__.py").touch()
    elif first == "stubs":
        stubs = search_path1 / "package-stubs"
        stubs.mkdir()
        stubs.joinpath("__init__.pyi").touch()

    if second == "package":
        package = search_path2 / "package"
        package.mkdir()
        package.joinpath("__init__.py").touch()
    elif second == "stubs":
        stubs = search_path2 / "package-stubs"
        stubs.mkdir()
        stubs.joinpath("__init__.pyi").touch()

    finder = ModuleFinder([search_path1, search_path2])

    if expect == "none":
        with pytest.raises(ModuleNotFoundError):
            finder.find_spec("package", try_relative_path=False, find_stubs_package=find_stubs)
        return

    name, result = finder.find_spec("package", try_relative_path=False, find_stubs_package=find_stubs)
    assert name == "package"

    if expect == "both":
        assert isinstance(result, Package)
        assert result.path.suffix == ".py"
        assert not result.path.parent.name.endswith("-stubs")
        assert result.stubs
        assert result.stubs.suffix == ".pyi"
        assert result.stubs.parent.name.endswith("-stubs")
    elif expect == "package":
        assert isinstance(result, Package)
        assert result.path.suffix == ".py"
        assert not result.path.parent.name.endswith("-stubs")
        assert result.stubs is None
    else:
        assert expect == "stubs"
        assert isinstance(result, Package)
        assert result.path.suffix == ".pyi"
        assert result.path.parent.name.endswith("-stubs")
        assert result.stubs is None


@pytest.mark.parametrize("namespace_package", [False, True])
def test_scanning_package_and_module_with_same_names(namespace_package: bool) -> None:
    """The finder correctly scans package and module having same the name.

    Parameters:
        namespace_package: Whether the temporary package is a namespace one.
    """
    init = not namespace_package
    with temporary_pypackage("pkg", ["pkg/mod.py", "mod/mod.py"], init=init, inits=init) as tmp_package:
        # Here we must make sure that all paths are relative
        # to correctly assert the finder's behavior,
        # so we pass `.` and actually enter the temporary directory.
        path = Path(tmp_package.name)
        filepath: Path | list[Path] = [path] if namespace_package else path
        old = Path.cwd()
        os.chdir(tmp_package.path.parent)
        try:
            finder = ModuleFinder(search_paths=[])
            found = [path for _, path in finder.submodules(Module("pkg", filepath=filepath))]
        finally:
            os.chdir(old)
        check = (path / "pkg/mod.py", path / "mod/mod.py")
        for mod in check:
            assert mod in found


def test_not_finding_namespace_package_twice() -> None:
    """Deduplicate paths when finding namespace packages."""
    with temporary_pypackage("pkg", ["pkg/mod.py", "mod/mod.py"], init=False, inits=False) as tmp_package:
        old = Path.cwd()
        os.chdir(tmp_package.tmpdir)
        try:
            finder = ModuleFinder(search_paths=[Path(), tmp_package.tmpdir])
            found = finder.find_package("pkg")
        finally:
            os.chdir(old)
        assert isinstance(found, NamespacePackage)
        assert len(found.path) == 1


def test_finder_edge_cases(tmp_path: Path) -> None:
    """Test `ModuleFinder` edge cases (relative search path, broken symlinks, editable hooks, submodules)."""
    from griffe._internal import finder as finder_mod  # noqa: PLC0415
    from griffe._internal.exceptions import UnhandledEditableModuleError  # noqa: PLC0415

    # Relative path resolved to absolute, duplicate search path ignored
    f_no_scan = ModuleFinder(search_paths=[Path(), Path(), tmp_path])
    assert len(f_no_scan.search_paths) == 2

    # find_spec with try_relative_path=True when module does not exist as a path
    with pytest.raises(ModuleNotFoundError):
        f_no_scan.find_spec("nonexistent_local_module_xyz", try_relative_path=True)

    # find_spec with try_relative_path=True for a single .py module
    single_py = tmp_path / "single_mod.py"
    single_py.write_text("x = 1\n", encoding="utf8")
    name, pkg = ModuleFinder(search_paths=[tmp_path]).find_spec(single_py, try_relative_path=True)
    assert name == "single_mod"
    assert isinstance(pkg, NamespacePackage)

    # find_spec with unreadable file or invalid directory name
    invalid_dir = tmp_path / "invalid-pkg-name"
    invalid_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        f_no_scan.find_spec(tmp_path / "does_not_exist_at_all", try_relative_path=True)
    with pytest.raises(ModuleNotFoundError):
        f_no_scan.find_spec(invalid_dir, try_relative_path=True)

    # find_package with both package and stubs (and stubs-only when find_stubs_package=True)
    pkg_dir = tmp_path / "my_typed_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("x = 1\n", encoding="utf8")
    stubs_dir = tmp_path / "my_typed_pkg-stubs"
    stubs_dir.mkdir()
    (stubs_dir / "__init__.pyi").write_text("x: int\n", encoding="utf8")

    finder_stubs = ModuleFinder(search_paths=[tmp_path])
    _, found_pkg = finder_stubs.find_spec("my_typed_pkg", find_stubs_package=True)
    assert isinstance(found_pkg, Package)
    assert found_pkg.stubs is not None

    # Stubs for a single-file module where found_module is a list
    single_stub_mod = tmp_path / "single_with_stubs.py"
    single_stub_mod.write_text("a = 1\n", encoding="utf8")
    single_stubs_dir = tmp_path / "single_with_stubs-stubs"
    single_stubs_dir.mkdir()
    (single_stubs_dir / "__init__.pyi").write_text("a: int\n", encoding="utf8")
    finder_stubs2 = ModuleFinder(search_paths=[tmp_path])
    _, found_single_with_stubs = finder_stubs2.find_spec("single_with_stubs", find_stubs_package=True)
    assert isinstance(found_single_with_stubs, Package)
    assert found_single_with_stubs.stubs is not None

    # Submodules iteration with __pycache__, hidden files, .pyc, and non-matching extensions
    from griffe._internal.models import Module  # noqa: PLC0415

    (pkg_dir / "__pycache__").mkdir()
    (pkg_dir / "__pycache__" / "cached.pyc").write_bytes(b"")
    (pkg_dir / ".hidden.py").write_text("", encoding="utf8")
    (pkg_dir / "readme.txt").write_text("", encoding="utf8")
    (pkg_dir / "mod.py").write_text("x = 1\n", encoding="utf8")
    (pkg_dir / "mod.pyi").write_text("x: int\n", encoding="utf8")
    (pkg_dir / "only_stub.pyi").write_text("y: int\n", encoding="utf8")
    (pkg_dir / "subpkg").mkdir()
    (pkg_dir / "subpkg" / "__init__.pyi").write_text("z: int\n", encoding="utf8")
    submods = list(finder_stubs.submodules(Module("my_typed_pkg", filepath=found_pkg.path)))
    assert any(name_parts == ("mod",) for name_parts, _ in submods)

    # Submodules of a single-file Module returns empty
    assert list(finder_stubs.submodules(Module("single_mod", filepath=single_py))) == []

    # _contents with non-existent directory
    assert finder_stubs._contents(tmp_path / "nonexistent_dir_xyz") == []

    # _filter_py_modules when directory contains no .py/.pyi files
    empty_sub = pkg_dir / "empty_sub"
    empty_sub.mkdir()
    assert list(finder_stubs._filter_py_modules(pkg_dir))

    # _handle_pth_file and _handle_editable_module edge cases
    bad_pth = tmp_path / "bad.pth"
    bad_pth.write_bytes(b"\xff\xfe")
    assert finder_mod._handle_pth_file(bad_pth) == []

    # Editable pth where line doesn't start with import (regular path line inside __editable__.pth)
    edit_non_import = tmp_path / "__editable__non_import.pth"
    edit_non_import.write_text(f"# comment\n{pkg_dir}\n{tmp_path / 'nonexistent_dir_xyz'}\n", encoding="utf8")
    assert finder_mod._handle_pth_file(edit_non_import)

    edit_pth1 = tmp_path / "__editable__pkg1.pth"
    edit_pth1.write_text("import _editable_impl_1\n", encoding="utf8")
    impl_py1 = tmp_path / "_editable_impl_1.py"
    impl_py1.write_text(f"F.map_module('pkg', '{pkg_dir}/__init__.py')\n", encoding="utf8")
    assert finder_mod._handle_pth_file(edit_pth1)

    impl_py1_non_init = tmp_path / "_editable_impl_2.py"
    impl_py1_non_init.write_text(f"F.map_module('pkg', '{pkg_dir}/mod.py')\n", encoding="utf8")
    assert finder_mod._handle_editable_module(impl_py1_non_init)

    with pytest.raises(UnhandledEditableModuleError):
        finder_mod._handle_editable_module(tmp_path / "_editable_impl_missing.py")

    edit_pth2 = tmp_path / "__editable__pkg2.pth"
    edit_pth2.write_text(
        "import __editable___pkg2_finder; __editable___pkg2_finder.install()\n",
        encoding="utf8",
    )
    impl_py2 = tmp_path / "__editable___pkg2_finder.py"
    impl_py2.write_text(
        "def f(): pass\nOTHER = 1\nMAPPING: dict[str, str] = {'pkg': '" + str(pkg_dir) + "/__init__.py'}\n",
        encoding="utf8",
    )
    assert finder_mod._handle_pth_file(edit_pth2)

    impl_py2_no_map = tmp_path / "__editable___pkg3_finder.py"
    impl_py2_no_map.write_text("OTHER = 1\n", encoding="utf8")
    with pytest.raises(UnhandledEditableModuleError):
        finder_mod._handle_editable_module(impl_py2_no_map)

    # _handle_editable_module with meson-python style _*_editable_loader.py
    meson_dir = tmp_path / "meson_build"
    (meson_dir / "src" / "meson_pkg").mkdir(parents=True)
    meson_py = tmp_path / "_meson_editable_loader.py"
    meson_py.write_text(
        f"x = 1\ninstall({{'meson_pkg'}}, '{meson_dir}', ['path'], False)\n",
        encoding="utf8",
    )
    assert finder_mod._handle_editable_module(meson_py)

    meson_py_no_install = tmp_path / "_meson2_editable_loader.py"
    meson_py_no_install.write_text("x = 1\n", encoding="utf8")
    with pytest.raises(UnhandledEditableModuleError):
        finder_mod._handle_editable_module(meson_py_no_install)

    unhandled_pth = tmp_path / "__editable__unhandled.pth"
    unhandled_pth.write_text("import something_completely_unknown\n", encoding="utf8")
    assert finder_mod._handle_pth_file(unhandled_pth) == []

    unhandled_py = tmp_path / "something_unknown.py"
    unhandled_py.write_text("x = 1\n", encoding="utf8")
    with pytest.raises(UnhandledEditableModuleError):
        finder_mod._handle_editable_module(unhandled_py)

    # insert_search_path duplicate vs new, find_spec with try_relative_path=True on relative string path
    f_no_scan.insert_search_path(0, tmp_path)
    f_no_scan.insert_search_path(0, pkg_dir)
    old_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        rel_name, _ = f_no_scan.find_spec("single_mod.py", try_relative_path=True)
        assert rel_name == "single_mod"
    finally:
        os.chdir(old_cwd)

    # find_package with dotted module_name and stubs-only when neither exists
    _, sub_found = finder_stubs.find_spec("my_typed_pkg.mod", try_relative_path=False)
    assert isinstance(sub_found, Package)
    with pytest.raises(ModuleNotFoundError):
        finder_stubs.find_package("nonexistent_top_pkg")
    with pytest.raises(ModuleNotFoundError):
        finder_stubs.find_spec("nonexistent_both_pkg_and_stubs", find_stubs_package=True)

    # Namespace package + Namespace stubs merged in find_spec
    ns_dir = tmp_path / "my_ns_pkg" / "sub"
    ns_dir.mkdir(parents=True)
    ns_stubs_dir = tmp_path / "my_ns_pkg-stubs" / "sub"
    ns_stubs_dir.mkdir(parents=True)
    finder_ns = ModuleFinder(search_paths=[tmp_path])
    _, found_ns = finder_ns.find_spec("my_ns_pkg", find_stubs_package=True)
    assert isinstance(found_ns, NamespacePackage)

    # iter_submodules with list of paths (namespace package) and seen subpackage skipping
    ns_part1 = tmp_path / "ns_scan_1" / "ns_p"
    ns_part2 = tmp_path / "ns_scan_2" / "ns_p"
    (ns_part1 / "subpkg").mkdir(parents=True)
    (ns_part1 / "subpkg" / "__init__.py").write_text("", encoding="utf8")
    (ns_part2 / "subpkg").mkdir(parents=True)
    (ns_part2 / "subpkg" / "skipped.py").write_text("", encoding="utf8")
    assert list(finder_ns.iter_submodules([ns_part1, ns_part2]))

    # _module_name_path with directory containing __init__.py and with __init__.py file directly
    assert finder_ns._module_name_path(pkg_dir)[0] == "my_typed_pkg"
    assert finder_ns._module_name_path(pkg_dir / "__init__.py")[0] == "my_typed_pkg"

    # _extend_from_pth_files with meson editable pth (always_scan_for)
    meson_pth = tmp_path / "__editable__meson.pth"
    meson_pth.write_text("import _meson_editable_loader\n", encoding="utf8")
    finder_with_meson = ModuleFinder(search_paths=[tmp_path])
    assert "meson_pkg" in finder_with_meson._always_scan_for

    # _top_module_name walking up parent directories with __init__.py when outside search_paths
    outside_root = tmp_path / "outside_search"
    outside_sub = outside_root / "top_pkg" / "mid_pkg" / "leaf.py"
    outside_sub.parent.mkdir(parents=True)
    (outside_root / "top_pkg" / "__init__.py").write_text("", encoding="utf8")
    (outside_root / "top_pkg" / "mid_pkg" / "__init__.py").write_text("", encoding="utf8")
    outside_sub.write_text("", encoding="utf8")
    finder_empty = ModuleFinder(search_paths=[pkg_dir])
    assert finder_empty._top_module_name(outside_sub) == "top_pkg"
