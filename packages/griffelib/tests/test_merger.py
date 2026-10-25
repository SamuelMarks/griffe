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

# Tests for the `merger` module.

from __future__ import annotations

import pytest

from griffe import temporary_visited_package


def test_dont_trigger_alias_resolution_when_merging_stubs() -> None:
    """Assert that we don't trigger alias resolution when merging stubs."""
    with temporary_visited_package(
        "package",
        {
            "mod.py": "import pathlib\n\ndef f() -> pathlib.Path:\n    return pathlib.Path()",
            "mod.pyi": "import pathlib\n\ndef f() -> pathlib.Path: ...",
        },
    ) as pkg:
        assert not pkg["mod.pathlib"].resolved


def test_merge_stubs_on_wildcard_imported_objects() -> None:
    """Assert that stubs can be merged on wildcard imported objects."""
    with temporary_visited_package(
        "package",
        {
            "mod.py": "class A:\n    def hello(value: int | str) -> int | str:\n        return value",
            "__init__.py": "from .mod import *",
            "__init__.pyi": """
                from typing import overload
                class A:
                    @overload
                    def hello(value: int) -> int: ...
                    @overload
                    def hello(value: str) -> str: ...
                """,
        },
    ) as pkg:
        assert pkg["A.hello"].overloads


def test_merge_imports() -> None:
    """Assert that imports are merged correctly."""
    with temporary_visited_package(
        "package",
        {
            "mod.py": "import abc",
            "mod.pyi": "import collections",
        },
    ) as pkg:
        assert set(pkg["mod"].imports) == {"abc", "collections"}


def test_override_exports() -> None:
    """Assert that exports are overridden too (like imports are merged)."""
    with temporary_visited_package(
        "package",
        {
            "__init__.py": "import dynamic_all\n__all__ = dynamic_all()",
            "__init__.pyi": "from ._hello import hello\n__all__ = ['hello']",
            "_hello.py": "def hello() -> None:\n    '''Say hello.'''",
        },
    ) as pkg:
        assert pkg.exports == ["hello"]


def test_merge_attribute_values() -> None:
    """Assert that attribute values are merged correctly."""
    with temporary_visited_package(
        "package",
        {
            "__init__.py": "import dynamic_all\n__all__ = dynamic_all()",
            "__init__.pyi": "from ._hello import hello\n__all__ = ['hello']",
            "_hello.py": "def hello() -> None:\n    '''Say hello.'''",
        },
    ) as pkg:
        assert str(pkg["__all__"].value) == "['hello']"


def test_merge_overload_annotations() -> None:
    """Assert that overload annotations are merged correctly."""
    with temporary_visited_package(
        "package",
        {
            "mod.py": "def func(x): ...",
            "mod.pyi": """
                from typing import overload

                @overload
                def func(x: int) -> int: ...

                @overload
                def func(x: float) -> float: ...
                """,
        },
    ) as pkg:
        func = pkg["mod.func"]
        assert str(func.parameters["x"].annotation) == "int | float"
        assert str(func.returns) == "int | float"


@pytest.mark.parametrize(
    ("psd", "expected"),
    [(True, "Stubs"), (False, "Source")],
)
def test_prefer_stubs_docstrings(psd: bool, expected: str) -> None:
    """The "prefer stubs docstrings" option is respected."""
    with temporary_visited_package(
        "package",
        {
            "mod.py": "def func():\n    '''Source'''",
            "mod.pyi": "def func():\n    '''Stubs'''",
        },
        prefer_stubs_docs=psd,
    ) as pkg:
        func = pkg["mod.func"]
        assert func.docstring.value == expected


def test_merger_and_helpers_edge_cases() -> None:
    """Test stubs merger edge cases and `griffe._internal.helpers` functions."""
    from pathlib import Path  # noqa: PLC0415

    from griffe._internal import helpers as helpers_mod  # noqa: PLC0415
    from griffe._internal import merger as merger_mod  # noqa: PLC0415
    from griffe._internal.enumerations import TypeParameterKind  # noqa: PLC0415
    from griffe._internal.expressions import ExprName  # noqa: PLC0415
    from griffe._internal.models import (  # noqa: PLC0415
        Alias,
        Attribute,
        Class,
        Docstring,
        Function,
        Module,
        Parameter,
        Parameters,
        TypeAlias,
        TypeParameter,
        TypeParameters,
    )

    # helpers: vtree, htree, module_vtree
    with pytest.raises(ValueError, match="At least one object"):
        helpers_mod.vtree()
    with pytest.raises(ValueError, match="At least one object"):
        helpers_mod.htree()

    m_a = Module("a")
    m_b = Module("b")
    assert helpers_mod.vtree(m_a, m_b, return_leaf=True) is m_b
    m_root = Module("root")
    c1 = Class("C1")
    c2 = Class("C2")
    assert helpers_mod.htree(m_root, c1, c2) is m_root
    assert "C1" in m_root.members
    assert "C2" in m_root.members
    leaf_mod = helpers_mod.module_vtree("x.y.z", leaf_package=False, return_leaf=True)
    assert leaf_mod.filepath.name == "z.py"  # ty:ignore[unresolved-attribute]
    pkg_mod = helpers_mod.module_vtree("x.y.z", leaf_package=True, return_leaf=True)
    assert pkg_mod.filepath.name == "__init__.py"  # ty:ignore[unresolved-attribute]

    # temporary_pypackage with list of modules and inits=False
    with helpers_mod.temporary_pypackage("pkg", ["sub/mod.py"], init=False, inits=False) as tmp_pkg:
        assert (tmp_pkg.path / "sub" / "mod.py").exists()
        assert not (tmp_pkg.path / "__init__.py").exists()

    # temporary_visited_package and temporary_inspected_package with search_sys_path=True
    with helpers_mod.temporary_visited_package("vpkg", {"m.py": "x = 1"}, search_sys_path=True) as vpkg:
        assert "m" in vpkg.members
    with helpers_mod.temporary_inspected_package("ipkg", {"m.py": "x = 1"}, search_sys_path=True) as ipkg:
        assert "m" in ipkg.members

    # temporary_inspected_module when module_name was removed from sys.modules
    import sys  # noqa: PLC0415

    with helpers_mod.temporary_inspected_module("x = 1", module_name="temp_del_mod"):
        sys.modules.pop("temp_del_mod", None)

    # merge_stubs order and error when neither is .pyi
    reg1 = Module("m", filepath=Path("m.py"))
    reg2 = Module("m", filepath=Path("m2.py"))
    with pytest.raises(ValueError, match="cannot merge regular"):
        merger_mod.merge_stubs(reg1, reg2)

    stub_first = Module("m", filepath=Path("m.pyi"))
    reg_second = Module("m", filepath=Path("m.py"))
    assert merger_mod.merge_stubs(stub_first, reg_second) is reg_second

    # _merge_annotations empty, single, multiple
    assert merger_mod._merge_annotations([]) is None
    e1 = ExprName("int")
    e2 = ExprName("str")
    assert merger_mod._merge_annotations([e1]) is e1
    assert str(merger_mod._merge_annotations([e1, e2])) == "int | str"

    # _merge_stubs_overloads with empty overloads list and non-function target
    mod_concrete = Module("mc", filepath=Path("mc.py"))
    mod_concrete["not_a_func"] = Attribute("not_a_func", value="1", parent=mod_concrete)
    mod_concrete["fn"] = Function(
        "fn",
        parameters=Parameters(Parameter("a", annotation=None), Parameter("already", annotation=e1)),
        returns=None,
        parent=mod_concrete,
    )
    mod_stubs = Module("mc", filepath=Path("mc.pyi"), docstring=Docstring("stub doc"))
    mod_stubs["fn"] = Function(
        "fn",
        parameters=Parameters(Parameter("a", annotation=e1), Parameter("extra_stub_param", annotation=e2)),
        returns=None,
        parent=mod_stubs,
    )
    mod_stubs.exports = ["fn"]
    mod_stubs.overloads["empty_ov"] = []
    mod_stubs.overloads["not_a_func"] = [Function("not_a_func")]
    ov1 = Function("fn", parameters=Parameters(Parameter("a", annotation=e1)), returns=e1)
    ov2 = Function("fn", parameters=Parameters(Parameter("a", annotation=e2)), returns=e2)
    ov3 = Function("fn", parameters=Parameters(Parameter("a", annotation="raw_str")), returns="raw_str")
    mod_stubs.overloads["fn"] = [ov1, ov2, ov3]

    # Members in stubs: alias, different kind overwrite, class, function, attribute, type_alias, new member
    mod_concrete["diff_kind"] = Attribute("diff_kind", value="1", parent=mod_concrete)
    mod_stubs["diff_kind"] = Function("diff_kind", parent=mod_stubs)
    mod_concrete["aliased_in_stub"] = Attribute("aliased_in_stub", value="1", parent=mod_concrete)
    mod_stubs["aliased_in_stub"] = Alias("aliased_in_stub", "other.x", parent=mod_stubs)

    mod_concrete["sub_mod"] = Module("sub_mod", filepath=Path("sub.py"), parent=mod_concrete)
    mod_stubs["sub_mod"] = Module("sub_mod", filepath=Path("sub.pyi"), parent=mod_stubs)

    mod_concrete["Cls"] = Class("Cls", parent=mod_concrete)
    mod_stubs["Cls"] = Class(
        "Cls",
        type_parameters=TypeParameters(TypeParameter("T", kind=TypeParameterKind.type_var)),
        parent=mod_stubs,
    )

    mod_concrete["attr_val"] = Attribute("attr_val", value="1", parent=mod_concrete)
    mod_stubs["attr_val"] = Attribute("attr_val", value="2", annotation=e1, parent=mod_stubs)
    mod_concrete["attr_ellipsis"] = Attribute("attr_ellipsis", value="1", parent=mod_concrete)
    mod_stubs["attr_ellipsis"] = Attribute("attr_ellipsis", value="...", annotation=e1, parent=mod_stubs)

    mod_concrete["TA"] = TypeAlias("TA", parent=mod_concrete)
    mod_stubs["TA"] = TypeAlias(
        "TA",
        type_parameters=TypeParameters(TypeParameter("T", kind=TypeParameterKind.type_var)),
        parent=mod_stubs,
    )

    mod_stubs["only_in_stub"] = Attribute("only_in_stub", value="1", parent=mod_stubs)

    merger_mod.merge_stubs(mod_concrete, mod_stubs, prefer_stubs_docs=True)
    assert mod_concrete["only_in_stub"].runtime is False
    assert mod_concrete["attr_val"].value == "2"
    assert mod_concrete["attr_ellipsis"].value == "1"
    assert mod_concrete["diff_kind"].is_function
