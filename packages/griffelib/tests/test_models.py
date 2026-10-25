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

# Tests for the `dataclasses` module.

from __future__ import annotations

import sys
from copy import deepcopy
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from griffe import (
    Alias,
    AliasResolutionError,
    Attribute,
    Class,
    Docstring,
    Function,
    GriffeLoader,
    Module,
    NameResolutionError,
    Parameter,
    ParameterKind,
    Parameters,
    TypeParameter,
    TypeParameterKind,
    TypeParameters,
    module_vtree,
    temporary_inspected_module,
    temporary_pypackage,
    temporary_visited_module,
    temporary_visited_package,
)


def test_lazy_alias_resolution_error_message(tmp_path: Path) -> None:
    """Build detailed alias-resolution messages only when rendered."""
    module = Module("module", filepath=tmp_path / "module.py")
    alias = Alias("alias", "missing.target", parent=module)
    summary = "Could not resolve alias module.alias pointing at missing.target"
    expected = f"Could not resolve alias module.alias pointing at missing.target (in {module.relative_filepath}:None)"

    error = AliasResolutionError(alias)
    assert error.args == (summary,)
    assert error._detailed_message is None
    assert str(error) == expected
    assert error.args == (summary,)
    assert error._detailed_message == expected


def test_submodule_exports() -> None:
    """Check that a module is exported depending on whether it was also imported."""
    root = Module("root")
    sub = Module("sub")
    private = Attribute("_private")
    root["sub"] = sub
    root["_private"] = private

    assert not sub.is_wildcard_exposed
    root.imports["sub"] = "root.sub"
    assert sub.is_wildcard_exposed

    assert not private.is_wildcard_exposed
    root.exports = ["_private"]
    assert private.is_wildcard_exposed


def test_has_docstrings() -> None:
    """Assert the `.has_docstrings` method is recursive."""
    with temporary_visited_module("class A:\n    '''Hello.'''") as module:
        assert module.has_docstrings


def test_has_docstrings_submodules() -> None:
    """Assert the `.has_docstrings` method descends into submodules."""
    module = module_vtree("a.b.c.d")
    module["b.c.d"].docstring = Docstring("Hello.")
    assert module.has_docstrings


def test_handle_aliases_chain_in_has_docstrings() -> None:
    """Assert the `.has_docstrings` method can handle aliases chains in members."""
    with temporary_pypackage("package", ["mod_a.py", "mod_b.py"]) as tmp_package:
        mod_a = tmp_package.path / "mod_a.py"
        mod_b = tmp_package.path / "mod_b.py"
        mod_a.write_text("from .mod_b import someobj", encoding="utf8")
        mod_b.write_text("from somelib import someobj", encoding="utf8")

        loader = GriffeLoader(search_paths=[tmp_package.tmpdir])
        package = loader.load(tmp_package.name)
        assert not package.has_docstrings
        loader.resolve_aliases(implicit=True)
        assert not package.has_docstrings


def test_has_docstrings_does_not_trigger_alias_resolution() -> None:
    """Assert the `.has_docstrings` method does not trigger alias resolution."""
    with temporary_pypackage("package", ["mod_a.py", "mod_b.py"]) as tmp_package:
        mod_a = tmp_package.path / "mod_a.py"
        mod_b = tmp_package.path / "mod_b.py"
        mod_a.write_text("from .mod_b import someobj", encoding="utf8")
        mod_b.write_text("from somelib import someobj", encoding="utf8")

        loader = GriffeLoader(search_paths=[tmp_package.tmpdir])
        package = loader.load(tmp_package.name)
        assert not package.has_docstrings
        assert not package["mod_a.someobj"].resolved


def test_deepcopy() -> None:
    """Assert we can deep-copy object trees."""
    loader = GriffeLoader()
    mod = loader.load("griffe")

    deepcopy(mod)
    deepcopy(mod.as_dict())


def test_dataclass_properties_and_class_variables() -> None:
    """Don't return properties or class variables as parameters of dataclasses."""
    code = """
        from dataclasses import dataclass
        from functools import cached_property
        from typing import ClassVar

        @dataclass
        class Point:
            x: float
            y: float

            # These definitions create class variables.
            r: ClassVar[float]
            s: float = 3
            t: ClassVar[float] = 3

            @property
            def a(self):
                return 0

            @cached_property
            def b(self):
                return 0
    """
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        params = module["Point"].parameters
        assert [p.name for p in params] == ["self", "x", "y", "s"]


@pytest.mark.parametrize(
    "code",
    [
        """
        @dataclass
        class Dataclass:
            x: float
            y: float = field(kw_only=True)

        class Class:
            def __init__(self, x: float, *, y: float): ...
        """,
        """
        @dataclass
        class Dataclass:
            x: float = field(kw_only=True)
            y: float

        class Class:
            def __init__(self, y: float, *, x: float): ...
        """,
        """
        @dataclass
        class Dataclass:
            x: float
            _: KW_ONLY
            y: float

        class Class:
            def __init__(self, x: float, *, y: float): ...
        """,
        """
        @dataclass
        class Dataclass:
            _: KW_ONLY
            x: float
            y: float

        class Class:
            def __init__(self, *, x: float, y: float): ...
        """,
        """
        @dataclass(kw_only=True)
        class Dataclass:
            x: float
            y: float

        class Class:
            def __init__(self, *, x: float, y: float): ...
        """,
    ],
)
def test_dataclass_parameter_kinds(code: str) -> None:
    """Check dataclass and equivalent non-dataclass parameters.

    The parameter kinds for each pair should be the same.

    Parameters:
        code: Python code to visit.
    """
    code = f"from dataclasses import dataclass, field, KW_ONLY\n\n{dedent(code)}"
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        for dataclass_param, regular_param in zip(
            module["Dataclass"].parameters,
            module["Class"].parameters,
            strict=False,
        ):
            assert dataclass_param == regular_param


def test_regular_class_inheriting_dataclass_dont_get_its_own_params() -> None:
    """A regular class inheriting from a dataclass don't have its attributes added to `__init__`."""
    code = """
        from dataclasses import dataclass

        @dataclass
        class Base:
            a: int
            b: str

        @dataclass
        class Derived1(Base):
            c: float

        class Derived2(Base):
            d: float
    """
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        params1 = module["Derived1"].parameters
        params2 = module["Derived2"].parameters
        assert [p.name for p in params1] == ["self", "a", "b", "c"]
        assert [p.name for p in params2] == ["self", "a", "b"]


def test_regular_class_inheriting_dataclass_is_labelled_dataclass() -> None:
    """A regular class inheriting from a dataclass is labelled as a dataclass too."""
    code = """
        from dataclasses import dataclass

        @dataclass
        class Base:
            pass

        class Derived(Base):
            pass
    """
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        obj = module["Derived"]
        assert "dataclass" in obj.labels


def test_fields_with_init_false() -> None:
    """Fields marked with `init=False` are not added to the `__init__` method."""
    code = """
        from dataclasses import dataclass, field

        @dataclass
        class PointA:
            x: float
            y: float
            z: float = field(init=False)

        @dataclass(init=False)
        class PointB:
            x: float
            y: float

        @dataclass(init=False)
        class PointC:
            x: float
            y: float = field(init=True)  # `init=True` has no effect.
    """
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        params_a = module["PointA"].parameters
        params_b = module["PointB"].parameters
        params_c = module["PointC"].parameters

        assert "z" not in params_a
        assert "x" not in params_b
        assert "y" not in params_b
        assert "x" not in params_c
        assert "y" not in params_c


def test_parameters_are_reorderd_to_match_their_kind() -> None:
    """Keyword-only parameters in base class are pushed back to the end of the signature."""
    code = """
        from dataclasses import dataclass

        @dataclass(kw_only=True)
        class Base:
            a: int
            b: str

        @dataclass
        class Reordered(Base):
            b: float
            c: float
    """
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        params_base = module["Base"].parameters
        params_reordered = module["Reordered"].parameters
        assert [p.name for p in params_base] == ["self", "a", "b"]
        assert [p.name for p in params_reordered] == ["self", "b", "c", "a"]
        assert str(params_reordered["b"].annotation) == "float"


def test_parameters_annotated_as_initvar() -> None:
    """Don't return InitVar annotated fields as class members.

    But if __init__ is defined, InitVar has no effect.
    """
    code = """
    from dataclasses import dataclass, InitVar

    @dataclass
    class PointA:
        x: float
        y: float
        z: InitVar[float]

    @dataclass
    class PointB:
        x: float
        y: float
        z: InitVar[float]

        def __init__(self, r: float): ...
    """

    with temporary_visited_package("package", {"__init__.py": code}) as module:
        point_a = module["PointA"]
        assert [p.name for p in point_a.parameters] == ["self", "x", "y", "z"]
        assert list(point_a.members) == ["x", "y", "__init__"]

        point_b = module["PointB"]
        assert [p.name for p in point_b.parameters] == ["self", "r"]
        assert list(point_b.members) == ["x", "y", "z", "__init__"]


def test_visited_module_source() -> None:
    """Check the source property of a module."""
    code = "print('hello')\nprint('world')"
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        assert module.source == code


def test_visited_class_source() -> None:
    """Check the source property of a class."""
    code = """
    class A:
        def __init__(self, x: int):
            self.x = x
    """
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        assert module["A"].source == dedent(code).strip()


def test_visited_object_source_with_missing_line_number() -> None:
    """Check the source property of an object with missing line number."""
    code = """
    class A:
        def __init__(self, x: int):
            self.x = x
    """
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        module["A"].endlineno = None
        assert not module["A"].source
        module["A"].endlineno = 3
        module["A"].lineno = None
        assert not module["A"].source


def test_inspected_module_source() -> None:
    """Check the source property of a module."""
    code = "print('hello')\nprint('world')"
    with temporary_inspected_module(code) as module:
        assert module.source == code


def test_inspected_class_source() -> None:
    """Check the source property of a class."""
    code = """
    class A:
        def __init__(self, x: int):
            self.x = x
    """
    with temporary_inspected_module(code) as module:
        assert module["A"].source == dedent(code).strip()


def test_inspected_object_source_with_missing_line_number() -> None:
    """Check the source property of an object with missing line number."""
    code = """
    class A:
        def __init__(self, x: int):
            self.x = x
    """
    with temporary_inspected_module(code) as module:
        module["A"].endlineno = None
        assert not module["A"].source
        module["A"].endlineno = 3
        module["A"].lineno = None
        assert not module["A"].source


def test_dataclass_parameter_docstrings() -> None:
    """Class parameters should have a docstring attribute."""
    code = """
    from dataclasses import dataclass, InitVar

    @dataclass
    class Base:
        a: int
        "Parameter a"
        b: InitVar[int] = 3
        "Parameter b"

    @dataclass
    class Derived(Base):
        c: float
        d: InitVar[float]
        "Parameter d"
    """

    with temporary_visited_package("package", {"__init__.py": code}) as module:
        base = module["Base"]
        param_self = base.parameters[0]
        param_a = base.parameters[1]
        param_b = base.parameters[2]
        assert param_self.docstring is None
        assert param_a.docstring.value == "Parameter a"
        assert param_b.docstring.value == "Parameter b"

        derived = module["Derived"]
        param_self = derived.parameters[0]
        param_a = derived.parameters[1]
        param_b = derived.parameters[2]
        param_c = derived.parameters[3]
        param_d = derived.parameters[4]
        assert param_self.docstring is None
        assert param_a.docstring.value == "Parameter a"
        assert param_b.docstring.value == "Parameter b"
        assert param_c.docstring is None
        assert param_d.docstring.value == "Parameter d"


def test_attributes_that_have_no_annotations() -> None:
    """Dataclass attributes that have no annotatations are not parameters."""
    code = """
        from dataclasses import dataclass, field

        @dataclass
        class Base:
            a: int
            b: str = field(init=False)
            c = 3  # Class attribute.

        @dataclass
        class Derived(Base):
            a = 1  # No effect on the parameter status of `a`.
            b = "b"  # Inherited non-parameter.
            d: float = 4
    """
    with temporary_visited_package("package", {"__init__.py": code}) as module:
        base_params = [p.name for p in module["Base"].parameters]
        derived_params = [p.name for p in module["Derived"].parameters]
        assert base_params == ["self", "a"]
        assert derived_params == ["self", "a", "d"]


def test_name_resolution() -> None:
    """Name are correctly resolved in the scope of an object."""
    code = """
    module_attribute = 0

    class Class:
        import imported

        class_attribute = 0

        def __init__(self):
            self.instance_attribute = 0

        def method(self):
            local_variable = 0
    """
    with temporary_visited_module(code) as module:
        assert module.resolve("module_attribute") == "module.module_attribute"
        assert module.resolve("Class") == "module.Class"

        assert module["module_attribute"].resolve("Class") == "module.Class"
        with pytest.raises(NameResolutionError):
            module["module_attribute"].resolve("class_attribute")

        assert module["Class"].resolve("module_attribute") == "module.module_attribute"
        assert module["Class"].resolve("imported") == "imported"
        assert module["Class"].resolve("class_attribute") == "module.Class.class_attribute"
        assert module["Class"].resolve("instance_attribute") == "module.Class.instance_attribute"
        assert module["Class"].resolve("method") == "module.Class.method"

        assert module["Class.class_attribute"].resolve("module_attribute") == "module.module_attribute"
        assert module["Class.class_attribute"].resolve("Class") == "module.Class"
        assert module["Class.class_attribute"].resolve("imported") == "imported"
        assert module["Class.class_attribute"].resolve("instance_attribute") == "module.Class.instance_attribute"
        assert module["Class.class_attribute"].resolve("method") == "module.Class.method"

        assert module["Class.instance_attribute"].resolve("module_attribute") == "module.module_attribute"
        assert module["Class.instance_attribute"].resolve("Class") == "module.Class"
        assert module["Class.instance_attribute"].resolve("imported") == "imported"
        assert module["Class.instance_attribute"].resolve("class_attribute") == "module.Class.class_attribute"
        assert module["Class.instance_attribute"].resolve("method") == "module.Class.method"

        assert module["Class.method"].resolve("module_attribute") == "module.module_attribute"
        assert module["Class.method"].resolve("Class") == "module.Class"
        assert module["Class.method"].resolve("imported") == "imported"
        assert module["Class.method"].resolve("class_attribute") == "module.Class.class_attribute"
        assert module["Class.method"].resolve("instance_attribute") == "module.Class.instance_attribute"


def test_set_parameters() -> None:
    """We can set parameters."""
    parameters = Parameters()
    # Does not exist yet.
    parameters["x"] = Parameter(name="x")
    assert "x" in parameters
    # Already exists, by name.
    parameters["x"] = Parameter(name="x")
    assert "x" in parameters
    assert len(parameters) == 1
    # Already exists, by index.
    parameters[0] = Parameter(name="y")
    assert "y" in parameters
    assert len(parameters) == 1


def test_delete_parameters() -> None:
    """We can delete parameters."""
    parameters = Parameters()
    # By name.
    parameters["x"] = Parameter(name="x")
    del parameters["x"]
    assert "x" not in parameters
    assert len(parameters) == 0
    # By index.
    parameters["x"] = Parameter(name="x")
    del parameters[0]
    assert "x" not in parameters
    assert len(parameters) == 0


def test_not_resolving_attribute_value_to_itself() -> None:
    """Attribute values with same name don't resolve to themselves."""
    with temporary_visited_module(
        """
        class A:
            def __init__(self):
                x = "something"
                self.x = x
        """,
    ) as module:
        assert module["A.x"].value.canonical_path == "x"  # Not `module.A.x`.
        assert module["A.x"].value.reference_path is None


def test_resolving_never_raises_alias_errors() -> None:
    """Resolving never raises alias errors."""
    with temporary_visited_package(
        "package",
        {
            "__init__.py": """
                from package.mod import pd

                class A:
                    def __init__(self):
                        pass
            """,
            "mod.py": "import pandas as pd",
        },
    ) as module:
        assert module["A.__init__"].resolve("pd") == "package.mod.pd"


def test_building_function_and_class_signatures() -> None:
    """Test the construction of a class/function signature."""
    # Test simple function signatures.
    simple_params = Parameters(
        Parameter("x", annotation="int"),
        Parameter("y", annotation="int", default="0"),
    )
    simple_func = Function("simple_function", parameters=simple_params, returns="int")
    assert simple_func.signature() == "simple_function(x: int, y: int = 0) -> int"

    # Test class signatures.
    init = Function("__init__", parameters=simple_params, returns="None")
    cls = Class("TestClass")
    cls.set_member("__init__", init)
    assert cls.signature() == "TestClass(x: int, y: int = 0)"

    # Create a more complex function with various parameter types.
    params = Parameters(
        Parameter("a", kind=ParameterKind.positional_only),
        Parameter("b", kind=ParameterKind.positional_only, annotation="int", default="0"),
        Parameter("c", kind=ParameterKind.positional_or_keyword),
        Parameter("d", kind=ParameterKind.positional_or_keyword, annotation="str", default="''"),
        Parameter("args", kind=ParameterKind.var_positional),
        Parameter("e", kind=ParameterKind.keyword_only),
        Parameter("f", kind=ParameterKind.keyword_only, annotation="bool", default="False"),
        Parameter("kwargs", kind=ParameterKind.var_keyword),
    )

    func = Function("test_function", parameters=params, returns="None")
    expected = "test_function(a, b: int = 0, /, c, d: str = '', *args, e, f: bool = False, **kwargs) -> None"
    assert func.signature() == expected


def test_set_type_parameters() -> None:
    """We can set type parameters."""
    type_parameters = TypeParameters()
    # Does not exist yet.
    type_parameters["x"] = TypeParameter(name="x", kind=TypeParameterKind.type_var)
    assert "x" in type_parameters
    # Already exists, by name.
    type_parameters["x"] = TypeParameter(name="x", kind=TypeParameterKind.type_var)
    assert "x" in type_parameters
    assert len(type_parameters) == 1
    # Already exists, by name, with different kind.
    type_parameters["x"] = TypeParameter(name="x", kind=TypeParameterKind.param_spec)
    assert "x" in type_parameters
    assert len(type_parameters) == 1
    # Already exists, by index.
    type_parameters[0] = TypeParameter(name="y", kind=TypeParameterKind.type_var)
    assert "y" in type_parameters
    assert len(type_parameters) == 1


def test_delete_type_parameters() -> None:
    """We can delete type parameters."""
    type_parameters = TypeParameters()
    # By name.
    type_parameters["x"] = TypeParameter(name="x", kind=TypeParameterKind.type_var)
    del type_parameters["x"]
    assert "x" not in type_parameters
    assert len(type_parameters) == 0
    # By index.
    type_parameters["x"] = TypeParameter(name="x", kind=TypeParameterKind.type_var)
    del type_parameters[0]
    assert "x" not in type_parameters
    assert len(type_parameters) == 0


# YORE: EOL 3.11: Remove line.
@pytest.mark.skipif(sys.version_info < (3, 12), reason="Python less than 3.12 does not have PEP 695 generics")
def test_annotation_resolution() -> None:  # pragma: no cover
    """Names are correctly resolved in the annotation scope of an object."""
    with temporary_visited_module(
        """
        class C[T]:
            class D[T]:
                def func[Y](self, arg1: T, arg2: Y): pass
            def func[Z](arg1: T, arg2: Y): pass
        """,
    ) as module:
        assert module["C.D"].resolve("T") == "module.C.D[T]"

        assert module["C.D.func"].resolve("T") == "module.C.D[T]"
        assert module["C.D.func"].resolve("Y") == "module.C.D.func[Y]"

        assert module["C"].resolve("T") == "module.C[T]"

        assert module["C.func"].resolve("T") == "module.C[T]"
        with pytest.raises(NameResolutionError):
            module["C.func"].resolve("Y")


def test_models_comprehensive_coverage(tmp_path: Path) -> None:
    """Test remaining model methods, properties, alias proxies, and edge cases."""
    from pathlib import Path  # noqa: PLC0415

    from griffe._internal.collections import LinesCollection, ModulesCollection  # noqa: PLC0415
    from griffe._internal.enumerations import Kind, ParameterKind, TypeParameterKind  # noqa: PLC0415
    from griffe._internal.exceptions import (  # noqa: PLC0415
        AliasResolutionError,
        CyclicAliasError,
        NameResolutionError,
    )
    from griffe._internal.expressions import ExprCall, ExprName  # noqa: PLC0415
    from griffe._internal.git import GitInfo  # noqa: PLC0415
    from griffe._internal.models import (  # noqa: PLC0415
        Alias,
        Attribute,
        Class,
        Decorator,
        Docstring,
        Function,
        Module,
        Parameter,
        Parameters,
        TypeAlias,
        TypeParameter,
        TypeParameters,
    )

    # Docstring.source errors and success
    assert Docstring("hello").lines == ["hello"]
    with pytest.raises(ValueError, match="without parent"):
        _ = Docstring("hello").source
    ns_mod = Module("ns", filepath=[tmp_path / "ns1", tmp_path / "ns2"])
    with pytest.raises(ValueError, match="namespace package"):
        _ = Docstring("hello", lineno=1, endlineno=1, parent=ns_mod).source
    reg_mod = Module("reg", filepath=tmp_path / "reg.py")
    with pytest.raises(ValueError, match="without line numbers"):
        _ = Docstring("hello", lineno=None, endlineno=None, parent=reg_mod).source

    # Parameter.__str__, __repr__, __eq__, as_dict
    p1 = Parameter("p", annotation="int", kind=ParameterKind.positional_only, default="1", docstring=Docstring("p doc"))
    p_nokind = Parameter("p", annotation="int", kind=None, default="1")
    assert "[positional-only]" in str(p1)
    assert str(p_nokind) == "p: int = 1"
    assert "Parameter(" in repr(p1)
    assert (p1 == "not_a_param") is False
    assert p1 == Parameter("p", annotation="int", kind=ParameterKind.positional_only, default="1")
    assert "docstring" in p1.as_dict(full=True)

    # Parameters __repr__, KeyError on get/del, ValueError on duplicate add, and add success
    params = Parameters(p1)
    params.add(Parameter("p2"))
    assert len(params) == 2
    assert "Parameters(" in repr(params)
    with pytest.raises(KeyError, match="not found"):
        _ = params["missing"]
    with pytest.raises(KeyError, match="not found"):
        del params["missing"]
    with pytest.raises(ValueError, match="already present"):
        params.add(p1)

    # TypeParameter validation, repr, constraints/bound setters, as_dict, and TypeParameters container
    with pytest.raises(ValueError, match="mutually exclusive"):
        TypeParameter("T", kind=TypeParameterKind.type_var, bound="int", constraints=["int", "str"])
    tp = TypeParameter("T", kind=TypeParameterKind.type_var, constraints=["int", "str"])
    assert "TypeParameter(" in repr(tp)
    assert tp.bound is None
    assert tp.constraints == ("int", "str")
    tp.constraints = None
    assert tp.constraints is None
    tp.bound = "float"
    assert tp.bound == "float"
    assert tp.as_dict()["name"] == "T"

    tps = TypeParameters(tp)
    tps.add(TypeParameter("U", kind=TypeParameterKind.type_var))
    assert len(tps) == 2
    assert "TypeParameters(" in repr(tps)
    assert tps[0] is tp
    assert tps["T"] is tp
    with pytest.raises(KeyError, match="not found"):
        _ = tps["missing"]
    with pytest.raises(KeyError, match="not found"):
        del tps["missing"]
    with pytest.raises(ValueError, match="already present"):
        tps.add(tp)
    assert "missing" not in tps

    # Decorator callable_path with ExprCall and string
    dec_call = Decorator(ExprCall(ExprName("my_dec"), []), lineno=1, endlineno=1)
    assert dec_call.callable_path == "my_dec"
    dec_str = Decorator("str_dec", lineno=1, endlineno=1)
    assert dec_str.callable_path == "str_dec"

    # Object repr, bool, len, git_info, source_link, has_docstrings, is_kind, inherited_members, filter_members
    mc = ModulesCollection()
    lc = LinesCollection()
    repo_dir = tmp_path / "repo"
    pkg_dir = repo_dir / "pkg"
    pkg_dir.mkdir(parents=True)
    init_py = pkg_dir / "__init__.py"
    lc[init_py] = ["def f():\n", "    pass\n"]
    git_info = GitInfo(repository=repo_dir, service="github", remote_url="https://github.com/u/r", commit_hash="abc")

    pkg = Module("pkg", filepath=init_py, lines_collection=lc, modules_collection=mc, git_info=git_info)
    mc["pkg"] = pkg
    fn_doc = Docstring("fn doc", lineno=1, endlineno=1)
    fn = Function("f", lineno=1, endlineno=2, parent=pkg, docstring=fn_doc)
    fn_doc.parent = fn
    assert fn_doc.source == "def f():\n"
    pkg["f"] = fn
    assert repr(fn) == "Function('f', 1, 2)"
    assert bool(fn) is True
    assert len(pkg) == 1
    assert fn.git_info is git_info
    fn.git_info = git_info
    assert fn.source_link is not None
    assert fn.source_link is not None  # cached _source_link branch
    fn.source_link = "https://custom/link"
    assert fn.source_link == "https://custom/link"
    fn.public = True
    fn.deprecated = "dep"
    assert fn.as_dict(full=False)["public"] is True
    assert fn.as_dict(full=False)["deprecated"] == "dep"
    assert fn.as_dict(full=True)["path"] == "pkg.f"

    # source_link when filepath is not relative to repository or lineno is None
    outside_mod = Module("out", filepath=tmp_path / "out.py", git_info=git_info)
    no_line_fn = Function("nl", lineno=None, endlineno=None, parent=pkg)
    assert outside_mod.source_link is None
    assert no_line_fn.source_link is None

    # has_docstrings with broken alias and undocumented members
    undoc_mod = Module("undoc", modules_collection=mc)
    mc["undoc"] = undoc_mod
    undoc_mod["broken"] = Alias("broken", "nonexistent.target", parent=undoc_mod)
    undoc_mod.imports["_priv_imp"] = "pkg.f"
    priv_imp = Alias("_priv_imp", "pkg.f", parent=undoc_mod)
    undoc_mod["_priv_imp"] = priv_imp

    class RaisingMember:
        is_imported = False
        is_public = True

        @property
        def has_docstrings(self) -> bool:
            raise AliasResolutionError(Alias("x", "y", parent=undoc_mod))

    undoc_mod.members["raising_m"] = RaisingMember()  # ty:ignore[invalid-assignment]
    assert not undoc_mod.has_docstrings
    del undoc_mod.members["raising_m"]
    assert pkg.has_docstrings

    # is_kind validation and branches
    with pytest.raises(ValueError, match="empty set"):
        fn.is_kind(set())
    assert fn.is_kind("function")
    assert fn.is_kind(Kind.FUNCTION)
    assert fn.is_kind({Kind.FUNCTION, "class"})
    assert not fn.is_kind({Kind.CLASS, "attribute"})

    # inherited_members on non-Class, Class with empty MRO, and Class with MRO cycle
    assert fn.inherited_members == {}
    empty_mro_cls = Class("EmptyMro", parent=pkg)
    assert empty_mro_cls.inherited_members == {}
    assert len(empty_mro_cls.parameters) == 0
    assert not empty_mro_cls.is_attribute
    assert not empty_mro_cls.is_init_method
    cyc_a = Class("A", bases=["cyc.B"], parent=undoc_mod)
    cyc_b = Class("B", bases=["undoc.A"], parent=undoc_mod)
    undoc_mod["A"] = cyc_a
    mc["cyc"] = Module("cyc", modules_collection=mc)
    mc["cyc"]["B"] = cyc_b
    with pytest.raises(ValueError, match="inheritance cycle detected"):
        cyc_a.mro()
    assert cyc_a.inherited_members == {}

    # Object default boolean properties & filter_members
    assert not fn.is_init_method
    assert not fn.is_init_module
    assert not fn.is_package
    assert not fn.is_subpackage
    assert not fn.is_namespace_package
    assert not fn.is_namespace_subpackage
    assert fn.has_labels()
    assert pkg.filter_members() == pkg.members
    assert pkg.filter_members(lambda m: m.name == "f") == {"f": fn}

    # relative_package_filepath for namespace packages and regular submodules under namespace packages
    ns_top = Module("ns_top", filepath=[tmp_path / "s1" / "ns_top", tmp_path / "s2" / "ns_top"])
    ns_sub = Module("ns_sub", filepath=[tmp_path / "s2" / "ns_top" / "ns_sub"], parent=ns_top)
    ns_bad = Module("ns_bad", filepath=[Path("/nonexistent_xyz/ns_bad")], parent=ns_top)
    reg_under_ns = Module("reg_sub", filepath=tmp_path / "s2" / "ns_top" / "reg_sub.py", parent=ns_top)
    reg_bad_under_ns = Module("reg_bad", filepath=Path("/nonexistent_xyz/reg_bad.py"), parent=ns_top)
    assert ns_sub.relative_package_filepath == Path("ns_top/ns_sub")
    with pytest.raises(ValueError):  # noqa: PT011
        _ = ns_bad.relative_package_filepath
    assert reg_under_ns.relative_package_filepath == Path("ns_top/reg_sub.py")
    with pytest.raises(ValueError):  # noqa: PT011
        _ = reg_bad_under_ns.relative_package_filepath

    # relative_filepath for namespace package (in cwd vs outside cwd)
    ns_in_cwd = Module("ns_cwd", filepath=[Path.cwd() / "sub_ns"])
    assert ns_in_cwd.relative_filepath == Path("sub_ns")
    with pytest.raises(ValueError, match="is relative to the current working directory"):
        _ = ns_bad.relative_filepath

    # modules_collection & lines_collection errors, lines on builtin/namespace/missing/no-lineno
    orphan_fn = Function("orphan")
    with pytest.raises(ValueError, match="no modules collection"):
        _ = orphan_fn.modules_collection
    with pytest.raises(ValueError, match="no lines collection"):
        _ = orphan_fn.lines_collection
    builtin_mod = Module("builtin_m", filepath=None, lines_collection=lc)
    assert builtin_mod.lines == []
    assert ns_top.lines == []
    untracked_mod = Module("untracked", filepath=tmp_path / "untracked.py", lines_collection=lc)
    assert untracked_mod.lines == []
    assert no_line_fn.lines == []
    assert pkg.lines == ["def f():\n", "    pass\n"]

    # resolve with TypeParameter (* and **), and nested serialization context
    fn_tp = Function(
        "fn_tp",
        type_parameters=TypeParameters(
            TypeParameter("T", kind=TypeParameterKind.type_var),
            TypeParameter("Ts", kind=TypeParameterKind.type_var_tuple),
            TypeParameter("P", kind=TypeParameterKind.param_spec),
        ),
        parent=pkg,
    )
    assert fn_tp.resolve("T") == "pkg.fn_tp[T]"
    assert fn_tp.resolve("Ts") == "pkg.fn_tp[*Ts]"
    assert fn_tp.resolve("P") == "pkg.fn_tp[**P]"
    assert TypeAlias("TA_dict", value="int", parent=pkg).as_dict()["value"] == "int"

    sub_pkg = Module("sub_pkg", filepath=pkg_dir / "sub_pkg" / "__init__.py", parent=pkg, lines_collection=lc)
    pkg["sub_pkg"] = sub_pkg
    fn_in_pkg = Function("fn2", lineno=1, endlineno=2, parent=pkg)
    pkg["fn2"] = fn_in_pkg
    full_dict = pkg.as_dict(full=True)
    assert full_dict["members"]["fn2"]["source_link"] is not None
    assert fn_in_pkg.as_dict(full=True)["path"] == "pkg.fn2"

    from griffe._internal.models import _module_serialization_context, _ModuleSerializationContext  # noqa: PLC0415

    tok = _module_serialization_context.set(_ModuleSerializationContext(pkg))
    try:
        assert pkg.as_dict(full=True)["path"] == "pkg"
    finally:
        _module_serialization_context.reset(tok)

    # Alias proxies and methods
    cls_target = Class(
        "MyCls",
        lineno=1,
        endlineno=5,
        bases=["Base"],
        decorators=[dec_str],
        keywords={"metaclass": "Meta"},
        docstring=Docstring("cls doc"),
        type_parameters=TypeParameters(tp),
        parent=pkg,
    )
    init_method = Function(
        "__init__",
        parameters=Parameters(
            Parameter("self", kind=ParameterKind.positional_only),
            Parameter("x", kind=ParameterKind.positional_only, default="1"),
            Parameter("y", kind=ParameterKind.keyword_only),
        ),
        returns="None",
        parent=cls_target,
    )
    cls_target["__init__"] = init_method
    prop_attr = Attribute("prop", value="1", annotation="int", parent=cls_target)
    prop_attr.setter = Function("prop", parent=cls_target)
    prop_attr.deleter = Function("prop", parent=cls_target)
    cls_target["prop"] = prop_attr
    pkg["MyCls"] = cls_target
    ta_target = TypeAlias("MyTA", value="int", parent=pkg)
    pkg["MyTA"] = ta_target

    al_cls = Alias("AlCls", cls_target, lineno=1, endlineno=1, parent=pkg)
    al_fn = Alias("AlFn", init_method, parent=pkg)
    al_attr = Alias("AlAttr", prop_attr, parent=pkg)
    al_mod = Alias("AlMod", pkg, parent=pkg)
    al_ta = Alias("AlTA", ta_target, parent=pkg)
    al_broken = Alias("AlBroken", "does.not.exist", lineno=2, endlineno=3, analysis="static", parent=pkg)
    al_broken.deprecated = "old"
    al_broken_public = Alias("AlBrokenPub", "does.not.exist", parent=pkg)
    al_broken_public.public = True

    assert repr(al_cls) == "Alias('AlCls', 'pkg.MyCls')"
    assert bool(al_cls) is True
    assert len(al_cls) == 1
    assert al_cls.has_docstring is True
    assert al_broken.has_docstring is False
    assert al_cls.has_docstrings is True
    assert al_broken.has_docstrings is False

    # Alias.public getter/setter and inherited alias public
    inh_al = Alias("inh", prop_attr, parent=cls_target, inherited=True)
    assert inh_al.public is None
    with pytest.raises(TypeError, match="forbidden"):
        inh_al.public = True
    al_cls.public = True
    assert al_cls.public is True

    # Alias.members and Alias.inherited_members and Alias.as_json
    base_cls = Class("Base", parent=pkg)
    base_cls["base_m"] = Attribute("base_m", value="0", parent=base_cls)
    pkg["Base"] = base_cls
    cls_target.bases = ["pkg.Base"]
    assert "prop" in al_cls.members
    assert "base_m" in al_cls.inherited_members
    assert al_cls.as_json(full=False)
    assert al_broken.as_json(full=False)
    assert al_broken.as_dict(full=True)["deprecated"] == "old"
    assert al_broken_public.as_dict(full=False)["public"] is True

    # Generic & specific proxies on Alias
    assert al_cls.git_info is git_info
    al_cls.git_info = git_info
    assert al_cls.source_link == cls_target.source_link
    al_cls.source_link = "https://link"
    assert al_cls.extra == cls_target.extra
    assert al_cls.lineno == 1
    al_cls.lineno = 2
    assert al_cls.endlineno == 5
    al_cls.endlineno = 6
    assert al_cls.docstring is not None
    al_cls.docstring = Docstring("new doc")
    assert len(al_cls.type_parameters) == 1
    al_cls.type_parameters = TypeParameters()
    assert al_cls.labels == set()
    assert al_cls.imports == {}
    assert al_cls.exports is None
    assert al_cls.aliases
    assert al_cls.is_kind(Kind.CLASS)
    assert not al_cls.is_module
    assert al_cls.is_class
    assert not al_cls.is_function
    assert not al_cls.is_attribute
    assert not al_cls.is_type_alias
    assert al_ta.is_type_alias
    assert al_cls.has_labels()
    assert al_cls.filter_members()
    assert al_cls.module is pkg
    assert al_cls.package is pkg
    assert al_cls.filepath == init_py
    assert al_cls.relative_filepath
    assert al_cls.relative_package_filepath
    assert al_cls.canonical_path == "pkg.MyCls"
    assert al_cls.lines_collection is lc
    assert al_cls.lines
    assert al_cls.source
    assert al_cls.resolve("prop") == "pkg.MyCls.prop"
    assert al_mod._filepath == init_py
    assert al_cls.bases == ["pkg.Base"]
    assert al_cls.keywords == {"metaclass": "Meta"}
    assert al_cls.decorators == [dec_str]
    assert not al_mod.imports_future_annotations
    assert al_fn.is_init_method
    assert al_mod.is_init_module
    assert al_mod.is_package
    assert not al_mod.is_subpackage
    assert not al_mod.is_namespace_package
    assert not al_mod.is_namespace_subpackage
    assert al_fn.overloads is None
    al_fn.overloads = []
    assert len(al_cls.parameters) == 3
    assert al_fn.returns == "None"
    al_fn.returns = "int"
    assert al_attr.setter is not None
    assert al_attr.deleter is not None
    assert al_attr.value == "1"
    al_attr.value = "2"
    assert al_attr.annotation == "int"
    al_attr.annotation = "str"
    assert al_cls.resolved_bases == [base_cls]
    assert al_cls.mro() == [base_cls]
    assert al_cls.signature()

    # Alias target setter & CyclicAliasError branches
    with pytest.raises(CyclicAliasError):
        al_cls.target = al_cls
    al_orphan = Alias("OrphanAl", "some.target", parent=pkg)
    al_orphan.target = cls_target
    assert al_orphan.resolved

    # Pre-resolved alias cycle in final_target
    cyc1 = Alias("cyc1", "pkg.cyc2", parent=pkg)
    cyc2 = Alias("cyc2", "pkg.cyc1", parent=pkg)
    cyc1._target = cyc2
    cyc2._target = cyc1
    with pytest.raises(CyclicAliasError):
        _ = cyc1.final_target

    # Self-alias and _passed_through in resolve_target
    self_al = Alias("self_al", "pkg.self_al", parent=pkg)
    pkg["self_al"] = self_al
    with pytest.raises(CyclicAliasError):
        self_al.resolve_target()
    self_al._passed_through = True
    try:
        with pytest.raises(CyclicAliasError):
            self_al.resolve_target()
    finally:
        self_al._passed_through = False

    # Alias without parent resolved in _resolve_target
    al_no_parent = Alias("np", "pkg.MyCls")
    al_no_parent._parent = pkg  # give access to modules_collection via property while testing parent check
    al_no_parent.resolve_target()
    assert al_no_parent.wildcard is None

    # Module properties on builtin / namespace modules
    assert repr(builtin_mod) == "Module('builtin_m')"
    assert not builtin_mod.is_init_module
    assert not ns_top.is_init_module
    assert not builtin_mod.is_namespace_package
    assert not builtin_mod.is_namespace_subpackage
    ns_sub_under_builtin = Module("ns_b", filepath=None, parent=ns_top)
    assert not ns_sub_under_builtin.is_namespace_subpackage
    assert ns_top.as_dict()["filepath"] == [str(tmp_path / "s1" / "ns_top"), str(tmp_path / "s2" / "ns_top")]
    assert builtin_mod.as_dict()["filepath"] is None
    assert not fn.is_type_alias

    # inherited_members when child class defines a member overriding base_cls member
    cls_target["base_m"] = Attribute("base_m", value="1", parent=cls_target)
    assert "base_m" not in cls_target.inherited_members

    # Class.signature when __init__ is not a Function or missing, and Class.resolved_bases with alias base
    cls_no_init = Class("NoInit", parent=pkg)
    assert cls_no_init.signature() == ""
    cls_attr_init = Class("AttrInit", parent=pkg)
    cls_attr_init["__init__"] = Attribute("__init__", parent=cls_attr_init)
    assert cls_attr_init.signature() == ""
    pkg["BaseAl"] = Alias("BaseAl", base_cls, parent=pkg)
    cls_al_base = Class("ClsAlBase", bases=["pkg.BaseAl"], parent=pkg)
    assert cls_al_base.resolved_bases == [base_cls]

    # Function.annotation, Function.resolve in __init__ (parameter, missing member, broken alias, normal member)
    assert init_method.annotation == "int"
    assert init_method.resolve("x") == "pkg.MyCls(x)"
    cls_target["broken_al"] = al_broken
    assert init_method.resolve("broken_al") == "does.not.exist"
    cls_target["al_to_broken"] = Alias("al_to_broken", "pkg.AlBroken", parent=cls_target)
    pkg["AlBroken"] = al_broken
    assert init_method.resolve("al_to_broken") == "pkg.AlBroken"

    class BrokenLabelsAttr:
        path = "pkg.MyCls.broken_lbl"
        is_alias = False
        is_attribute = True

        @property
        def labels(self) -> set[str]:
            raise AliasResolutionError(al_broken)

    cls_target.members["broken_lbl"] = BrokenLabelsAttr()  # ty:ignore[invalid-assignment]
    assert init_method.resolve("broken_lbl") == "pkg.MyCls.broken_lbl"
    del cls_target.members["broken_lbl"]

    cls_target["inst_attr"] = Attribute("inst_attr", parent=cls_target)
    cls_target["inst_attr"].labels.add("instance-attribute")
    with pytest.raises(NameResolutionError):
        init_method.resolve("inst_attr")
    assert init_method.resolve("prop") == "pkg.MyCls.prop"

    # Function.signature with only positional-only parameters
    pos_only_fn = Function(
        "pos_fn",
        parameters=Parameters(Parameter("a", kind=ParameterKind.positional_only)),
    )
    assert pos_only_fn.signature() == "pos_fn(a, /)"
