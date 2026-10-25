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

# Test inspection mechanisms.

from __future__ import annotations

import sys

import pytest

from griffe import (
    Expr,
    TypeParameterKind,
    inspect,
    temporary_inspected_module,
    temporary_inspected_package,
    temporary_pypackage,
)
from tests.helpers import clear_sys_modules


def test_annotations_from_builtin_types() -> None:
    """Assert builtin types are correctly transformed to annotations."""
    with temporary_inspected_module("def func(a: int) -> str: pass") as module:
        func = module["func"]
        assert func.parameters[0].name == "a"
        assert func.parameters[0].annotation.name == "int"
        assert func.returns.name == "str"


def test_annotations_from_classes() -> None:
    """Assert custom classes are correctly transformed to annotations."""
    with temporary_inspected_module("class A: pass\ndef func(a: A) -> A: pass") as module:
        func = module["func"]
        assert func.parameters[0].name == "a"
        param = func.parameters[0].annotation
        assert param.name == "A"
        assert param.canonical_path == f"{module.name}.A"
        returns = func.returns
        assert returns.name == "A"
        assert returns.canonical_path == f"{module.name}.A"


# YORE: EOL 3.13: Remove block.
@pytest.mark.skipif(sys.version_info >= (3, 14), reason="3.14 changes type annotations, see test below")
@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        ("tuple[int, str]", "tuple[int, str]"),
        ("Union[int, str]", "typing.Union[int, str]"),
        ("int | str", "int | str"),
        ("int | Literal[1]", "typing.Union[int, typing.Literal[1]]"),
    ],
)
def test_annotations_from_types_before_314(annotation: str, expected: str) -> None:
    """Assert annotations are correctly converted to string."""
    with temporary_inspected_module(
        f"""
        from typing import Literal, Union
        def func(param: {annotation}): ...
        """,
    ) as module:
        param = module["func"].parameters["param"]
        assert str(param.annotation) == expected


# YORE: EOL 3.13: Remove line.
@pytest.mark.skipif(sys.version_info < (3, 14), reason="3.14 modernizes type unions")
@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        ("tuple[int, str]", "tuple[int, str]"),
        ("Union[int, str]", "int | str"),
        ("int | str", "int | str"),
        ("int | Literal[1]", "int | typing.Literal[1]"),
    ],
)
def test_annotations_from_types(annotation: str, expected: str) -> None:  # pragma: no cover
    """Assert annotations are correctly converted to string."""
    with temporary_inspected_module(
        f"""
        from typing import Literal, Union
        def func(param: {annotation}): ...
        """,
    ) as module:
        param = module["func"].parameters["param"]
        assert str(param.annotation) == expected


def test_class_level_imports() -> None:
    """Assert annotations using class-level imports are resolved."""
    with temporary_inspected_module(
        """
        class A:
            from io import StringIO
            def method(self, p: StringIO):
                pass
        """,
    ) as module:
        method = module["A.method"]
        name = method.parameters["p"].annotation
        assert name.name == "StringIO"
        assert name.canonical_path == "io.StringIO"


def test_missing_dependency() -> None:
    """Assert missing dependencies are handled during dynamic imports."""
    with pytest.raises(ImportError, match="ModuleNotFoundError: No module named 'missing'"):
        temporary_inspected_module("import missing").__enter__()


def test_inspect_properties_as_attributes() -> None:
    """Assert properties are created as attributes and not functions."""
    with temporary_inspected_module(
        """
        from functools import cached_property

        class C:
            @property
            def prop(self) -> bool:
                return True
            @cached_property
            def cached_prop(self) -> int:
                return 0
        """,
    ) as module:
        assert module["C.prop"].is_attribute
        assert "property" in module["C.prop"].labels
        assert module["C.cached_prop"].is_attribute
        assert "cached" in module["C.cached_prop"].labels


def test_inspecting_module_importing_other_module() -> None:
    """Assert aliases to modules are correctly inspected and aliased."""
    with temporary_inspected_module("import itertools as it") as module:
        assert module["it"].is_alias
        assert module["it"].target_path == "itertools"


def test_inspecting_lazy_module_members() -> None:
    """Inspect members exposed by module hooks without caching them in globals."""
    # Neither lazy member is stored in the module's namespace.
    with temporary_inspected_module(
        '''
        def __dir__():
            return sorted(set(globals()) | {"hello", "answer", "missing"})

        def __getattr__(name):
            if name == "hello":
                def hello() -> str:
                    """Return a greeting."""
                    return "Hello!"
                return hello
            if name == "answer":
                return 42
            raise AttributeError(name)
        ''',
    ) as module:
        hello = module["hello"]

        assert hello.is_function
        assert str(hello.returns) == "str"
        assert hello.docstring.value == "Return a greeting."
        assert module["answer"].value == "42"
        assert "missing" not in module.members

        # Inspection must not populate the runtime module's globals.
        assert "hello" not in vars(sys.modules[module.name])
        assert "answer" not in vars(sys.modules[module.name])


def test_inspecting_lazy_reexports() -> None:
    """Resolve lazy reexports without caching them in the package globals."""
    with temporary_inspected_package(
        "pkg",
        {
            "__init__.py": """
                __all__ = ["hello"]

                def __dir__():
                    return sorted(set(globals()) | set(__all__))

                def __getattr__(name):
                    if name == "hello":
                        from ._impl import hello
                        return hello
                    raise AttributeError(name)
            """,
            "_impl.py": '''
                def hello() -> str:
                    """Return a greeting."""
                    return "Hello!"
            ''',
        },
        resolve_aliases=True,
    ) as package:
        hello = package["hello"]

        assert hello.is_alias
        assert hello.target_path == "pkg._impl.hello"
        assert hello.docstring.value == "Return a greeting."
        assert "hello" not in vars(sys.modules[package.name])


def test_inspecting_parameters_with_functions_as_default_values() -> None:
    """Assert functions as default parameter values are serialized with their name."""
    with temporary_inspected_module("def func(): ...\ndef other_func(f=func): ...") as module:
        default = module["other_func"].parameters["f"].default
    assert default == "func"


def test_inspecting_package_and_module_with_same_names() -> None:
    """Package and module having same name shouldn't cause issues."""
    with temporary_inspected_package("package", {"package.py": "a = 0"}):
        pass


def test_inspecting_module_with_submodules() -> None:
    """Inspecting a module shouldn't register any of its submodules if they're not imported."""
    with temporary_pypackage("pkg", ["mod.py"]) as tmp_package:
        pkg = inspect("pkg", filepath=tmp_package.path / "__init__.py")
    assert "mod" not in pkg.members
    clear_sys_modules("pkg")


def test_inspecting_module_with_imported_submodules() -> None:
    """When inspecting a package on the disk, direct submodules should be skipped entirely."""
    with temporary_pypackage(
        "pkg",
        {
            "__init__.py": "from pkg import subpkg\nfrom pkg.subpkg import mod",
            "subpkg/__init__.py": "a = 0",
            "subpkg/mod.py": "b = 0",
        },
    ) as tmp_package:
        pkg = inspect("pkg", filepath=tmp_package.path / "__init__.py")
    assert "subpkg" not in pkg.members
    assert "mod" in pkg.members
    assert pkg["mod"].is_alias
    assert pkg["mod"].target_path == "pkg.subpkg.mod"
    clear_sys_modules("pkg")


def test_inspecting_objects_from_private_builtin_stdlib_moduless() -> None:
    """Inspect objects from private built-in modules in the standard library."""
    ast = inspect("ast")
    assert "Assign" in ast.members
    assert not ast["Assign"].is_alias

    ast = inspect("_ast")
    assert "Assign" in ast.members
    assert not ast["Assign"].is_alias


def test_inspecting_partials_as_functions() -> None:
    """Assert partials are correctly inspected as functions."""
    with temporary_inspected_module(
        """
        from functools import partial
        def func(a: int, b: int) -> int: pass
        partial_func = partial(func, 1)
        partial_func.__module__ = __name__
        """,
    ) as module:
        partial_func = module["partial_func"]
        assert partial_func.is_function
        assert partial_func.parameters[0].name == "b"
        assert partial_func.parameters[0].annotation.name == "int"
        assert partial_func.returns.name == "int"


def test_inspecting_class_instance() -> None:
    """Assert class instances are correctly inspected."""
    with temporary_inspected_package(
        "pkg",
        {
            "__init__.py": "",
            "foo.py": "from . import bar\nx = bar.X()",
            "bar.py": "class X: pass",
        },
    ) as tmp_package:
        assert not tmp_package["foo.x"].is_alias


def test_inheriting_self_from_parent_class() -> None:
    """Inspect self only once when inheriting it from parent class."""
    with temporary_inspected_module(
        """
        class A: ...
        class B(A): ...

        A.B = B
        """,
    ) as module:
        assert "B" in module["A"].members
        assert "B" in module["B"].all_members
        # Continue indefinitely.
        assert "B" in module["A.B"].all_members
        assert "B" in module["B.B"].all_members
        assert "B" in module["A.B.B"].all_members
        assert "B" in module["B.B.B"].all_members
        # All resolve to A.B.
        assert module["A.B.B"].final_target is module["A.B"]
        assert module["B.B.B"].final_target is module["A.B"]
        assert module["A.B.B.B"].final_target is module["A.B"]
        assert module["B.B.B.B"].final_target is module["A.B"]


# YORE: EOL 3.12: Remove block.
# YORE: EOL 3.11: Remove line.
@pytest.mark.skipif(sys.version_info < (3, 12), reason="Python less than 3.12 does not have PEP 695 generics")
def test_inspecting_pep695_generics_without_defaults() -> None:  # pragma: no cover
    """Assert PEP 695 generics are correctly inspected."""
    with temporary_inspected_module(
        """
        class Class[X: Exception]: pass
        def func[**P, T, *R](arg: T, *args: P.args, **kwargs: P.kwargs) -> tuple[*R]: pass
        type TA[T: (int, str)] = dict[str, T]
        """,
    ) as module:
        class_ = module["Class"]
        assert class_.is_class
        assert class_.type_parameters[0].name == "X"
        assert class_.type_parameters[0].kind == TypeParameterKind.type_var
        assert class_.type_parameters[0].bound.name == "Exception"
        assert not class_.type_parameters[0].constraints
        assert class_.type_parameters[0].default is None

        func = module["func"]
        assert func.is_function
        assert func.type_parameters[0].name == "P"
        assert func.type_parameters[0].kind == TypeParameterKind.param_spec
        assert func.type_parameters[0].bound is None
        assert not func.type_parameters[0].constraints
        assert func.type_parameters[0].default is None
        assert func.type_parameters[1].name == "T"
        assert func.type_parameters[1].kind == TypeParameterKind.type_var
        assert func.type_parameters[1].bound is None
        assert not func.type_parameters[1].constraints
        assert func.type_parameters[1].default is None
        assert func.type_parameters[2].name == "R"
        assert func.type_parameters[2].kind == TypeParameterKind.type_var_tuple
        assert func.type_parameters[2].bound is None
        assert not func.type_parameters[2].constraints
        assert func.type_parameters[2].default is None

        type_alias = module["TA"]
        assert type_alias.is_type_alias
        assert type_alias.type_parameters[0].name == "T"
        assert type_alias.type_parameters[0].kind == TypeParameterKind.type_var
        assert type_alias.type_parameters[0].bound is None
        assert type_alias.type_parameters[0].constraints[0].name == "int"
        assert type_alias.type_parameters[0].constraints[1].name == "str"
        assert type_alias.type_parameters[0].default is None
        assert isinstance(type_alias.value, Expr)
        assert str(type_alias.value) == "dict[str, T]"


# YORE: EOL 3.12: Remove line.
@pytest.mark.skipif(sys.version_info < (3, 13), reason="Python less than 3.13 does not have defaults in PEP 695 generics")  # fmt: skip
def test_inspecting_pep695_generics() -> None:  # pragma: no cover
    """Assert PEP 695 generics are correctly inspected."""
    with temporary_inspected_module(
        """
        class Class[X: Exception = OSError]: pass
        def func[**P, T, *R](arg: T, *args: P.args, **kwargs: P.kwargs) -> tuple[*R]: pass
        type TA[T: (int, str) = str] = dict[str, T]
        """,
    ) as module:
        class_ = module["Class"]
        assert class_.is_class
        assert class_.type_parameters[0].name == "X"
        assert class_.type_parameters[0].kind == TypeParameterKind.type_var
        assert class_.type_parameters[0].bound.name == "Exception"
        assert not class_.type_parameters[0].constraints
        assert class_.type_parameters[0].default.name == "OSError"

        func = module["func"]
        assert func.is_function
        assert func.type_parameters[0].name == "P"
        assert func.type_parameters[0].kind == TypeParameterKind.param_spec
        assert func.type_parameters[0].bound is None
        assert not func.type_parameters[0].constraints
        assert func.type_parameters[0].default is None
        assert func.type_parameters[1].name == "T"
        assert func.type_parameters[1].kind == TypeParameterKind.type_var
        assert func.type_parameters[1].bound is None
        assert not func.type_parameters[1].constraints
        assert func.type_parameters[1].default is None
        assert func.type_parameters[2].name == "R"
        assert func.type_parameters[2].kind == TypeParameterKind.type_var_tuple
        assert func.type_parameters[2].bound is None
        assert not func.type_parameters[2].constraints
        assert func.type_parameters[2].default is None

        type_alias = module["TA"]
        assert type_alias.is_type_alias
        assert type_alias.type_parameters[0].name == "T"
        assert type_alias.type_parameters[0].kind == TypeParameterKind.type_var
        assert type_alias.type_parameters[0].bound is None
        assert type_alias.type_parameters[0].constraints[0].name == "int"
        assert type_alias.type_parameters[0].constraints[1].name == "str"
        assert type_alias.type_parameters[0].default.name == "str"
        assert isinstance(type_alias.value, Expr)
        assert str(type_alias.value) == "dict[str, T]"


def test_inspector_and_runtime_node_edge_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test Inspector and ObjectNode edge cases (docstrings, linenos, dynamic submodules, descriptors, annotations)."""
    import inspect as py_inspect  # noqa: PLC0415
    import types  # noqa: PLC0415
    import typing  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415
    from tempfile import gettempdir  # noqa: PLC0415

    from griffe._internal.agents import inspector as inspector_mod  # noqa: PLC0415
    from griffe._internal.agents.nodes.runtime import ObjectNode  # noqa: PLC0415
    from griffe._internal.collections import LinesCollection  # noqa: PLC0415
    from griffe._internal.enumerations import ObjectKind  # noqa: PLC0415
    from griffe._internal.extensions.base import Extensions  # noqa: PLC0415
    from griffe._internal.helpers import _TMPDIR_PREFIX  # noqa: PLC0415
    from griffe._internal.models import Module  # noqa: PLC0415
    from tests.helpers import clear_sys_modules  # noqa: PLC0415

    # Test clear_sys_modules(None)
    fake_tmp_prefix = str(Path(gettempdir()) / f"{_TMPDIR_PREFIX}fake_mod")
    fake_m1 = types.ModuleType("_fake_tmp_mod_1")
    fake_m1.__file__ = f"{fake_tmp_prefix}/mod.py"
    fake_m2 = types.ModuleType("_fake_tmp_mod_2")
    fake_m2.__path__ = [f"{fake_tmp_prefix}/pkg"]
    sys.modules["_fake_tmp_mod_1"] = fake_m1
    sys.modules["_fake_tmp_mod_2"] = fake_m2
    clear_sys_modules(None)
    assert "_fake_tmp_mod_1" not in sys.modules
    assert "_fake_tmp_mod_2" not in sys.modules

    # ObjectNode unwrap exception, repr, path, module error
    class BadUnwrap:
        @property
        def __wrapped__(self) -> object:
            raise RuntimeError("unwrap error")

    node_bad_unwrap = ObjectNode(BadUnwrap(), "bad")
    assert repr(node_bad_unwrap) == "ObjectNode(name='bad')"
    assert node_bad_unwrap.path == "bad"
    with pytest.raises(ValueError, match="does not have a parent module"):
        _ = node_bad_unwrap.module

    # ObjectNode.module_path edge cases
    mod_root = types.ModuleType("root_m")
    mod_root.__name__ = "root_m"
    mod_node = ObjectNode(mod_root, "root_m")

    # 1. Object without __module__ where getmodule raises ValueError
    node_val_err = ObjectNode(42, "num", parent=mod_node)
    monkeypatch.setattr(py_inspect, "getmodule", lambda _o: (_ for _ in ()).throw(ValueError("bad")))
    assert node_val_err.module_path is None
    monkeypatch.undo()

    # 2. Object without __module__ where getmodule returns None and parent module has __spec__.name vs only __name__
    mod_with_spec = types.ModuleType("spec_m")
    mod_with_spec.__spec__ = types.SimpleNamespace(name="spec_m_name")  # ty:ignore[invalid-assignment]
    node_spec_parent = ObjectNode(mod_with_spec, "spec_m")
    monkeypatch.setattr(py_inspect, "getmodule", lambda _o: None)
    assert ObjectNode(object(), "child", parent=node_spec_parent).module_path == "spec_m_name"

    mod_no_spec = types.ModuleType("no_spec_m")
    delattr(mod_no_spec, "__spec__")
    node_no_spec_parent = ObjectNode(mod_no_spec, "no_spec_m")
    assert ObjectNode(object(), "child", parent=node_no_spec_parent).module_path == "no_spec_m"
    monkeypatch.undo()

    # 3. Object with __module__ set to a ModuleType or an invalid int
    class ModAsModule:
        __module__ = mod_root  # ty:ignore[invalid-assignment]

    class ModAsInt:
        __module__ = 123  # ty:ignore[invalid-assignment]

    assert ObjectNode(ModAsModule, "ModAsModule", parent=mod_node).module_path == "root_m"
    assert ObjectNode(ModAsInt, "ModAsInt", parent=mod_node).module_path is None

    # ObjectNode kind / descriptor / method / staticmethod / classmethod edge cases
    class WithMethods:
        def regular_method(self) -> None:
            return None

        @staticmethod
        def sm() -> None:
            return None

        @classmethod
        def cm(cls) -> None:
            return None

    WithMethods().regular_method()
    WithMethods.sm()
    WithMethods.cm()

    cls_node = ObjectNode(WithMethods, "WithMethods", parent=mod_node)
    assert ObjectNode(WithMethods.regular_method, "regular_method", parent=cls_node).kind is ObjectKind.METHOD
    assert ObjectNode(WithMethods.sm, "sm", parent=cls_node).kind is ObjectKind.STATICMETHOD
    assert ObjectNode(WithMethods.cm, "cm", parent=cls_node).kind is ObjectKind.CLASSMETHOD
    assert ObjectNode(int.__dict__["real"], "real", parent=cls_node).kind is ObjectKind.GETSET_DESCRIPTOR
    assert ObjectNode(str.split, "split", parent=cls_node).kind is ObjectKind.METHOD_DESCRIPTOR
    assert ObjectNode([].append, "append", parent=cls_node).kind is ObjectKind.BUILTIN_METHOD
    assert not ObjectNode(WithMethods.sm, "sm", parent=None).is_staticmethod
    assert not ObjectNode(WithMethods.cm, "cm", parent=None).is_classmethod

    # Parent whose obj has no __dict__ (e.g. int instance forced as class parent)
    no_dict_parent = ObjectNode(1, "one")
    assert not ObjectNode(WithMethods.sm, "sm", parent=no_dict_parent).is_staticmethod
    assert not ObjectNode(WithMethods.cm, "cm", parent=no_dict_parent).is_classmethod

    # alias_target_path edge cases
    assert node_bad_unwrap.alias_target_path is None  # parent is None
    assert ObjectNode(ModAsInt, "ModAsInt", parent=mod_node).alias_target_path is None  # child_module_path is None
    bad_parent_mod = ObjectNode(ModAsInt, "BadParent")
    assert (
        ObjectNode(WithMethods, "WithMethods", parent=bad_parent_mod).alias_target_path is None
    )  # parent_module_path is None
    os_mod = types.ModuleType("os")
    posix_mod = types.ModuleType("posix")
    os_node = ObjectNode(os_mod, "os")
    assert ObjectNode(posix_mod, "posix", parent=os_node).alias_target_path is None  # cyclic relationship
    other_sub = types.ModuleType("other_pkg.sub")
    assert ObjectNode(other_sub, "sub", parent=mod_node).alias_target_path == "other_pkg.sub"

    # Inspector._get_docstring and _get_linenos edge cases
    class BadDoc:
        @property
        def __doc__(self) -> str:
            raise RuntimeError("doc error")

    class NonStrDoc:
        __doc__ = 12345  # ty:ignore[invalid-assignment]

    lc = LinesCollection()
    fpath = Path("fake_insp.py")
    lc[fpath] = ["def f():\n", "    pass\n"]
    insp = inspector_mod.Inspector("fake_insp", filepath=fpath, extensions=Extensions(), lines_collection=lc)
    assert insp._get_docstring(ObjectNode(BadDoc(), "bd")) is None
    assert insp._get_docstring(ObjectNode(NonStrDoc(), "nsd")) is None
    assert insp._get_linenos(ObjectNode(42, "num")) == (None, None)
    assert insp._get_linenos(ObjectNode(WithMethods.regular_method, "regular_method"))[0] is not None

    # Inspector.get_module with parent and __init__.py filepath, and generic_inspect with in-memory submodule
    parent_griffe_mod = Module("pkg_p", filepath=fpath.parent / "__init__.py")
    sub_insp = inspector_mod.Inspector(
        "sub_m",
        filepath=fpath.parent / "pkg_p" / "sub_m" / "__init__.py",
        extensions=Extensions(),
        parent=parent_griffe_mod,
    )
    in_mem_mod = types.ModuleType("pkg_p.sub_m")
    in_mem_child = types.ModuleType("pkg_p.sub_m.mem_child")
    # Ensure in_mem_child has no __file__, and another child has __file__
    disk_child = types.ModuleType("pkg_p.sub_m.disk_child")
    disk_child.__file__ = "disk_child.py"
    in_mem_mod.mem_child = in_mem_child  # ty:ignore[unresolved-attribute]
    in_mem_mod.disk_child = disk_child  # ty:ignore[unresolved-attribute]

    class BadRepr:
        def __repr__(self) -> str:
            raise RuntimeError("bad repr")

    import asyncio  # noqa: PLC0415

    my_coro = asyncio.sleep
    in_mem_mod.bad_repr = BadRepr()  # ty:ignore[unresolved-attribute]
    in_mem_mod.my_coro = my_coro  # ty:ignore[unresolved-attribute]
    in_mem_mod.b_func = len  # ty:ignore[unresolved-attribute]
    in_mem_mod.__all__ = ["my_coro"]  # ty:ignore[unresolved-attribute]

    class ClsWithSpecials:
        sm = staticmethod(lambda: None)
        cm = classmethod(lambda cls: None)
        md = str.split
        bm = [].append
        gs = int.__dict__["real"]

    ClsWithSpecials.__module__ = "pkg_p.sub_m"
    in_mem_mod.ClsWithSpecials = ClsWithSpecials  # ty:ignore[unresolved-attribute]

    monkeypatch.setattr(inspector_mod, "dynamic_import", lambda *_a, **_kw: in_mem_mod)
    res_mod = sub_insp.get_module(import_paths=[])
    sub_insp.inspect_builtin_function(ObjectNode(len, "b_func_direct", parent=mod_node))
    sub_insp.inspect_builtin_method(ObjectNode([].append, "b_meth_direct", parent=cls_node))
    sub_insp.inspect_method_descriptor(ObjectNode(str.split, "m_desc_direct", parent=cls_node))
    sub_insp.inspect_staticmethod(ObjectNode(WithMethods.sm, "sm_direct", parent=cls_node))
    sub_insp.inspect_classmethod(ObjectNode(WithMethods.cm, "cm_direct", parent=cls_node))
    sub_insp.inspect_method(ObjectNode(WithMethods().regular_method, "m_direct", parent=cls_node))
    sub_insp.inspect_coroutine(ObjectNode(my_coro, "coro_direct", parent=mod_node))
    assert "mem_child" in res_mod.members
    assert "disk_child" not in res_mod.members
    assert res_mod["bad_repr"].value is None
    assert "async" in res_mod["coro_direct"].labels
    assert "builtin" in res_mod["b_func_direct"].labels
    assert "builtin" in res_mod["b_meth_direct"].labels
    assert "method descriptor" in res_mod["m_desc_direct"].labels
    assert res_mod.exports == ["my_coro"]
    monkeypatch.undo()

    # _convert_object_to_annotation and _convert_type_to_annotation edge cases
    class NoNameRepr:
        def __repr__(self) -> str:
            return "int"

    class BadSyntaxRepr:
        def __repr__(self) -> str:
            return "def invalid syntax"

    assert inspector_mod._convert_object_to_annotation("int", parent=res_mod) is not None
    assert inspector_mod._convert_object_to_annotation(NoNameRepr(), parent=res_mod) is not None
    bad_syn = BadSyntaxRepr()
    assert inspector_mod._convert_object_to_annotation(bad_syn, parent=res_mod) is bad_syn
    assert inspector_mod._convert_type_to_annotation(int | str, parent=res_mod) is not None
    assert inspector_mod._convert_type_to_annotation(list[int], parent=res_mod) is not None

    # ObjectNode.kind for type_alias, inspect_type_alias, and _convert_type_parameters
    ta_kind_node = ObjectNode(object(), "ta_kind", parent=mod_node)
    ta_kind_node.__dict__["is_type_alias"] = True
    assert ta_kind_node.kind is ObjectKind.TYPE_ALIAS

    class FakeTypeParam:
        def __init__(
            self,
            name: str,
            bound: object = None,
            constraints: tuple[object, ...] = (),
            default: object = None,
            *,
            has_def: bool = False,
        ) -> None:
            self.__name__ = name
            self.__bound__ = bound
            self.__constraints__ = constraints
            self.__default__ = default
            self._has_def = has_def

        def has_default(self) -> bool:
            return self._has_def

    class FakeTypeAliasObj:
        __value__ = list[int]
        __type_params__ = (
            FakeTypeParam("T1", bound=int, default=str, has_def=True),
            FakeTypeParam("T2", constraints=(int, str), has_def=False),
        )

    monkeypatch.setitem(inspector_mod._type_parameter_kind_map, FakeTypeParam, TypeParameterKind.type_var)
    sub_insp.inspect_type_alias(ObjectNode(FakeTypeAliasObj(), "FakeTA", parent=mod_node))
    assert "FakeTA" in res_mod.members
    assert len(res_mod["FakeTA"].type_parameters) == 2

    orig_get_origin = typing.get_origin
    monkeypatch.setattr(typing, "get_origin", lambda o: "bad_origin" if o == list[int] else orig_get_origin(o))
    monkeypatch.setattr(
        inspector_mod, "_convert_object_to_annotation", lambda o, **_kw: None if o == "bad_origin" else "int"
    )
    assert inspector_mod._convert_type_to_annotation(list[int], parent=res_mod) is None
