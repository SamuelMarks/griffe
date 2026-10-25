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

# Tests for the `loader` module.

from __future__ import annotations

import logging
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from griffe import (
    AliasResolutionError,
    ExprName,
    Extensions,
    GriffeLoader,
    temporary_inspected_package,
    temporary_pyfile,
    temporary_pypackage,
    temporary_visited_package,
)


def test_skip_load_event_traversal_without_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not traverse loaded objects when no extension implements load-event hooks."""
    with temporary_pypackage("package", {"__init__.py": "def function(): ..."}) as package:
        loader = GriffeLoader(extensions=Extensions(), search_paths=[package.tmpdir])

        def fail_if_called(_module: object) -> None:  # pragma: no cover
            raise AssertionError("load events were fired without hooks")

        monkeypatch.setattr(loader, "_fire_load_events", fail_if_called)
        loader.load("package")


def test_resolve_aliases_defers_caught_error_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not format alias errors that the resolver catches internally."""
    with temporary_pypackage("package", {"__init__.py": "from missing import value"}) as package:
        loader = GriffeLoader(search_paths=[package.tmpdir])
        loader.load("package")

        def fail_if_formatted(_error: AliasResolutionError) -> str:  # pragma: no cover
            raise AssertionError("caught alias-resolution error was formatted")

        monkeypatch.setattr(AliasResolutionError, "_format_message", fail_if_formatted)
        unresolved, _ = loader.resolve_aliases(implicit=True, external=False)

    assert unresolved == {"package.value"}


if TYPE_CHECKING:
    from pathlib import Path

    from griffe import Alias


def test_has_docstrings_does_not_try_to_resolve_alias() -> None:
    """Assert that checkins presence of docstrings does not trigger alias resolution."""
    with temporary_pyfile("""from abc import abstractmethod""") as (module_name, path):
        loader = GriffeLoader(search_paths=[path.parent])
        module = loader.load(module_name)
        loader.resolve_aliases()
        assert "abstractmethod" in module.members
        assert not module.has_docstrings


def test_recursive_wildcard_expansion() -> None:
    """Assert that wildcards are expanded recursively."""
    with temporary_pypackage("package", ["mod_a/mod_b/mod_c.py"]) as tmp_package:
        mod_a_dir = tmp_package.path / "mod_a"
        mod_b_dir = mod_a_dir / "mod_b"
        mod_a = mod_a_dir / "__init__.py"
        mod_b = mod_b_dir / "__init__.py"
        mod_c = mod_b_dir / "mod_c.py"
        mod_c.write_text("CONST_X = 'X'\nCONST_Y = 'Y'", encoding="utf8")
        mod_b.write_text("from .mod_c import *", encoding="utf8")
        mod_a.write_text("from .mod_b import *", encoding="utf8")

        loader = GriffeLoader(search_paths=[tmp_package.tmpdir])
        package = loader.load(tmp_package.name)

        assert "CONST_X" in package["mod_a.mod_b.mod_c"].members
        assert "CONST_Y" in package["mod_a.mod_b.mod_c"].members

        assert "CONST_X" not in package.members
        assert "CONST_Y" not in package.members

        loader.expand_wildcards(package)  # ty:ignore[invalid-argument-type]

        assert "CONST_X" in package["mod_a"].members
        assert "CONST_Y" in package["mod_a"].members
        assert "CONST_X" in package["mod_a.mod_b"].members
        assert "CONST_Y" in package["mod_a.mod_b"].members


def test_dont_shortcut_alias_chain_after_expanding_wildcards() -> None:
    """Assert public aliases paths are not resolved to canonical paths when expanding wildcards."""
    with temporary_pypackage("package", ["mod_a.py", "mod_b.py", "mod_c.py"]) as tmp_package:
        mod_a = tmp_package.path / "mod_a.py"
        mod_b = tmp_package.path / "mod_b.py"
        mod_c = tmp_package.path / "mod_c.py"

        mod_a.write_text("from package.mod_b import *\nclass Child(Base): ...\n", encoding="utf8")
        mod_b.write_text("from package.mod_c import Base\n__all__ = ['Base']\n", encoding="utf8")
        mod_c.write_text("class Base: ...\n", encoding="utf8")

        loader = GriffeLoader(search_paths=[tmp_package.tmpdir])
        package = loader.load(tmp_package.name)
        loader.resolve_aliases()
        child = package["mod_a.Child"]
        assert child.bases
        base = child.bases[0]
        assert isinstance(base, ExprName)
        assert base.name == "Base"
        assert base.canonical_path == "package.mod_b.Base"


def test_dont_overwrite_lower_member_when_expanding_wildcard() -> None:
    """Check that we don't overwrite a member defined after the import when expanding a wildcard."""
    with temporary_pypackage("package", ["mod_a.py", "mod_b.py"]) as tmp_package:
        mod_a = tmp_package.path / "mod_a.py"
        mod_b = tmp_package.path / "mod_b.py"

        mod_a.write_text("overwritten = 0\nfrom package.mod_b import *\nnot_overwritten = 0\n", encoding="utf8")
        mod_b.write_text("overwritten = 1\nnot_overwritten = 1\n", encoding="utf8")

        loader = GriffeLoader(search_paths=[tmp_package.tmpdir])
        package = loader.load(tmp_package.name)
        loader.resolve_aliases()
        assert package["mod_a.overwritten"].value == "1"
        assert package["mod_a.not_overwritten"].value == "0"


def test_load_data_from_stubs() -> None:
    """Check that the loader is able to load data from stubs / `*.pyi` files."""
    with temporary_pypackage("package", ["_rust_notify.pyi"]) as tmp_package:
        # Code taken from samuelcolvin/watchfiles project.
        code = '''
            from typing import List, Literal, Optional, Protocol, Set, Tuple, Union

            __all__ = ['RustNotify']

            class AbstractEvent(Protocol):
                def is_set(self) -> bool: ...

            class RustNotify:
                """
                Interface to the Rust [notify](https://crates.io/crates/notify) crate which does
                the heavy lifting of watching for file changes and grouping them into a single event.
                """

                def __init__(self, watch_paths: List[str], debug: bool) -> None:
                    """
                    Create a new RustNotify instance and start a thread to watch for changes.

                    `FileNotFoundError` is raised if one of the paths does not exist.

                    Args:
                        watch_paths: file system paths to watch for changes, can be directories or files
                        debug: if true, print details about all events to stderr
                    """
        '''
        tmp_package.path.joinpath("_rust_notify.pyi").write_text(dedent(code), encoding="utf8")
        tmp_package.path.joinpath("__init__.py").write_text(
            "from ._rust_notify import RustNotify\n__all__ = ['RustNotify']",
            encoding="utf8",
        )
        loader = GriffeLoader(search_paths=[tmp_package.tmpdir])
        package = loader.load(tmp_package.name)
        loader.resolve_aliases()

        assert "_rust_notify" in package.members
        assert "RustNotify" in package.members
        assert package["RustNotify"].resolved


def test_load_from_both_py_and_pyi_files() -> None:
    """Check that the loader is able to merge data loaded from `*.py` and `*.pyi` files."""
    with temporary_pypackage("package", ["mod.py", "mod.pyi"]) as tmp_package:
        tmp_package.path.joinpath("mod.py").write_text(
            dedent(
                """
                CONST = 0

                class Class:
                    class_attr = True

                    def function1(self, arg1):
                        pass

                    def function2(self, arg1=2.2):
                        pass
                """,
            ),
            encoding="utf8",
        )
        tmp_package.path.joinpath("mod.pyi").write_text(
            dedent(
                """
                from typing import Sequence, overload

                CONST: int

                class Class:
                    class_attr: bool

                    @overload
                    def function1(self, arg1: str) -> Sequence[str]: ...
                    @overload
                    def function1(self, arg1: bytes) -> Sequence[bytes]: ...

                    def function2(self, arg1: float) -> float: ...
                """,
            ),
            encoding="utf8",
        )
        loader = GriffeLoader(search_paths=[tmp_package.tmpdir])
        package = loader.load(tmp_package.name)
        loader.resolve_aliases()

        assert "mod" in package.members
        mod = package["mod"]
        assert mod.filepath.suffix == ".py"

        assert "CONST" in mod.members
        const = mod["CONST"]
        assert const.value == "0"
        assert const.annotation.name == "int"

        assert "Class" in mod.members
        class_ = mod["Class"]

        assert "class_attr" in class_.members
        class_attr = class_["class_attr"]
        assert class_attr.value == "True"
        assert class_attr.annotation.name == "bool"

        assert "function1" in class_.members
        function1 = class_["function1"]
        assert len(function1.overloads) == 2

        assert "function2" in class_.members
        function2 = class_["function2"]
        assert function2.returns.name == "float"
        assert function2.parameters["arg1"].annotation.name == "float"
        assert function2.parameters["arg1"].default == "2.2"


def test_overwrite_module_with_attribute() -> None:
    """Check we are able to overwrite a module with an attribute."""
    with temporary_pypackage("package", ["mod.py"]) as tmp_package:
        tmp_package.path.joinpath("mod.py").write_text("mod: list = [0, 1, 2]", encoding="utf8")
        tmp_package.path.joinpath("__init__.py").write_text("from package.mod import *", encoding="utf8")
        loader = GriffeLoader(search_paths=[tmp_package.tmpdir])
        loader.load(tmp_package.name)
        loader.resolve_aliases()


def test_load_package_from_both_py_and_pyi_files() -> None:
    """Check that the loader is able to merge a package loaded from `*.py` and `*.pyi` files.

    This is a special case of the previous test: where the package itself has a top level
    `__init__.pyi` (not so uncommon).
    """
    with temporary_pypackage("package", ["__init__.py", "__init__.pyi"]) as tmp_package:
        tmp_package.path.joinpath("__init__.py").write_text("globals()['f'] = lambda x: str(x)", encoding="utf8")
        tmp_package.path.joinpath("__init__.pyi").write_text("def f(x: int) -> str: ...", encoding="utf8")

        loader = GriffeLoader(search_paths=[tmp_package.tmpdir])
        package = loader.load(tmp_package.name)
        assert "f" in package.members


def test_load_single_module_from_both_py_and_pyi_files() -> None:
    """Check that the loader is able to merge a single-module package loaded from `*.py` and `*.pyi` files.

    This is a special case of the previous test: where  the package is a single module
    distribution that also drops a `.pyi` file in site-packages.
    """
    with temporary_pypackage("just_a_folder", ["mod.py", "mod.pyi"]) as tmp_folder:
        tmp_folder.path.joinpath("__init__.py").unlink()
        tmp_folder.path.joinpath("mod.py").write_text("globals()['f'] = lambda x: str(x)", encoding="utf8")
        tmp_folder.path.joinpath("mod.pyi").write_text("def f(x: int) -> str: ...", encoding="utf8")

        loader = GriffeLoader(search_paths=[tmp_folder.path])
        package = loader.load("mod")
        assert "f" in package.members


def test_unsupported_item_in_all(caplog: pytest.LogCaptureFixture) -> None:
    """Check that unsupported items in `__all__` log a warning.

    Parameters:
        caplog: Pytest fixture to capture logs.
    """
    item_name = "XXX"
    with temporary_pypackage("package", ["mod.py"]) as tmp_folder:
        tmp_folder.path.joinpath("__init__.py").write_text(
            f"from .mod import {item_name}\n__all__ = [{item_name}]",
            encoding="utf8",
        )
        tmp_folder.path.joinpath("mod.py").write_text(f"class {item_name}: ...", encoding="utf8")
        loader = GriffeLoader(search_paths=[tmp_folder.tmpdir])
        loader.expand_exports(loader.load("package"))  # ty:ignore[invalid-argument-type]
    assert any(item_name in record.message and record.levelname == "WARNING" for record in caplog.records)


def test_skip_modules_with_dots_in_filename(caplog: pytest.LogCaptureFixture) -> None:
    """Check that modules with dots in their filenames are skipped.

    Parameters:
        caplog: Pytest fixture to capture logs.
    """
    caplog.set_level(logging.DEBUG)
    with temporary_pypackage("package", ["gunicorn.conf.py"]) as tmp_folder:
        loader = GriffeLoader(search_paths=[tmp_folder.tmpdir])
        loader.load("package")
    assert any("gunicorn.conf.py" in record.message and record.levelname == "DEBUG" for record in caplog.records)


def test_nested_namespace_packages() -> None:
    """Load a deeply nested namespace package."""
    with temporary_pypackage("a/b/c/d", ["mod.py"]) as tmp_folder:
        loader = GriffeLoader(search_paths=[tmp_folder.tmpdir])
        a_package = loader.load("a")
        assert "b" in a_package.members
        b_package = a_package.members["b"]
        assert "c" in b_package.members
        c_package = b_package.members["c"]
        assert "d" in c_package.members
        d_package = c_package.members["d"]
        assert "mod" in d_package.members


def test_multiple_nested_namespace_packages() -> None:
    """Load a deeply nested namespace package appearing in several places."""
    with temporary_pypackage("a/b/c/d", ["mod1.py"], init=False) as tmp_ns1:  # noqa: SIM117
        with temporary_pypackage("a/b/c/d", ["mod2.py"], init=False) as tmp_ns2:
            with temporary_pypackage("a/b/c/d", ["mod3.py"], init=False) as tmp_ns3:
                tmp_namespace_pkgs = [tmp_ns.tmpdir for tmp_ns in (tmp_ns1, tmp_ns2, tmp_ns3)]
                loader = GriffeLoader(search_paths=tmp_namespace_pkgs)

                a_package = loader.load("a")
                for tmp_ns in tmp_namespace_pkgs:
                    assert tmp_ns.joinpath("a") in a_package.filepath  # ty:ignore[unsupported-operator]
                assert "b" in a_package.members

                b_package = a_package.members["b"]
                for tmp_ns in tmp_namespace_pkgs:
                    assert tmp_ns.joinpath("a/b") in b_package.filepath  # ty:ignore[unsupported-operator]
                assert "c" in b_package.members

                c_package = b_package.members["c"]
                for tmp_ns in tmp_namespace_pkgs:
                    assert tmp_ns.joinpath("a/b/c") in c_package.filepath  # ty:ignore[unsupported-operator]
                assert "d" in c_package.members

                d_package = c_package.members["d"]
                for tmp_ns in tmp_namespace_pkgs:
                    assert tmp_ns.joinpath("a/b/c/d") in d_package.filepath  # ty:ignore[unsupported-operator]
                assert "mod1" in d_package.members
                assert "mod2" in d_package.members
                assert "mod3" in d_package.members


def test_stop_at_first_package_inside_namespace_package() -> None:
    """Stop loading similar paths once we found a non-namespace package."""
    with temporary_pypackage("a/b/c/d", ["mod1.py"], init=True) as tmp_ns1:  # noqa: SIM117
        with temporary_pypackage("a/b/c/d", ["mod2.py"], init=True) as tmp_ns2:
            tmp_namespace_pkgs = [tmp_ns.tmpdir for tmp_ns in (tmp_ns1, tmp_ns2)]
            loader = GriffeLoader(search_paths=tmp_namespace_pkgs)

            a_package = loader.load("a")
            assert "b" in a_package.members

            b_package = a_package.members["b"]
            assert "c" in b_package.members

            c_package = b_package.members["c"]
            assert "d" in c_package.members

            d_package = c_package.members["d"]
            assert d_package.is_subpackage
            assert d_package.filepath == tmp_ns1.tmpdir.joinpath("a/b/c/d/__init__.py")
            assert "mod1" in d_package.members
            assert "mod2" not in d_package.members


def test_load_builtin_modules() -> None:
    """Assert builtin/compiled modules can be loaded."""
    loader = GriffeLoader()
    loader.load("_ast")
    loader.load("_collections")
    loader.load("_operator")
    assert "_ast" in loader.modules_collection
    assert "_collections" in loader.modules_collection
    assert "_operator" in loader.modules_collection


def test_resolve_aliases_of_builtin_modules() -> None:
    """Assert builtin/compiled modules can be loaded."""
    loader = GriffeLoader()
    loader.load("io")
    loader.load("_io")
    unresolved, _ = loader.resolve_aliases(external=True, implicit=True, max_iterations=1)
    io_unresolved = {un for un in unresolved if un.startswith(("io", "_io"))}
    assert len(io_unresolved) < 5


@pytest.mark.parametrize("namespace", [False, True])
def test_loading_stubs_only_packages(tmp_path: Path, namespace: bool) -> None:
    """Test loading and merging of stubs-only packages.

    Parameters:
        tmp_path: Pytest fixture.
        namespace: Whether the package and stubs are namespace packages.
    """
    # Create package.
    package_parent = tmp_path / "pkg_parent"
    package_parent.mkdir()
    package = package_parent / "package"
    package.mkdir()
    if not namespace:
        package.joinpath("__init__.py").write_text("a: int = 0", encoding="utf8")
    package.joinpath("module.py").write_text("a: int = 0", encoding="utf8")

    # Create stubs.
    stubs_parent = tmp_path / "stubs_parent"
    stubs_parent.mkdir()
    stubs = stubs_parent / "package-stubs"
    stubs.mkdir()
    if not namespace:
        stubs.joinpath("__init__.pyi").write_text("b: int", encoding="utf8")
    stubs.joinpath("module.pyi").write_text("b: int", encoding="utf8")

    # Exposing stubs first, to make sure order doesn't matter.
    loader = GriffeLoader(search_paths=[stubs_parent, package_parent])

    # Loading package and stubs, checking their contents.
    top_module = loader.load("package", try_relative_path=False, find_stubs_package=True)
    if not namespace:
        assert "a" in top_module.members
        assert "b" in top_module.members
    assert "a" in top_module["module"].members
    assert "b" in top_module["module"].members


@pytest.mark.parametrize(
    "init",
    [
        "from package.thing import thing",
        "thing = False",
    ],
)
def test_submodule_shadowing_member(init: str, caplog: pytest.LogCaptureFixture) -> None:
    """Warn when a submodule shadows a member of the same name.

    Parameters:
        init: Contents of the top-level init module.
    """
    caplog.set_level(logging.DEBUG)
    with temporary_visited_package(
        "package",
        {"__init__.py": init, "thing.py": "thing = True"},
        init=True,
    ):
        assert "shadowing" in caplog.text


@pytest.mark.parametrize("wildcard", [True, False])
@pytest.mark.parametrize(("external", "foo_is_resolved"), [(None, True), (True, True), (False, False)])
def test_side_loading_sibling_private_module(wildcard: bool, external: bool | None, foo_is_resolved: bool) -> None:
    """Automatically load `_a` when `a` (wildcard) imports from it.

    Parameters:
        wildcard: Whether the import is a wildcard import.
        external: Value for the `external` parameter when resolving aliases.
        foo_is_resolved: Whether the `foo` alias should be resolved.
    """
    with temporary_pypackage("_a", {"__init__.py": "def foo():\n    '''Docstring.'''"}) as pkg_a:  # noqa: SIM117
        with temporary_pypackage("a", {"__init__.py": f"from _a import {'*' if wildcard else 'foo'}"}) as pkg_a_private:
            loader = GriffeLoader(search_paths=[pkg_a.tmpdir, pkg_a_private.tmpdir])
            package = loader.load("a")
            loader.resolve_aliases(external=external, implicit=True)
            if foo_is_resolved:
                assert "foo" in package.members
                assert package["foo"].is_alias
                assert package["foo"].resolved
                assert package["foo"].docstring.value == "Docstring."
            elif wildcard:
                assert "foo" not in package.members
            else:
                assert "foo" in package.members
                assert package["foo"].is_alias
                assert not package["foo"].resolved


def test_forcing_inspection() -> None:
    """Load a package with forced dynamic analysis."""
    modules = {"__init__.py": "a = 0", "mod.py": "b = 1"}
    with (
        temporary_visited_package("static_pkg", modules) as static_package,
        temporary_inspected_package("dynamic_pkg", modules) as dynamic_package,
    ):
        for name in static_package.members:
            assert name in dynamic_package.members
        for name in static_package["mod"].members:
            assert name in dynamic_package["mod"].members


def test_relying_on_modules_path_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load a package that relies on the `__path__` attribute of a module."""

    def raise_module_not_found_error(*args, **kwargs) -> None:  # noqa: ARG001,ANN002,ANN003
        raise ModuleNotFoundError

    loader = GriffeLoader()
    monkeypatch.setattr(loader.finder, "find_spec", raise_module_not_found_error)
    assert loader.load("griffe")


def test_not_calling_package_hook_on_something_else_than_package() -> None:
    """Always call the `on_package` hook on a package, not any other object."""
    with temporary_pypackage("pkg", {"__init__.py": "from typing import List as L"}) as pkg:
        loader = GriffeLoader(search_paths=[pkg.tmpdir])
        alias: Alias = loader.load("pkg.L")  # ty:ignore[invalid-assignment]
        assert alias.is_alias
        assert not alias.resolved


def test_not_overriding_module_with_alias_from_wildcard_import() -> None:
    """Do not override a submodule with an imported object with the same name."""
    with temporary_visited_package(
        "pkg",
        {
            "__init__.py": "",
            "a/__init__.py": "from .m import *",
            "a/m.py": "def m(): pass",
            "b/__init__.py": "from .m import *",
            "b/m.py": "from pkg.a.m import m",
        },
        resolve_aliases=True,
    ) as pkg:
        assert pkg["a.m"].is_module
        assert pkg["a.m.m"].is_function
        assert pkg["b.m"].is_module
        assert pkg["b.m.m"].is_alias


def test_loading_utf8_with_bom_files(tmp_path: Path) -> None:
    """Check that the loader can handle UTF-8 files with BOM."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    init_file = pkg / "__init__.py"
    init_file.write_text("\ufeff# This is a UTF-8 file with BOM\n\ndef func() -> int: ...", encoding="utf-8")
    loader = GriffeLoader(search_paths=[tmp_path])
    package = loader.load("pkg")
    assert "func" in package.members  # Just checking all went well, no SyntaxError exceptions raised.


def test_deferred_finder(tmp_path: Path) -> None:
    """Check that the deferred finder works as expected."""
    ns = tmp_path / "ns"
    l1 = GriffeLoader(search_paths=[tmp_path])
    ns.mkdir(exist_ok=False)
    l2 = GriffeLoader(search_paths=[tmp_path])
    l1_result = l1.load("ns")
    l2_result = l2.load("ns")
    assert l1_result.as_dict() == l2_result.as_dict()


def test_loader_and_load_pypi_edge_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test `GriffeLoader`, `load`, `load_git`, and `load_pypi` edge cases."""
    from pathlib import Path  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    from griffe._internal import loader as loader_mod  # noqa: PLC0415
    from griffe._internal.exceptions import (  # noqa: PLC0415
        LoadingError,
    )
    from griffe._internal.expressions import ExprName  # noqa: PLC0415
    from griffe._internal.models import Alias, Attribute, Class, Module  # noqa: PLC0415

    # 1. ModuleNotFoundError when allow_inspection=False and force_inspection=False
    loader_no_insp = GriffeLoader(search_paths=[tmp_path], allow_inspection=False, force_inspection=False)
    with pytest.raises(ModuleNotFoundError):
        loader_no_insp.load("nonexistent_pkg_xyz_999")

    # 2. Dynamic import fallback with empty __path__ (builtin/compiled style) and >1 __path__ (namespace)
    monkeypatch.setattr(
        loader_mod,
        "dynamic_import",
        lambda *_a, **_kw: SimpleNamespace(__path__=[]),
    )
    monkeypatch.setattr(
        GriffeLoader,
        "_inspect_module",
        lambda self, name, *_a, **_kw: Module(name, modules_collection=self.modules_collection),
    )
    loader_dyn = GriffeLoader(search_paths=[tmp_path])
    assert loader_dyn.load("empty_path_mod").name == "empty_path_mod"

    ns_p1 = tmp_path / "nsp1"
    ns_p2 = tmp_path / "nsp2"
    ns_p1.mkdir()
    ns_p2.mkdir()
    monkeypatch.setattr(
        loader_mod,
        "dynamic_import",
        lambda *_a, **_kw: SimpleNamespace(__path__=[str(ns_p1), str(ns_p2)]),
    )
    assert loader_dyn.load("multi_path_mod").name == "multi_path_mod"
    monkeypatch.undo()

    # 3. LoadingError in load() re-raised with logger.exception
    bad_syntax_pkg = tmp_path / "bad_syntax_pkg"
    bad_syntax_pkg.mkdir()
    (bad_syntax_pkg / "__init__.py").write_text("def broken(:\n", encoding="utf8")
    loader_err = GriffeLoader(search_paths=[tmp_path])
    with pytest.raises(LoadingError, match="Syntax error"):
        loader_err.load("bad_syntax_pkg")

    # 4. _load_module exceptions: ImportError, UnicodeDecodeError, OSError, and compiled module without inspection
    bad_utf8_file = tmp_path / "bad_utf8.py"
    bad_utf8_file.write_bytes(b"\xff\xfe")
    with pytest.raises(LoadingError, match="UnicodeDecodeError"):
        loader_err._load_module("bad_utf8", bad_utf8_file)

    with pytest.raises(LoadingError, match="OSError"):
        loader_err._load_module("missing_file", tmp_path / "missing_file.py")

    so_file = tmp_path / "compiled.so"
    so_file.write_bytes(b"")
    with pytest.raises(LoadingError, match="Cannot load compiled module"):
        loader_no_insp._load_module("compiled", so_file)

    # _load_module_path with allow_inspection=True on .so file, and _inspect_module errors
    loader_err.ignored_modules.add("ignored_mod")
    with pytest.raises(LoadingError, match="Import error"):
        loader_err._load_module("ignored_mod", so_file)
    with pytest.raises(LoadingError, match="Import error"):
        loader_err._load_module("compiled_nonexistent_so", so_file)

    monkeypatch.setattr(loader_mod, "inspect", lambda *_a, **_kw: (_ for _ in ()).throw(SystemExit(1)))
    with pytest.raises(ImportError, match="raised a system exit"):
        loader_err._inspect_module("sys_exit_mod", filepath=bad_syntax_pkg / "__init__.py")
    monkeypatch.undo()

    # _fire_load_events with nested submodule and all member kinds via load()
    from griffe._internal.extensions.base import Extension, Extensions  # noqa: PLC0415
    from griffe._internal.models import Function, TypeAlias  # noqa: PLC0415

    class SubmodHookExt(Extension):
        def on_module(self, **_kw: object) -> None:
            pass

    loader_hook = GriffeLoader(search_paths=[tmp_path], extensions=Extensions(SubmodHookExt()))
    top_m = Module("top_m")
    top_m["child_m"] = Module("child_m", parent=top_m)
    top_m["child_c"] = Class("child_c", parent=top_m)
    top_m["child_f"] = Function("child_f", parent=top_m)
    top_m["child_a"] = Attribute("child_a", parent=top_m)
    top_m["child_ta"] = TypeAlias("child_ta", parent=top_m)
    top_m["child_al"] = Alias("child_al", "top_m.child_a", parent=top_m)
    loader_hook.modules_collection["top_m"] = top_m
    loader_hook._post_load(top_m, "top_m")

    # 5. _load_submodule with dot in subpart, Missing __init__ module, LoadingError in submodule, and non-shadowing module
    parent_mod = Module(
        "parent_mod", filepath=bad_syntax_pkg / "__init__.py", modules_collection=loader_err.modules_collection
    )
    loader_err._load_submodule(parent_mod, ("a.b",), bad_syntax_pkg / "a.b.py")
    loader_err._load_submodule(parent_mod, ("unimportable_dir", "mod"), bad_syntax_pkg / "unimportable_dir" / "mod.py")
    loader_err._load_submodule(parent_mod, ("broken",), bad_syntax_pkg / "__init__.py")

    valid_sub = tmp_path / "valid_sub.py"
    valid_sub.write_text("x = 1\n", encoding="utf8")
    parent_mod["valid_sub"] = Module("valid_sub", filepath=valid_sub)
    loader_err._load_submodule(parent_mod, ("valid_sub",), valid_sub)

    # _get_or_create_parent_module with existing parent_module that is not a namespace package
    parent_mod["subpkg"] = Module("subpkg", filepath=bad_syntax_pkg / "__init__.py")
    res_parent = loader_err._get_or_create_parent_module(
        parent_mod,
        ("subpkg", "leaf"),
        bad_syntax_pkg / "subpkg" / "__init__.py",
    )
    assert res_parent is parent_mod["subpkg"]

    # 6. expand_exports edge cases: already seen, ExprName missing, ExprName already seen, TypeError on None exports, alias submodule
    m_exp = Module("m_exp", modules_collection=loader_err.modules_collection)
    loader_err.modules_collection["m_exp"] = m_exp
    m_other = Module("m_other", modules_collection=loader_err.modules_collection)
    m_other.exports = None
    loader_err.modules_collection["m_other"] = m_other
    m_seen = Module("m_seen", modules_collection=loader_err.modules_collection)
    m_seen.exports = ["s1"]
    loader_err.modules_collection["m_seen"] = m_seen

    m_exp.exports = [
        ExprName("__all__", parent=Module("missing_exp_mod")),
        ExprName("m_other.__all__"),
        ExprName("m_seen.__all__"),
        ExprName("m_seen.__all__"),
        "own",
    ]
    m_exp["sub_seen"] = m_seen
    m_unseen_sub = Module("m_unseen_sub", parent=m_exp)
    m_exp["m_unseen_sub"] = m_unseen_sub
    m_exp["sub_alias"] = Alias("sub_alias", "m_seen", parent=m_exp)
    loader_err.expand_exports(m_exp, seen={"m_seen", "m_exp.m_seen"})

    # 7. expand_wildcards edge cases
    m_wc = Module("m_wc", filepath=valid_sub, modules_collection=loader_err.modules_collection)
    loader_err.modules_collection["m_wc"] = m_wc
    # Wildcard to external package that fails to load
    m_wc.set_member("/*", Alias("/*", "nonexistent_wc_pkg_xyz/*", parent=m_wc))
    m_wc["sub_seen"] = m_seen
    loader_err.expand_wildcards(m_wc, external=True, seen={"m_seen"})

    # Wildcard to loaded package whose submodule is missing in modules_collection
    m_wc2 = Module("m_wc", filepath=valid_sub, modules_collection=loader_err.modules_collection)
    loader_err.modules_collection["m_wc"] = m_wc2
    m_wc2.set_member("/*", Alias("/*", "m_wc.missing_sub/*", parent=m_wc2))
    loader_err.expand_wildcards(m_wc2, external=True)

    # Wildcard to target alias that is unresolved or cyclic (raises AliasResolutionError/CyclicAliasError)
    m_wc3 = Module("m_wc3", filepath=valid_sub, modules_collection=loader_err.modules_collection)
    loader_err.modules_collection["m_wc3"] = m_wc3
    m_wc3["target_al"] = Alias("target_al", "m_wc3.target_al", parent=m_wc3)
    m_wc3.set_member("/*", Alias("/*", "m_wc3.target_al.sub/*", parent=m_wc3))
    loader_err.expand_wildcards(m_wc3, external=False)

    # Self-alias and lower-lineno non-overwrite and broken alias prev_member in expand_wildcards
    m_src = Module("m_src", filepath=valid_sub, modules_collection=loader_err.modules_collection)
    m_src["self_al"] = Alias("self_al", "m_dst.self_al", parent=m_src)
    m_src["existing"] = Attribute("existing", value="1", lineno=100, parent=m_src)
    m_src["broken_prev"] = Attribute("broken_prev", value="2", lineno=1, parent=m_src)
    loader_err.modules_collection["m_src"] = m_src

    m_dst = Module("m_dst", filepath=valid_sub, modules_collection=loader_err.modules_collection)
    m_dst["existing"] = Alias("existing", "other.x", lineno=50, parent=m_dst)
    m_dst["broken_prev"] = Alias("broken_prev", "missing.broken", lineno=1, parent=m_dst)
    m_dst["/*src"] = Alias("/*", "m_src/*", lineno=10, parent=m_dst)
    loader_err.modules_collection["m_dst"] = m_dst
    loader_err.expand_wildcards(m_dst, external=False)

    # 8. resolve_module_aliases edge cases (CyclicAliasError, external load failure, already seen class)
    m_res = Module("m_res", filepath=valid_sub, modules_collection=loader_err.modules_collection)
    loader_err.modules_collection["m_res"] = m_res
    c_a = Alias("c_a", "m_res.c_b", parent=m_res)
    c_b = Alias("c_b", "m_res.c_a", parent=m_res)
    m_res["c_a"] = c_a
    m_res["c_b"] = c_b
    m_res["ext_fail"] = Alias("ext_fail", "nonexistent_ext_pkg_xyz.item", parent=m_res)
    cls_seen = Class("ClsSeen", parent=m_res)
    m_res["ClsSeen"] = cls_seen
    loader_err.resolve_module_aliases(m_res, implicit=True, external=True, seen={"m_res.ClsSeen"})

    # 9. stats() method and load() with store_source=False and resolve_aliases=True
    assert loader_err.stats() is not None
    loader_no_src = GriffeLoader(search_paths=[tmp_path], store_source=False)
    loader_no_src._visit_module("valid_sub", valid_sub)
    loader_no_src_insp = GriffeLoader(search_paths=[tmp_path], store_source=False, force_inspection=True)
    loader_no_src_insp._inspect_module("valid_sub", valid_sub)

    loaded_res = loader_mod.load("valid_sub", search_paths=[tmp_path], resolve_aliases=True)
    assert loaded_res.name == "valid_sub"

    # 10. load_git with Path and str objspec
    monkeypatch.setattr(loader_mod, "_tmp_worktree", lambda *_a, **_kw: __import__("contextlib").nullcontext(tmp_path))
    monkeypatch.setattr(loader_mod, "load", lambda spec, **_kw: Module(str(spec)))
    assert str(tmp_path / "valid_sub.py") in loader_mod.load_git(Path("valid_sub.py")).name
    assert loader_mod.load_git("valid_sub").name == "valid_sub"
    monkeypatch.undo()

    # 11. load_pypi edge cases
    monkeypatch.setattr(loader_mod, "find_spec", lambda _pkg: None)
    with pytest.raises(RuntimeError, match="Please install Griffe with the 'pypi' extra"):
        loader_mod.load_pypi("pkg", "pkg", "==1.0")
    monkeypatch.setattr(loader_mod, "find_spec", lambda _pkg: True)

    import platformdirs  # noqa: PLC0415

    cache_root = tmp_path / "pypi_cache"
    cache_root.mkdir()
    monkeypatch.setattr(platformdirs, "user_cache_dir", lambda _name: str(cache_root))
    monkeypatch.setattr(loader_mod, "load", lambda pkg, **_kw: Module(pkg))

    # Pre-existing cached install_dir with matching package name
    cached_dir = cache_root / "my-dist==1.0"
    cached_dir.mkdir()
    (cached_dir / "my_dist.py").write_text("x = 1\n", encoding="utf8")
    (cached_dir / "my_dist-1.0.dist-info").mkdir()
    assert loader_mod.load_pypi("", "my-dist", "==1.0").name == "my_dist"
    assert loader_mod.load_pypi("my_dist", "my-dist", "==1.0").name == "my_dist"

    # Download via subprocess: failure and success (with existing dest_dir vs new dest_dir)
    monkeypatch.setattr(
        loader_mod.subprocess,
        "run",
        lambda *_a, **_kw: SimpleNamespace(returncode=1, stdout="pip error"),
    )
    with pytest.raises(RuntimeError, match="Could not pip install"):
        loader_mod.load_pypi("pkg", "fail-dist", ">=1.0")

    def fake_pip_run(cmd: list[str], **_kw: object) -> SimpleNamespace:
        target = Path(cmd[cmd.index("-t") + 1])
        target.mkdir(parents=True, exist_ok=True)
        dist_spec = cmd[-1]
        if "only-dist-info" in dist_spec:
            (target / "only_dist_info-1.0.dist-info").mkdir()
        elif "two-dist-info" in dist_spec:
            (target / "two_dist_info-1.0.dist-info").mkdir()
            (target / "extra.dist-info").mkdir()
        elif "custom-mod" in dist_spec:
            (target / "custom_mod-1.0.dist-info").mkdir()
            (target / "actual_pkg_name.py").write_text("x = 1\n", encoding="utf8")
        else:
            (target / "my_dist-1.0.dist-info").mkdir()
            (target / "my_dist.py").write_text("x = 1\n", encoding="utf8")
        return SimpleNamespace(returncode=0, stdout="ok")

    monkeypatch.setattr(loader_mod.subprocess, "run", fake_pip_run)
    # Destination `my-dist==1.0` already exists
    assert loader_mod.load_pypi("my_dist", "my-dist", ">=1.0").name == "my_dist"
    # Destination does not exist yet + guess package name from files
    assert loader_mod.load_pypi("", "custom-mod", ">=1.0").name == "actual_pkg_name"
    # Only 1 file (.dist-info) -> RuntimeError("No package found")
    with pytest.raises(RuntimeError, match="No package found"):
        loader_mod.load_pypi("", "only-dist-info", ">=1.0")
    # Multiple .dist-info files -> StopIteration -> RuntimeError("Could not guess package name")
    with pytest.raises(RuntimeError, match="Could not guess package name"):
        loader_mod.load_pypi("", "two-dist-info", ">=1.0")
