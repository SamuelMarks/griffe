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

# Test nodes utilities.

from __future__ import annotations

import logging
import sys
import weakref
from ast import AST, Add, Name, PyCF_ONLY_AST

import pytest

from griffe import (
    Expr,
    ExprName,
    ast_children,
    module_vtree,
    relative_to_absolute,
    temporary_visited_module,
)
from griffe._internal.agents import visitor as visitor_module

syntax_examples = [
    # Operations.
    "b + c",
    "b - c",
    "b * c",
    "b / c",
    "b // c",
    "b ** c",
    "b ^ c",
    "b & c",
    "b | c",
    "b @ c",
    "b % c",
    "b >> c",
    "b << c",
    # Unary operations.
    "+b",
    "-b",
    "~b",
    # Comparisons.
    "b == c",
    "b >= c",
    "b > c",
    "b <= c",
    "b < c",
    "b != c",
    # Boolean logic.
    "b and c",
    "b or c",
    "not b",
    # Identify.
    "b is c",
    "b is not c",
    # Membership.
    "b in c",
    "b not in c",
    # Calls.
    "call()",
    "call(something)",
    "call(something=something)",
    # Strings.
    "f'a {round(key, 2)} {z}'",
    'f"it\'s {x}"',  # ' only -> " delimiter
    "f\"don't {x} won't {y}\"",  # multiple ' -> " delimiter
    "f'say \"hello\" to {x}'",  # " only -> ' delimiter
    'f\'"quoted" and "re-quoted" {x}\'',  # multiple " -> ' delimiter
    "f'''it's \"complicated\" {x}'''",  # both -> triple-' delimiter
    "f'''she said \"it's fine\" to {x}'''",  # both, different parts -> triple-'
    # YORE: EOL 3.13: Regex-replace `\*\(\[(.+)\].+\),` with `\1,` within line.
    *(["t'a {round(key, 2)} {z}'"] if sys.version_info >= (3, 14) else []),
    # YORE: EOL 3.13: Regex-replace `\*\(\[(.+)\].+\),` with `\1,` within line.
    *(['t"it\'s {x}"'] if sys.version_info >= (3, 14) else []),
    # YORE: EOL 3.13: Regex-replace `\*\(\[(.+)\].+\),` with `\1,` within line.
    *(["t'say \"hello\" to {x}'"] if sys.version_info >= (3, 14) else []),
    # YORE: EOL 3.13: Regex-replace `\*\(\[(.+)\].+\),` with `\1,` within line.
    *(["t'''it's \"complicated\" {x}'''"] if sys.version_info >= (3, 14) else []),
    # Formatted values: conversions and format specifiers.
    "f'{x!r}'",
    "f'{x!s}'",
    "f'{x!a}'",
    "f'{x:>10}'",
    "f'{x:{width}}'",
    "f'{x!r:>{width}}'",
    "f'a {x:%Y-%m-%d} b'",
    "f'{(x := 1)}'",
    "f'{ {1: 2}}'",
    # YORE: EOL 3.13: Regex-replace `\*\(\[(.+)\].+\),` with `\1,` within line.
    *(["t'{x!r}'"] if sys.version_info >= (3, 14) else []),
    # YORE: EOL 3.13: Regex-replace `\*\(\[(.+)\].+\),` with `\1,` within line.
    *(["t'{x!s:>{width}}'"] if sys.version_info >= (3, 14) else []),
    # Slices.
    "o[x]",
    "o[x, y]",
    "o[x:y]",
    "o[x:y, z]",
    "o[x, y(z)]",
    "o[(a, b):y]",
    "o[a + b:]",
    # Walrus operator.
    "a if (a := b) else c",
    "{(a := 1): 2}",
    "{1: (a := 2)}",
    "[a for a in b if (c := a)]",
    # Starred.
    "a(*b, **c)",
    "a(*b | c)",
    # Structs.
    "(a, b, c)",
    "{a, b, c}",
    "{a: b, c: d}",
    "{a + b: c + d for a, b in e}",
    "[a, b, c]",
    "[a + b for a in c]",
    # Generator expressions.
    "(a + b for a in c)",
    "a(b for b in c)",
    "sum((a for a in b), c)",
    "[(a for a in b), c]",
    "{1: (a for a in b)}",
    "(a for a in b if (c := a))",
    # Yields.
    "yield",
    "yield a",
    "yield a + b",
    "yield from a",
    # Lambdas.
    "lambda a: a",
    "lambda a, b: a",
    "lambda *a, **b: a",
    "lambda a, b=0: a",
    "lambda a=b + c: a",
    "lambda a, /, b, c: a",
    "lambda a, *, b, c: a",
    "lambda a, /, b, *, c: a",
    "lambda a, /: a",
    "lambda a, b, /: a",
    "lambda a, /, *args: args",
    "lambda a, /, **kwargs: kwargs",
    "lambda a, /, *, b: b",
    "lambda a, /, b=0, *args, c=1, **kwargs: a",
    "lambda *args, b: b",
    "lambda *args, b=0: b",
    # Calls with expression-level arguments.
    "call(a=b + c)",
    # Attribute access on integer literals.
    "(1).bit_length()",
]


def test_shared_ast_nodes_do_not_retain_parent_trees() -> None:
    """Shared AST operator/context instances must not keep parsed trees alive."""
    expression = compile("left + right", filename="<test>", mode="eval", flags=PyCF_ONLY_AST).body  # ty:ignore[unresolved-attribute]
    children = list(ast_children(expression))

    assert any(isinstance(child, Name) and child.parent is expression for child in children)  # ty:ignore[unresolved-attribute]
    assert any(isinstance(child, Add) and not hasattr(child, "parent") for child in children)
    assert all(isinstance(child, AST) for child in children)


def test_visitor_releases_ast_without_cyclic_gc(monkeypatch: pytest.MonkeyPatch) -> None:
    """A completed static analysis must not leave parent cycles behind."""
    references: list[weakref.ReferenceType[AST]] = []
    builtin_compile = compile

    def capture_ast(*args: object, **kwargs: object) -> AST:
        node = builtin_compile(*args, **kwargs)  # ty:ignore[no-matching-overload]
        references.append(weakref.ref(node))
        return node

    monkeypatch.setattr(visitor_module, "compile", capture_ast, raising=False)
    with temporary_visited_module("value = left + right"):
        pass

    assert references
    assert all(reference() is None for reference in references)


@pytest.mark.parametrize(
    ("code", "path", "is_package", "expected"),
    [
        ("from . import b", "a", False, "a.b"),
        ("from . import b", "a", True, "a.b"),
        ("from . import c", "a.b", False, "a.c"),
        ("from . import c", "a.b", True, "a.b.c"),
        ("from . import d", "a.b.c", False, "a.b.d"),
        ("from .c import d", "a", False, "a.c.d"),
        ("from .c import d", "a.b", False, "a.c.d"),
        ("from .b import c", "a.b", True, "a.b.b.c"),
        ("from .. import e", "a.c.d.i", False, "a.c.e"),
        ("from ..d import e", "a.c.d.i", False, "a.c.d.e"),
        ("from ... import f", "a.c.d.i", False, "a.f"),
        ("from ...b import f", "a.c.d.i", False, "a.b.f"),
        ("from ...c.d import e", "a.c.d.i", False, "a.c.d.e"),
        ("from .c import *", "a", False, "a.c.*"),
        ("from .c import *", "a.b", False, "a.c.*"),
        ("from .b import *", "a.b", True, "a.b.b.*"),
        ("from .. import *", "a.c.d.i", False, "a.c.*"),
        ("from ..d import *", "a.c.d.i", False, "a.c.d.*"),
        ("from ... import *", "a.c.d.i", False, "a.*"),
        ("from ...b import *", "a.c.d.i", False, "a.b.*"),
        ("from ...c.d import *", "a.c.d.i", False, "a.c.d.*"),
    ],
)
def test_relative_to_absolute_imports(code: str, path: str, is_package: bool, expected: str) -> None:
    """Check if relative imports are correctly converted to absolute ones.

    Parameters:
        code: The parametrized module code.
        path: The parametrized module path.
        is_package: Whether the module is a package (or subpackage) (parametrized).
        expected: The parametrized expected absolute path.
    """
    node = compile(code, mode="exec", filename="<>", flags=PyCF_ONLY_AST).body[0]  # ty:ignore[unresolved-attribute]
    module = module_vtree(path, leaf_package=is_package, return_leaf=True)
    for name in node.names:
        assert relative_to_absolute(node, name, module) == expected


def test_multipart_imports() -> None:
    """Assert that a multipart path like `a.b.c` imported as `x` points to the right target."""
    with temporary_visited_module(
        """
        import pkg.b.c
        import pkg.b.c as alias
        """,
    ) as module:
        pkg = module["pkg"]
        alias = module["alias"]
    assert pkg.target_path == "pkg"
    assert alias.target_path == "pkg.b.c"


@pytest.mark.parametrize(
    "expression",
    [
        "A",
        "A.B",
        "A[B]",
        "A.B[C.D]",
        "~A",
        "A | B",
        "A[[B, C], D]",
        "A(b=c, d=1)",
        "A[-1, +2.3]",
        "A[B, C.D(e='syntax error')]",
    ],
)
def test_building_annotations_from_nodes(expression: str) -> None:
    """Test building annotations from AST nodes.

    Parameters:
        expression: An expression (parametrized).
    """
    class_defs = "\n\n".join(f"class {letter}: ..." for letter in "ABCD")
    with temporary_visited_module(f"{class_defs}\n\nx: {expression}\ny: {expression} = 0") as module:
        assert "x" in module.members
        assert "y" in module.members
        assert str(module["x"].annotation) == expression
        assert str(module["y"].annotation) == expression


@pytest.mark.parametrize("code", syntax_examples)
def test_building_expressions_from_nodes(code: str) -> None:
    """Test building annotations from AST nodes.

    Parameters:
        code: An expression (parametrized).
    """
    with temporary_visited_module(f"__z__ = {code}") as module:
        assert "__z__" in module.members

        # Make space after comma non-significant.
        value = str(module["__z__"].value).replace(", ", ",")
        assert value == code.replace(", ", ",")


@pytest.mark.parametrize(
    ("code", "has_name"),
    [
        ("import typing\nclass A: ...\na: typing.Literal['A']", False),
        ("from typing import Literal\nclass A: ...\na: Literal['A']", False),
        ("import typing_extensions\nclass A: ...\na: typing.Literal['A']", False),
        ("from typing_extensions import Literal\nclass A: ...\na: Literal['A']", False),
        ("from mod import A\na: 'A'", True),
        ("from mod import A\na: list['A']", True),
    ],
)
def test_forward_references(code: str, has_name: bool) -> None:
    """Check that we support forward references (type names as strings).

    Parameters:
        code: Parametrized code.
        has_name: Whether the annotation should contain a Name rather than a string.
    """
    with temporary_visited_module(code) as module:
        annotation = list(module["a"].annotation.iterate(flat=True))
        if has_name:
            assert any(isinstance(item, ExprName) and item.name == "A" for item in annotation)
            assert all(not (isinstance(item, str) and item == "A") for item in annotation)
        else:
            assert "'A'" in annotation
            assert all(not (isinstance(item, ExprName) and item.name == "A") for item in annotation)


@pytest.mark.parametrize(
    "default",
    [
        "1",
        "'test_string'",
        "dict(key=1)",
        "{'key': 1}",
        "DEFAULT_VALUE",
        "None",
    ],
)
def test_default_value_from_nodes(default: str) -> None:
    """Test getting default value from AST nodes.

    Parameters:
        default: A default value (parametrized).
    """
    module_defs = f"def f(x={default}):\n    return x"
    with temporary_visited_module(module_defs) as module:
        assert "f" in module.members
        params = module.members["f"].parameters  # ty:ignore[unresolved-attribute]
        assert len(params) == 1
        assert str(params[0].default) == default


# https://github.com/mkdocstrings/griffe/issues/159
def test_parsing_complex_string_annotations() -> None:
    """Test parsing of complex, stringified annotations."""
    with temporary_visited_module(
        """
        class ArgsKwargs:
            def __init__(self, args: 'tuple[Any, ...]', kwargs: 'dict[str, Any] | None' = None) -> None:
                ...

            @property
            def args(self) -> 'tuple[Any, ...]':
                ...

            @property
            def kwargs(self) -> 'dict[str, Any] | None':
                ...
        """,
    ) as module:
        init_args_annotation = module["ArgsKwargs.__init__"].parameters["args"].annotation
        assert isinstance(init_args_annotation, Expr)
        assert init_args_annotation.is_tuple
        kwargs_return_annotation = module["ArgsKwargs.kwargs"].annotation
        assert isinstance(kwargs_return_annotation, Expr)


def test_parsing_dynamic_base_classes(caplog: pytest.LogCaptureFixture) -> None:
    """Assert parsing dynamic base classes does not trigger errors.

    Parameters:
        caplog: Pytest fixture to capture logs.
    """
    with (
        caplog.at_level(logging.ERROR),
        temporary_visited_module(
            """
            from collections import namedtuple
            class Thing(namedtuple('Thing', 'attr1 attr2')):
                ...
            """,
        ),
    ):
        pass
    assert not caplog.records


def test_ast_node_helpers_and_utilities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test AST navigation helpers, values, exports, parser fallback, and small internal modules."""
    import ast  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from griffe._internal import c3linear, collections, debug, exceptions, importer, logger, stats  # noqa: PLC0415
    from griffe._internal.agents import parser as parser_mod  # noqa: PLC0415
    from griffe._internal.agents.nodes import ast as ast_mod  # noqa: PLC0415
    from griffe._internal.agents.nodes import exports as exports_mod  # noqa: PLC0415
    from griffe._internal.agents.nodes import values as values_mod  # noqa: PLC0415
    from griffe._internal.enumerations import LogLevel  # noqa: PLC0415
    from griffe._internal.extensions.base import Extensions  # noqa: PLC0415
    from griffe._internal.models import Alias, Module  # noqa: PLC0415

    # AST navigation helpers
    tree = compile("x = 1\ny = 2\nz = 3", filename="<>", mode="exec", flags=PyCF_ONLY_AST)
    assert ast_mod.ast_kind(tree) == "module"
    children = list(ast_mod.ast_children(tree))
    assert len(children) == 3
    assert ast_mod.ast_first_child(tree) is children[0]
    assert ast_mod.ast_last_child(tree) is children[2]
    assert ast_mod.ast_next(children[0]) is children[1]
    assert ast_mod.ast_previous(children[1]) is children[0]
    assert list(ast_mod.ast_next_siblings(children[0])) == [children[1], children[2]]
    assert list(ast_mod.ast_previous_siblings(children[2])) == [children[0], children[1]]
    assert list(ast_mod.ast_siblings(children[1])) == [children[0], children[2]]

    # Custom AST node with missing field, non-AST field, and non-AST element in list field
    class CustomNode(ast.AST):
        _fields = ("missing_field", "non_ast", "mixed_list")

    cn = CustomNode()
    cn.non_ast = 123  # ty:ignore[unresolved-attribute]
    cn.mixed_list = [123, ast.Load()]  # ty:ignore[unresolved-attribute]
    assert len(list(ast_mod.ast_children(cn))) == 1

    # Orphan node not in its parent's children
    orphan = ast.Pass()
    orphan.parent = tree  # ty:ignore[unresolved-attribute]
    assert list(ast_mod.ast_previous_siblings(orphan)) == children
    assert list(ast_mod.ast_next_siblings(orphan)) == []
    assert list(ast_mod.ast_siblings(orphan)) == children

    with pytest.raises(exceptions.LastNodeError):
        ast_mod.ast_next(children[2])
    with pytest.raises(exceptions.LastNodeError):
        ast_mod.ast_previous(children[0])

    empty_tree = compile("", filename="<>", mode="exec", flags=PyCF_ONLY_AST)
    with pytest.raises(exceptions.LastNodeError):
        ast_mod.ast_first_child(empty_tree)
    with pytest.raises(exceptions.LastNodeError):
        ast_mod.ast_last_child(empty_tree)

    # Exports edge cases
    mod = Module("mod", filepath=Path("mod.py"))
    ann_empty = compile("__all__: list[str]", filename="<>", mode="exec", flags=PyCF_ONLY_AST).body[0]  # ty:ignore[unresolved-attribute]
    assert exports_mod.get__all__(ann_empty, parent=mod) == []

    call_assign = compile("__all__ = foo()", filename="<>", mode="exec", flags=PyCF_ONLY_AST).body[0]  # ty:ignore[unresolved-attribute]
    assert exports_mod.safe_get__all__(call_assign, parent=mod, log_level=LogLevel.debug) == []

    monkeypatch.setattr(exports_mod, "get__all__", lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("bad export")))
    assert exports_mod.safe_get__all__(call_assign, parent=mod, log_level=LogLevel.debug) == []
    monkeypatch.undo()

    # Values edge cases
    const_node = compile("'hello'", filename="<>", mode="eval", flags=PyCF_ONLY_AST).body  # ty:ignore[unresolved-attribute]
    assert values_mod.get_value(const_node) == "'hello'"
    assert values_mod.get_value(None) is None
    assert values_mod.safe_get_value(None) is None

    def bad_unparse(_node: object) -> str:
        raise RuntimeError("unparse failed")

    monkeypatch.setattr(values_mod, "unparse", bad_unparse)
    assert values_mod.safe_get_value(const_node, filepath=Path("a.py")) is None
    assert values_mod.safe_get_value(const_node, filepath=None) is None
    monkeypatch.undo()

    # Parser fallback when prune_source produces invalid syntax
    monkeypatch.setattr(parser_mod, "prune_source", lambda _code: "def broken(:\n")
    parsed_mod = parser_mod._compile_module("def f():\n    return 1\n", filename="m.py", extensions=Extensions())
    assert isinstance(parsed_mod, ast.Module)

    def raise_syntax_err(*_a: object, **_kw: object) -> None:
        raise SyntaxError("bad syntax")

    with pytest.raises(SyntaxError):
        parser_mod._compile_module("x = 1", filename="m.py", extensions=Extensions(), compiler=raise_syntax_err)  # ty:ignore[invalid-argument-type]
    monkeypatch.undo()

    # c3linear edge cases
    dep = c3linear._Dependency([1, 2])
    assert dep.head == 1
    assert list(dep.tail) == [2]
    empty_dep: c3linear._Dependency[int] = c3linear._Dependency()
    assert empty_dep.head is None

    class BadLenDep(c3linear._Dependency):
        def __len__(self) -> int:
            raise ValueError("bad len")

    assert list(BadLenDep([1]).tail) == []

    dl = c3linear._DependencyList([1, 2], [2])
    assert len(dl) == 1
    assert repr(dl)
    assert len(c3linear._DependencyList()) == 0
    assert c3linear.c3linear_merge() == []
    assert c3linear.c3linear_merge([], [1, 2]) == [1, 2]

    # Collections LinesCollection & ModulesCollection
    lc = collections.LinesCollection()
    lc[Path("test.py")] = ["a = 1", "b = 2"]
    assert bool(lc)
    assert list(lc.keys()) == [Path("test.py")]
    assert list(lc.values()) == [["a = 1", "b = 2"]]
    assert list(lc.items()) == [(Path("test.py"), ["a = 1", "b = 2"])]
    mc = collections.ModulesCollection()
    mc["mod"] = mod
    assert bool(mc)
    assert mc.all_members is mc.members

    # Debug info edge cases
    assert debug._get_version("nonexistent_dist_xyz_999") == "0.0.0"
    monkeypatch.setenv("GRIFFE_TEST_VAR", "val123")
    debug._print_debug_info()

    class FakeImplVersion:
        major = 3
        minor = 13
        micro = 0
        releaselevel = "alpha"
        serial = 1

    class FakeImpl:
        name = "cpython"
        version = FakeImplVersion()

    monkeypatch.setattr(debug.sys, "implementation", FakeImpl())
    assert debug._interpreter_name_version() == ("cpython", "3.13.0a1")
    monkeypatch.delattr(debug.sys, "implementation")
    assert debug._interpreter_name_version() == ("", "0.0.0")
    monkeypatch.undo()

    # Exceptions
    assert str(exceptions.CyclicAliasError(["a.b", "b.a"]))
    mod_builtin = Module("builtins", filepath=None)
    alias_builtin = Alias("a", "b", parent=mod_builtin)
    err_alias = exceptions.AliasResolutionError(alias_builtin)
    assert str(err_alias)
    assert str(err_alias)  # Second call uses cached _detailed_message

    # Importer edge cases
    with importer.sys_path():
        pass
    assert importer.dynamic_import("os.path.join") is not None
    with pytest.raises(ImportError):
        importer.dynamic_import("os.path.nonexistent_attr_xyz_999")
    with pytest.raises(ImportError):
        importer.dynamic_import("nonexistent_pkg_xyz_999.sub")

    # Logger patching and disable context manager
    log_inst = logger.get_logger("griffe.test_custom")
    assert logger.get_logger("griffe.test_custom") is log_inst
    with log_inst.disable():
        assert log_inst._logger.level == 100
    logger.patch_loggers(logging.getLogger)
    assert log_inst._logger.name == "griffe.test_custom"

    # Stats formatting with 0 modules and >0 modules (including builtin and directory filepath)
    from griffe._internal.models import Attribute  # noqa: PLC0415

    mod_dir = Module("dir_mod", filepath=[Path("a"), Path("b")])
    mod_dir["alias_mem"] = Alias("alias_mem", "other.x", parent=mod_dir)
    mod_dir["attr_mem"] = Attribute("attr_mem", value="1", parent=mod_dir)
    mod_builtin_stat = Module("builtin_mod", filepath=None)
    mc_dir = collections.ModulesCollection()
    mc_dir["dir_mod"] = mod_dir
    mc_dir["builtin_mod"] = mod_builtin_stat
    loader_dir = type(
        "DummyLoader",
        (),
        {
            "lines_collection": lc,
            "modules_collection": mc_dir,
            "force_inspection": False,
        },
    )()
    st_dir = stats.Stats(loader_dir)  # ty:ignore[invalid-argument-type]
    st_dir.time_spent_visiting = 1000
    st_dir.time_spent_inspecting = 1000
    assert "Time spent visiting" in st_dir.as_text()

    mod_py = Module("py_mod", filepath=Path("py_mod.py"))
    mc_py = collections.ModulesCollection()
    mc_py["py_mod"] = mod_py
    loader_force = type(
        "DummyLoaderForce",
        (),
        {
            "lines_collection": lc,
            "modules_collection": mc_py,
            "force_inspection": True,
        },
    )()
    st_force = stats.Stats(loader_force)  # ty:ignore[invalid-argument-type]
    st_force.time_spent_visiting = 1000
    st_force.time_spent_inspecting = 1000
    assert "Time spent visiting" in st_force.as_text()

    mc_only_py = collections.ModulesCollection()
    mc_only_py["py_mod"] = mod_py
    loader_no_insp = type(
        "DummyLoaderNoInsp",
        (),
        {
            "lines_collection": lc,
            "modules_collection": mc_only_py,
            "force_inspection": False,
        },
    )()
    st_no_insp = stats.Stats(loader_no_insp)  # ty:ignore[invalid-argument-type]
    st_no_insp.time_spent_visiting = 1000
    st_no_insp.time_spent_inspecting = 0
    assert "Time spent inspecting" in st_no_insp.as_text()
