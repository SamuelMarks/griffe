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

# Tests for the `mixins` module.

from __future__ import annotations

from griffe import module_vtree


def test_access_members_with_string_and_tuples() -> None:
    """Assert we can access members with both strings and tuples."""
    module = module_vtree("a.b.c.d")
    assert module["b"] is module[("b",)]
    assert module["b.c"] is module[("b", "c")]
    assert module["b.c.d"] is module[("b", "c", "d")]


def test_mixins_methods_and_properties() -> None:
    """Test all methods and properties of `GetMembersMixin`, `SetMembersMixin`, `DelMembersMixin`, and `ObjectAliasMixin`."""
    from pathlib import Path  # noqa: PLC0415

    import pytest  # noqa: PLC0415

    from griffe._internal.collections import ModulesCollection  # noqa: PLC0415
    from griffe._internal.enumerations import TypeParameterKind  # noqa: PLC0415
    from griffe._internal.models import (  # noqa: PLC0415
        Alias,
        Attribute,
        Class,
        Function,
        Module,
        TypeAlias,
        TypeParameter,
        TypeParameters,
    )

    with pytest.raises(ValueError, match="Empty strings are not supported"):
        _ = module_vtree("a")[""]
    with pytest.raises(ValueError, match="Empty tuples are not supported"):
        _ = module_vtree("a")[()]

    mc = ModulesCollection()
    root = Module("root", filepath=Path("root/__init__.py"), modules_collection=mc)
    mc.set_member("root", root)
    sub = Module("sub", filepath=Path("sub.py"))
    root.set_member("sub", sub)
    sub["x"] = Attribute("x", value="0")
    al_to_sub = Alias("al_to_sub", "root.sub", parent=root)
    root.set_member("al_to_sub", al_to_sub)
    assert al_to_sub.target is sub

    # Reassigning alias member in set_member
    root.set_member("al_to_sub", Alias("al_to_sub", "root.sub", parent=root))

    # Re-setting a module with set_member merges stubs and updates aliases
    sub_same = Module("sub", filepath=Path("sub.py"))
    root.set_member("sub", sub_same)
    sub_stub = Module("sub", filepath=Path("sub.pyi"))
    sub_stub["y"] = Attribute("y", value="2")
    root.set_member("sub", sub_stub)
    assert "y" in root.get_member("sub").members
    assert root.get_member(("sub", "y")).value == "2"

    # Reassigning module with non-module
    root.set_member("sub_mod_to_attr", Module("sub_mod_to_attr", filepath=Path("s.py")))
    root.set_member("sub_mod_to_attr", Attribute("sub_mod_to_attr", value="1"))

    # Reassigning namespace package module
    ns_mod = Module("ns_mod", filepath=[Path("a"), Path("b")])
    mc.set_member("ns_mod", ns_mod)
    mc.set_member("ns_mod", Module("ns_mod", filepath=Path("ns.pyi")))

    # Reassigning in ModulesCollection directly with stubs
    mc_mod = Module("mc_mod", filepath=Path("mc_mod.py"))
    mc.set_member("mc_mod", mc_mod)
    mc.set_member("mc_mod", Module("mc_mod", filepath=Path("mc_mod.pyi")))
    mc["mc_direct"] = Module("mc_direct", filepath=Path("mc_direct.py"))

    # Nested set_member, __setitem__, del_member, __delitem__
    root.set_member("sub.z", Attribute("z", value="3"))
    assert "z" in root["sub"].members
    root["sub.w"] = Attribute("w", value="4")
    assert "w" in root["sub"].members
    root.del_member("sub.z")
    assert "z" not in root["sub"].members
    del root["sub.w"]
    assert "w" not in root["sub"].members
    root.del_member("sub")
    assert "sub" not in root.members

    # Delete inherited member via __delitem__
    base_cls = Class("Base", parent=root)
    base_cls["inh"] = Attribute("inh", value="1", parent=base_cls)
    root["Base"] = base_cls
    from griffe._internal.expressions import ExprName  # noqa: PLC0415

    child_cls = Class("Child", bases=[ExprName("Base", parent=root)], parent=root)
    root["Child"] = child_cls
    assert "inh" in child_cls.inherited_members
    del child_cls["inh"]

    # ObjectAliasMixin properties and predicates
    cls = Class(
        "MyCls",
        type_parameters=TypeParameters(TypeParameter("T", kind=TypeParameterKind.type_var)),
        parent=root,
    )
    cls.deprecated = "Deprecated cls"
    root["MyCls"] = cls
    cls["__priv"] = Attribute("__priv", value="1", parent=cls)
    cls["_prot"] = Attribute("_prot", value="2", parent=cls)
    cls["__dunder__"] = Function("__dunder__", parent=cls)
    cls["meth"] = Function("meth", parent=cls)
    cls["TA"] = TypeAlias("TA", parent=cls)
    cls["al"] = Alias("al", "root.MyCls.meth", parent=cls)

    assert root.is_module
    assert not root.is_class
    assert not root.is_function
    assert not root.is_attribute
    assert not root.is_alias
    assert not root.is_type_alias
    assert not root.is_imported
    assert cls.is_class
    assert cls.is_deprecated
    assert cls.is_generic
    assert cls["meth"].is_function
    assert cls["TA"].is_type_alias
    assert cls["al"].is_alias
    assert cls["__priv"].is_private
    assert cls["__priv"].is_class_private
    assert cls["_prot"].is_private
    assert not cls["_prot"].is_class_private
    assert cls["__dunder__"].is_special

    # Filtered member dictionaries (`modules`, `classes`, `functions`, `attributes`, `type_aliases`)
    assert "MyCls" in root.classes
    assert "meth" in cls.functions
    assert "__priv" in cls.attributes
    assert "TA" in cls.type_aliases
    assert not cls.modules
