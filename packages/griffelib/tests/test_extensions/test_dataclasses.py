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

# Test the dataclasses extension.

from griffe import ParameterKind, load_extensions, temporary_visited_package


def test_dataclass_support() -> None:
    """Test our `dataclass` support."""
    code = """
        from dataclasses import dataclass

        @dataclass
        class Point:
            x: int
            '''Docstring for x.'''
            y: int
            '''Docstring for y.'''
    """
    with temporary_visited_package(
        "pkg",
        {"__init__.py": code},
        extensions=load_extensions("dataclasses"),
    ) as pkg:
        point = pkg["Point"]
    assert "__init__" in point.members
    init = point["__init__"]
    assert len(init.parameters) == 3
    assert "self" in init.parameters
    assert "x" in init.parameters
    assert "y" in init.parameters
    assert str(init.parameters["x"].annotation) == "int"
    assert str(init.parameters["y"].annotation) == "int"
    assert init.parameters["x"].docstring.value == "Docstring for x."
    assert init.parameters["y"].docstring.value == "Docstring for y."
    assert init.returns == "None"


def test_non_init_fields() -> None:
    """Test that non-init fields are not included in the `__init__` method."""
    code = """
        from dataclasses import dataclass, field

        @dataclass
        class Point:
            x: int
            '''Docstring for x.'''
            y: int = field(init=False)
            '''Docstring for y.'''
    """
    with temporary_visited_package(
        "pkg",
        {"__init__.py": code},
        extensions=load_extensions("dataclasses"),
    ) as pkg:
        point = pkg["Point"]
    assert "__init__" in point.members
    init = point["__init__"]
    assert len(init.parameters) == 2
    assert "self" in init.parameters
    assert "x" in init.parameters
    assert "y" not in init.parameters


def test_classvar_fields() -> None:
    """Test that `ClassVar` fields are not included in the `__init__` method."""
    code = """
        from dataclasses import dataclass
        from typing import ClassVar

        @dataclass
        class Point:
            x: int
            '''Docstring for x.'''
            y: ClassVar[int]
            '''Docstring for y.'''
    """
    with temporary_visited_package(
        "pkg",
        {"__init__.py": code},
        extensions=load_extensions("dataclasses"),
    ) as pkg:
        point = pkg["Point"]
    assert "__init__" in point.members
    init = point["__init__"]
    assert len(init.parameters) == 2
    assert "self" in init.parameters
    assert "x" in init.parameters
    assert "y" not in init.parameters


def test_kw_only_fields() -> None:
    """Test that `kw_only` fields are included as keyword-only parameters in the `__init__` method."""
    code = """
        from dataclasses import dataclass, field

        @dataclass
        class Point:
            x: int
            '''Docstring for x.'''
            y: int = field(kw_only=True)
            '''Docstring for y.'''
    """
    with temporary_visited_package(
        "pkg",
        {"__init__.py": code},
        extensions=load_extensions("dataclasses"),
    ) as pkg:
        point = pkg["Point"]
    assert "__init__" in point.members
    init = point["__init__"]
    assert len(init.parameters) == 3
    assert "self" in init.parameters
    assert "x" in init.parameters
    assert "y" in init.parameters
    assert init.parameters["y"].kind is ParameterKind.keyword_only


def test_kw_only_sentinel() -> None:
    """Test that the `KW_ONLY` sentinel works."""
    code = """
        from dataclasses import dataclass, KW_ONLY

        @dataclass
        class Point:
            x: int
            '''Docstring for x.'''
            _: KW_ONLY
            y: int
            '''Docstring for y.'''
    """
    with temporary_visited_package(
        "pkg",
        {"__init__.py": code},
        extensions=load_extensions("dataclasses"),
    ) as pkg:
        point = pkg["Point"]
    assert "__init__" in point.members
    init = point["__init__"]
    assert len(init.parameters) == 3
    assert "self" in init.parameters
    assert "x" in init.parameters
    assert "y" in init.parameters
    assert init.parameters["y"].kind is ParameterKind.keyword_only


def test_all_kw_only_fields() -> None:
    """Test that all fields can be made keyword-only."""
    code = """
        from dataclasses import dataclass

        @dataclass(kw_only=True)
        class Point:
            x: int
            '''Docstring for x.'''
            y: int
            '''Docstring for y.'''
    """
    with temporary_visited_package(
        "pkg",
        {"__init__.py": code},
        extensions=load_extensions("dataclasses"),
    ) as pkg:
        point = pkg["Point"]
    assert "__init__" in point.members
    init = point["__init__"]
    assert len(init.parameters) == 3
    assert "self" in init.parameters
    assert "x" in init.parameters
    assert "y" in init.parameters
    assert init.parameters["x"].kind is ParameterKind.keyword_only
    assert init.parameters["y"].kind is ParameterKind.keyword_only


def test_dataclass_edge_cases() -> None:
    """Test dataclass extension edge cases (unpacked dict kwargs, init=False, default_factory, InitVar, MRO)."""
    from griffe._internal.expressions import ExprName  # noqa: PLC0415
    from griffe._internal.extensions import dataclasses as dc_mod  # noqa: PLC0415
    from griffe._internal.models import Class, Parameter  # noqa: PLC0415

    code = """
        import dataclasses
        from dataclasses import dataclass, field, InitVar

        DC_OPTS = {"kw_only": False}

        def other_dec(cls):
            return cls

        @other_dec
        @dataclass(**DC_OPTS)
        class Base:
            a: int = dataclasses.field(default_factory=list)
            init_var: InitVar[str] = "iv"
            unannotated = 123
            def method(self) -> None:
                pass

        @dataclass(init=False)
        class NoInit(Base):
            b: int = 1

        @dataclass
        class Child(Base):
            from . import Base as _Base
            c: int = 2
            class Nested:
                pass

        class WithManualInit:
            def __init__(self) -> None:
                pass
    """
    with temporary_visited_package(
        "pkg",
        {"__init__.py": code, "sub.py": "from . import Base\n"},
        extensions=load_extensions("dataclasses"),
    ) as pkg:
        base = pkg["Base"]
        assert "init_var" not in base.members
        assert str(base["__init__"].parameters["a"].default) == "list()"
        assert "b" not in pkg["NoInit"]["__init__"].parameters

    # Direct unit checks for _expr_args with non-call/non-dict, _reorder_parameters with positional_only,
    # _set_dataclass_init with broken MRO, and _apply_recursively with already-processed
    assert dc_mod._expr_args(ExprName("x")) == {}
    p_pos = Parameter("p1", kind=ParameterKind.positional_only)
    p_kw = Parameter("p2", kind=ParameterKind.keyword_only)
    p_reg = Parameter("p3", kind=ParameterKind.positional_or_keyword)
    assert dc_mod._reorder_parameters([p_kw, p_reg, p_pos]) == [p_pos, p_reg, p_kw]

    cls_bad_mro = Class("BadMRO", bases=[ExprName("MissingBase")])
    dc_mod._set_dataclass_init(cls_bad_mro)

    processed = {cls_bad_mro.canonical_path}
    dc_mod._apply_recursively(cls_bad_mro, processed)
