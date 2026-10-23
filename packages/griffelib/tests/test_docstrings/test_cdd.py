"""Tests for cdd-python docstring parser integration."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

import pytest

from griffe import (
    Attribute,
    Class,
    Docstring,
    DocstringAdmonition,
    DocstringAttribute,
    DocstringClass,
    DocstringDeprecated,
    DocstringElement,
    DocstringFunction,
    DocstringModule,
    DocstringNamedElement,
    DocstringParameter,
    DocstringRaise,
    DocstringReceive,
    DocstringReturn,
    DocstringSectionAdmonition,
    DocstringSectionAttributes,
    DocstringSectionClasses,
    DocstringSectionDeprecated,
    DocstringSectionExamples,
    DocstringSectionFunctions,
    DocstringSectionKind,
    DocstringSectionModules,
    DocstringSectionOtherParameters,
    DocstringSectionParameters,
    DocstringSectionRaises,
    DocstringSectionReceives,
    DocstringSectionReturns,
    DocstringSectionText,
    DocstringSectionTypeAliases,
    DocstringSectionTypeParameters,
    DocstringSectionWarns,
    DocstringSectionYields,
    DocstringTypeAlias,
    DocstringTypeParameter,
    DocstringWarn,
    DocstringYield,
    ExprTuple,
    Function,
    Module,
    Parser,
    infer_docstring_style,
    ir_param_to_griffe_param,
    ir_to_griffe,
    parse,
    parse_auto,
    parse_cdd,
    parse_google,
    parse_numpy,
    parse_sphinx,
)

if TYPE_CHECKING:
    from cdd.shared.types import ParamVal

    from tests.test_docstrings.helpers import ParserType


def test_parse_cdd_basic(
    parse_rest: ParserType,
    parse_google: ParserType,
    parse_numpy: ParserType,
    parse_sphinx: ParserType,
) -> None:
    """Test basic functionality of cdd-python parser integration.

    Parameters:
        parse_rest: The ReST parser fixture.
        parse_google: The Google parser fixture.
        parse_numpy: The Numpy parser fixture.
        parse_sphinx: The Sphinx parser fixture.
    """
    docstring = """
    A simple summary.

    :param int foo: A foo
    :param str bar: A bar
    :return: Something
    :rtype: bool
    """
    for parser_func in (parse_rest, parse_google, parse_numpy, parse_sphinx):
        sections, _warnings = parser_func(docstring)
        assert len(sections) == 3
        assert isinstance(sections[0], DocstringSectionText)
        assert isinstance(sections[1], DocstringSectionParameters)
        assert isinstance(sections[2], DocstringSectionReturns)


def test_parse_with_parent(parse_rest: ParserType) -> None:
    """Test parsing a docstring attached to a parent object.

    Parameters:
        parse_rest: The ReST parser fixture.
    """
    parent = Function("my_func")
    sections, warnings = parse_rest("Summary.", parent=parent)
    assert len(sections) == 1
    assert not warnings
    assert parent.docstring is not None
    assert parent.docstring.parent is parent


def test_ir_to_griffe_branches() -> None:
    """Test all branches of `ir_to_griffe` and `ir_param_to_griffe_param`."""
    empty_sections = ir_to_griffe({"name": None, "type": "static", "doc": None, "params": OrderedDict(), "returns": None})
    assert empty_sections == []

    no_doc_sections = ir_to_griffe(
        {
            "name": None,
            "type": "static",
            "doc": None,
            "params": OrderedDict({"x": {"typ": "int", "doc": "X param", "default": "0"}}),
            "returns": None,
        },
    )
    assert len(no_doc_sections) == 2
    assert isinstance(no_doc_sections[0], DocstringSectionText)
    assert no_doc_sections[0].value == ""
    assert isinstance(no_doc_sections[1], DocstringSectionParameters)
    assert no_doc_sections[1].value[0].name == "x"
    assert no_doc_sections[1].value[0].annotation == "int"
    assert no_doc_sections[1].value[0].description == "X param"
    assert no_doc_sections[1].value[0].value == "0"

    empty_val: ParamVal = {"default": None, "doc": None, "typ": ""}
    empty_param_dict: OrderedDict[str, ParamVal] = OrderedDict([("y", empty_val)])
    empty_param = ir_param_to_griffe_param(empty_param_dict, DocstringParameter)
    assert empty_param[0].name == "y"
    assert empty_param[0].description == ""
    assert empty_param[0].annotation is None
    assert empty_param[0].value is None


def test_parsers_dispatch() -> None:
    """Test `parse`, `parse_cdd`, `parse_google`, `parse_numpy`, `parse_sphinx`, and `parse_auto`."""
    doc = Docstring(
        """
        :param int x: X.
        :return: Y.
        :rtype: str
        """,
    )
    assert len(parse(doc, "rest")) == 3
    assert len(parse(doc, Parser.google)) == 3
    assert len(parse_cdd(doc)) == 3
    assert len(parse_google(doc)) == 3
    assert len(parse_numpy(doc)) == 3
    assert len(parse_sphinx(doc)) == 3

    assert parse(Docstring("Plain text."), None) != []
    assert parse(Docstring(""), None) == []


def test_auto_parser() -> None:
    """Test `infer_docstring_style` and `parse_auto` across detection methods."""
    sphinx_doc = Docstring(
        """
        Summary.

        :param x: Value.
        :returns: Output.
        """,
    )
    style, sections = infer_docstring_style(sphinx_doc, method="heuristics")
    assert style is Parser.sphinx
    assert sections is None
    assert len(parse_auto(sphinx_doc, method="heuristics")) == 3

    plain_doc = Docstring("Just plain text.")
    style, sections = infer_docstring_style(plain_doc, method="heuristics", default="google")
    assert style is Parser.google
    assert sections is None

    style, sections = infer_docstring_style(plain_doc, method="heuristics", default=None)
    assert style is None
    assert sections is None
    assert len(parse_auto(plain_doc, method="heuristics", default=None)) == 1

    style, sections = infer_docstring_style(
        sphinx_doc,
        method="max_sections",
        style_order=["google", "sphinx"],
    )
    assert style is Parser.google
    assert sections is not None
    assert len(parse_auto(sphinx_doc, method="max_sections")) == 3

    custom_parser = lambda _doc, **_opts: []  # noqa: E731
    from griffe._internal.docstrings.parsers import parsers  # noqa: PLC0415

    orig_google = parsers[Parser.google]
    try:
        parsers[Parser.google] = custom_parser
        style, sections = infer_docstring_style(
            sphinx_doc,
            method="max_sections",
            style_order=["google", "sphinx"],
        )
        assert style is Parser.sphinx
        assert sections is not None
    finally:
        parsers[Parser.google] = orig_google

    with pytest.raises(ValueError, match="Invalid method"):
        infer_docstring_style(plain_doc, method="invalid")  # ty:ignore[invalid-argument-type]


def test_docstring_models() -> None:
    """Test all docstring element and section models and their properties."""
    elem = DocstringElement(description="desc", annotation="int")
    assert elem.as_dict() == {"annotation": "int", "description": "desc"}

    named = DocstringNamedElement("x", description="desc", annotation="int", value="1")
    assert named.as_dict() == {"name": "x", "annotation": "int", "description": "desc", "value": "1"}
    named_no_val = DocstringNamedElement("x", description="desc")
    assert "value" not in named_no_val.as_dict()

    adm = DocstringAdmonition(description="text", annotation="note")
    assert adm.kind == "note"
    adm.kind = "warning"
    assert adm.kind == "warning"
    assert adm.contents == "text"
    adm.contents = "new text"
    assert adm.contents == "new text"

    dep = DocstringDeprecated(description="old", annotation="1.0")
    assert dep.version == "1.0"
    dep.version = "2.0"
    assert dep.version == "2.0"

    param = DocstringParameter("p", description="param", value="None")
    assert param.default == "None"
    param.default = "0"
    assert param.default == "0"

    tparam = DocstringTypeParameter("T", description="type param", annotation="int", value="str")
    assert tparam.default == "str"
    tparam.default = "bool"
    assert tparam.default == "bool"
    assert tparam.bound == "int"
    assert tparam.constraints is None
    tparam.bound = "float"
    assert tparam.bound == "float"
    tparam.constraints = ["int", "str"]
    assert tparam.bound is None
    assert isinstance(tparam.annotation, ExprTuple)
    assert tparam.constraints == ("int", "str")
    tparam.constraints = None
    assert tparam.annotation is None

    dfunc = DocstringFunction("f", description="func", annotation="f(x)")
    assert dfunc.signature == "f(x)"

    dcls = DocstringClass("C", description="cls", annotation="C(x)")
    assert dcls.signature == "C(x)"

    sections = [
        DocstringSectionText("hello", title="Title"),
        DocstringSectionParameters([param]),
        DocstringSectionOtherParameters([param]),
        DocstringSectionTypeParameters([tparam]),
        DocstringSectionRaises([DocstringRaise(description="err", annotation="ValueError")]),
        DocstringSectionWarns([DocstringWarn(description="warn", annotation="UserWarning")]),
        DocstringSectionReturns([DocstringReturn("", description="ret", annotation="int")]),
        DocstringSectionYields([DocstringYield("", description="yld", annotation="int")]),
        DocstringSectionReceives([DocstringReceive("", description="rcv", annotation="int")]),
        DocstringSectionExamples([(DocstringSectionKind.text, "ex")]),
        DocstringSectionAttributes([DocstringAttribute("a", description="attr", annotation="int")]),
        DocstringSectionFunctions([dfunc]),
        DocstringSectionClasses([dcls]),
        DocstringSectionTypeAliases([DocstringTypeAlias("TA", description="ta")]),
        DocstringSectionModules([DocstringModule("m", description="mod")]),
        DocstringSectionDeprecated(version="1.0", text="dep", title="Dep"),
        DocstringSectionAdmonition(kind="note", text="adm"),
    ]
    for sec in sections:
        assert bool(sec)
        data = sec.as_dict()
        assert "kind" in data
        assert "value" in data

    # Ensure imported types are referenced.
    assert Attribute is not None
    assert Class is not None
    assert Module is not None
