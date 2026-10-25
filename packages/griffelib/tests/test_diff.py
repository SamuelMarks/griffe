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

# Tests for the `diff` module.

from __future__ import annotations

from pathlib import Path

import pytest

from griffe import Breakage, BreakageKind, find_breaking_changes, temporary_visited_module, temporary_visited_package


@pytest.mark.parametrize(
    ("old_code", "new_code", "expected_breakages"),
    [
        (
            "class a(int, str): ...",
            "class a(int): ...",
            [BreakageKind.CLASS_REMOVED_BASE],
        ),
        (
            "a = 0",
            "class a: ...",
            [BreakageKind.OBJECT_CHANGED_KIND],
        ),
        (
            "a = True",
            "",
            [BreakageKind.OBJECT_REMOVED],
        ),
        (
            "def a(): ...",
            "def a(x): ...",
            [BreakageKind.PARAMETER_ADDED_REQUIRED],
        ),
        (
            "def a(x=0): ...",
            "def a(x=1): ...",
            [BreakageKind.PARAMETER_CHANGED_DEFAULT],
        ),
        (
            # Positional-only to keyword-only.
            "def a(x, /): ...",
            "def a(*, x): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        (
            # Keyword-only to positional-only.
            "def a(*, x): ...",
            "def a(x, /): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        (
            # Positional or keyword to positional-only.
            "def a(x): ...",
            "def a(x, /): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        (
            # Positional or keyword to keyword-only.
            "def a(x): ...",
            "def a(*, x): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        # To variadic positional.
        (
            # Positional-only to variadic positional.
            "def a(x, /): ...",
            "def a(*x): ...",
            [],
        ),
        (
            # Positional or keyword to variadic positional.
            "def a(x): ...",
            "def a(*x): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        (
            # Keyword-only to variadic positional.
            "def a(*, x): ...",
            "def a(*x): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        (
            # Variadic keyword to variadic positional.
            "def a(**x): ...",
            "def a(*x): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        (
            # Positional or keyword to variadic positional, with variadic keyword.
            "def a(x): ...",
            "def a(*x, **y): ...",
            [],
        ),
        (
            # Keyword-only to variadic positional, with variadic keyword.
            "def a(*, x): ...",
            "def a(*x, **y): ...",
            [],
        ),
        # To variadic keyword.
        (
            # Positional-only to variadic keyword.
            "def a(x, /): ...",
            "def a(**x): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        (
            # Positional or keyword to variadic keyword.
            "def a(x): ...",
            "def a(**x): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        (
            # Keyword-only to variadic keyword.
            "def a(*, x): ...",
            "def a(**x): ...",
            [],
        ),
        (
            # Variadic positional to variadic keyword.
            "def a(*x): ...",
            "def a(**x): ...",
            [BreakageKind.PARAMETER_CHANGED_KIND],
        ),
        (
            # Positional-only to variadic keyword, with variadic positional.
            "def a(x, /): ...",
            "def a(*y, **x): ...",
            [],
        ),
        (
            # Positional or keyword to variadic keyword, with variadic positional.
            "def a(x): ...",
            "def a(*y, **x): ...",
            [],
        ),
        (
            "def a(x=1): ...",
            "def a(x): ...",
            [BreakageKind.PARAMETER_CHANGED_REQUIRED],
        ),
        (
            "def a(x, y): ...",
            "def a(y, x): ...",
            [BreakageKind.PARAMETER_MOVED, BreakageKind.PARAMETER_MOVED],
        ),
        (
            "def a(x, y): ...",
            "def a(x): ...",
            [BreakageKind.PARAMETER_REMOVED],
        ),
        (
            "def a() -> int: ...",
            "def a() -> str: ...",
            [],  # Not supported yet: `BreakageKind.RETURN_CHANGED_TYPE`.
        ),
    ],
)
def test_diff_griffe(old_code: str, new_code: str, expected_breakages: list[Breakage]) -> None:
    """Test the different incompatibility finders.

    Parameters:
        old_code: Parametrized code of the old module version.
        new_code: Parametrized code of the new module version.
        expected_breakages: A list of breakage kinds to expect.
    """
    # Check without any alias.
    with temporary_visited_module(old_code) as old_package, temporary_visited_module(new_code) as new_package:
        breaking = list(find_breaking_changes(old_package, new_package))
    assert len(breaking) == len(expected_breakages)
    for breakage, expected_kind in zip(breaking, expected_breakages, strict=False):
        assert breakage.kind is expected_kind
    # Check with aliases.
    import_a = "from ._mod_a import a\n__all__ = ['a']"
    old_modules = {"__init__.py": import_a, "_mod_a.py": old_code}
    new_modules = {"__init__.py": new_code and import_a, "_mod_a.py": new_code}
    with temporary_visited_package("package_old", old_modules) as old_package:  # noqa: SIM117
        with temporary_visited_package("package_new", new_modules) as new_package:
            breaking = list(find_breaking_changes(old_package, new_package))
    assert len(breaking) == len(expected_breakages)
    for breakage, expected_kind in zip(breaking, expected_breakages, strict=False):
        assert breakage.kind is expected_kind


def test_moving_members_in_parent_classes() -> None:
    """Test that moving an object from a base class to a parent class doesn't trigger a breakage."""
    old_code = """
        class Parent:
            ...

        class Base(Parent):
            def method(self):
                ...
    """
    new_code = """
        class Parent:
            def method(self):
                ...

        class Base(Parent):
            ...
    """
    with temporary_visited_module(old_code) as old_package, temporary_visited_module(new_code) as new_package:
        assert not list(find_breaking_changes(old_package, new_package))


def test_breakage_explanations_and_diff_edge_cases(tmp_path: Path) -> None:
    """Test breakage formatting styles and diff edge cases."""
    from griffe._internal.diff import (  # noqa: PLC0415
        AttributeChangedTypeBreakage,
        AttributeChangedValueBreakage,
        ClassRemovedBaseBreakage,
        ObjectChangedKindBreakage,
        ObjectRemovedBreakage,
        ParameterAddedRequiredBreakage,
        ParameterChangedDefaultBreakage,
        ParameterChangedKindBreakage,
        ParameterChangedRequiredBreakage,
        ParameterMovedBreakage,
        ParameterRemovedBreakage,
        ReturnChangedTypeBreakage,
        _class_incompatibilities,
        _function_incompatibilities,
        _member_incompatibilities,
        _returns_are_compatible,
        _type_based_yield,
    )
    from griffe._internal.enumerations import ExplanationStyle, Kind, ParameterKind  # noqa: PLC0415
    from griffe._internal.expressions import ExprName  # noqa: PLC0415
    from griffe._internal.git import _WORKTREE_PREFIX  # noqa: PLC0415
    from griffe._internal.models import Alias, Attribute, Class, Function, Module, Parameter, Parameters  # noqa: PLC0415

    mod = Module("pkg", filepath=Path.cwd() / "pkg" / "__init__.py")
    sub = Module("sub", filepath=Path.cwd() / "pkg" / "sub.py", parent=mod)
    mod["sub"] = sub
    attr_old = Attribute("attr", value="1", annotation="int", lineno=10, endlineno=12, parent=sub)
    attr_new = Attribute("attr", value="2", annotation="str", lineno=10, endlineno=10, parent=sub)
    sub["attr"] = attr_new

    cls_old = Class("MyClass", bases=[ExprName("BaseA"), ExprName("BaseB")], lineno=1, endlineno=5, parent=sub)
    cls_new = Class("MyClass", bases=[ExprName("BaseA")], lineno=1, endlineno=5, parent=sub)
    sub["MyClass"] = cls_new

    p_req = Parameter("p", kind=ParameterKind.positional_or_keyword, default=None)
    p_opt = Parameter("p", kind=ParameterKind.positional_or_keyword, default="1")
    p_kw = Parameter("p", kind=ParameterKind.keyword_only, default="1")
    fn_new = Function("fn", parameters=Parameters(p_req), returns="str", lineno=20, endlineno=25, parent=sub)
    sub["fn"] = fn_new

    breakages: list[Breakage] = [
        AttributeChangedTypeBreakage(attr_new, "int", "str", details="extra detail"),
        AttributeChangedValueBreakage(attr_new, "1", ""),
        AttributeChangedValueBreakage(attr_new, "", "2"),
        ClassRemovedBaseBreakage(cls_new, [ExprName("BaseA"), ExprName("BaseB")], [ExprName("BaseA")]),
        ObjectChangedKindBreakage(attr_new, Kind.FUNCTION, Kind.ATTRIBUTE),
        ObjectRemovedBreakage(attr_old, None, None),
        ObjectRemovedBreakage(sub, None, None),
        ParameterAddedRequiredBreakage(fn_new, None, p_req),
        ParameterChangedDefaultBreakage(fn_new, p_opt, p_opt),
        ParameterChangedKindBreakage(fn_new, p_opt, p_kw),
        ParameterChangedRequiredBreakage(fn_new, p_opt, p_req),
        ParameterMovedBreakage(fn_new, p_req, p_req, details="moved"),
        ParameterRemovedBreakage(fn_new, p_req, None),
        ReturnChangedTypeBreakage(fn_new, "int", "str"),
    ]

    for style in ExplanationStyle:
        for b in breakages:
            assert b.explain(style=style)
            assert str(b)
            assert repr(b)

    assert breakages[0].as_dict()["kind"] == BreakageKind.ATTRIBUTE_CHANGED_TYPE
    assert breakages[0]._filepath == sub.filepath
    assert breakages[0]._relative_package_filepath

    # Worktree prefix location stripping and alias properties
    wt_mod = Module("wt", filepath=tmp_path / f"{_WORKTREE_PREFIX}123" / "griffe_repo" / "pkg" / "mod.py")
    wt_attr = Attribute("x", value="1", lineno=5, parent=wt_mod)
    b_wt = ObjectRemovedBreakage(wt_attr, wt_attr, None)
    assert b_wt._location == Path("pkg/mod.py")
    assert b_wt._lineno == 0

    ext_mod = Module("ext", filepath=Path("/nonexistent_root_path_xyz/ext.py"))
    ext_attr = Attribute("x", value="1", lineno=None, parent=ext_mod)
    b_ext = ObjectRemovedBreakage(ext_attr, None, None)
    assert b_ext._location == Path("/nonexistent_root_path_xyz/ext.py")

    alias_obj = Alias("my_alias", "pkg.sub.attr", lineno=42, parent=mod)
    b_alias = ObjectRemovedBreakage(alias_obj, alias_obj, None)  # ty:ignore[invalid-argument-type]
    assert b_alias._filepath == mod.filepath
    assert b_alias._relative_filepath == mod.relative_filepath
    assert b_alias._relative_package_filepath == mod.relative_package_filepath
    assert b_alias._canonical_path == "pkg.my_alias"
    assert b_alias._module_path == "pkg"
    assert b_alias._lineno == 42

    # Test _returns_are_compatible
    assert not _returns_are_compatible(
        Function("f1", returns="int"),
        Function("f2", returns=None),
    )
    assert _returns_are_compatible(
        Function("f1", returns="int"),
        Function("f2", returns="int"),
    )
    assert _returns_are_compatible(
        Function("f1", returns="int"),
        Function("f2", returns="str"),
    )

    # Test _class_incompatibilities when bases did not shrink
    assert not list(_class_incompatibilities(cls_new, cls_old, seen_paths=set()))

    # Test _function_incompatibilities with *args / **kwargs swallowing removed params and bad default equality
    class BadEq:
        def __ne__(self, other: object) -> bool:
            raise RuntimeError("bad eq")

    fn_with_var = Function(
        "f",
        parameters=Parameters(
            Parameter("d", default=BadEq()),  # ty:ignore[invalid-argument-type]
            Parameter("args", kind=ParameterKind.var_positional),
            Parameter("kwargs", kind=ParameterKind.var_keyword),
        ),
        returns=None,
    )
    fn_old_params = Function(
        "f",
        parameters=Parameters(
            Parameter("a", kind=ParameterKind.positional_only),
            Parameter("b", kind=ParameterKind.positional_or_keyword),
            Parameter("args", kind=ParameterKind.var_positional),
            Parameter("c", kind=ParameterKind.keyword_only),
            Parameter("d", default=BadEq()),  # ty:ignore[invalid-argument-type]
        ),
        returns="int",
    )
    incomp_fn = list(_function_incompatibilities(fn_old_params, fn_with_var))
    assert any(b.kind is BreakageKind.PARAMETER_CHANGED_DEFAULT for b in incomp_fn)
    assert any(b.kind is BreakageKind.RETURN_CHANGED_TYPE for b in incomp_fn)

    # Test _member_incompatibilities with debug logging, private members, and unresolved aliases
    from griffe._internal.collections import ModulesCollection  # noqa: PLC0415
    from griffe._internal.logger import logger  # noqa: PLC0415

    mc = ModulesCollection()
    m1 = Module("m", modules_collection=mc)
    m2 = Module("m", modules_collection=mc)
    m1["_priv"] = Attribute("_priv", value="1", parent=m1)
    m1["bad_alias"] = Alias("bad_alias", "missing.x", parent=m1)
    m2["bad_alias"] = Alias("bad_alias", "missing.y", parent=m2)
    m1["submod"] = Module("submod", parent=m1)
    m2["submod"] = Module("submod", parent=m2)
    m1["removed_priv_alias"] = Alias("removed_priv_alias", "missing.z", parent=m1)
    m1["removed_priv_alias"].public = False
    m1["val_same"] = Attribute("val_same", value="1", parent=m1)
    m2["val_same"] = Attribute("val_same", value="1", parent=m2)

    orig_enabled = logger._logger.isEnabledFor
    logger._logger.isEnabledFor = lambda _lvl: True
    try:
        assert not list(_member_incompatibilities(m1, m2))
    finally:
        logger._logger.isEnabledFor = orig_enabled

    # Seen paths early return and non-standard object kind in _type_based_yield
    assert not list(_type_based_yield(m1["val_same"], m2["val_same"], seen_paths={m1["val_same"].path}))

    from griffe._internal.models import TypeAlias  # noqa: PLC0415

    ta1 = TypeAlias("TA", parent=m1)
    ta2 = TypeAlias("TA", parent=m2)
    assert not list(_type_based_yield(ta1, ta2, seen_paths=set()))

    # Variadic parameter default check skipped in _function_incompatibilities
    fn_var1 = Function("fv", parameters=Parameters(Parameter("args", kind=ParameterKind.var_positional, default="()")))
    fn_var2 = Function("fv", parameters=Parameters(Parameter("args", kind=ParameterKind.var_positional, default="()")))
    assert not list(_function_incompatibilities(fn_var1, fn_var2))

    # Optional parameter becoming required skips non_required default check, and equal defaults do not yield breakage
    fn_opt = Function("fr", parameters=Parameters(p_opt))
    fn_req = Function("fr", parameters=Parameters(p_req))
    assert any(b.kind is BreakageKind.PARAMETER_CHANGED_REQUIRED for b in _function_incompatibilities(fn_opt, fn_req))
    assert not list(_function_incompatibilities(fn_opt, fn_opt))
