"""Tests for the docstrings utility functions."""

from __future__ import annotations

from pathlib import Path

from griffe import (
    Docstring,
    ExprName,
    Function,
    Module,
    Parameter,
    ParameterKind,
    Parameters,
    Parser,
    docstring_warning,
    parse,
    parse_docstring_annotation,
)


def test_can_warn_without_parent_module() -> None:
    """Assert we can parse a docstring even if it does not have a parent module."""
    function = Function(
        "func",
        parameters=Parameters(
            Parameter("param1", annotation=None, kind=ParameterKind.positional_or_keyword),
            Parameter("param2", annotation="int", kind=ParameterKind.keyword_only),
        ),
    )
    text = """
    Hello I'm a docstring!

    Parameters:
        param1: Description.
        param2: Description.
    """
    docstring = Docstring(text, lineno=1, parent=function)
    assert parse(docstring, Parser.google)


def test_docstring_warning_variants() -> None:
    """Test `docstring_warning` with different parent configurations."""
    # No parent
    doc_no_parent = Docstring("Hello", lineno=1)
    docstring_warning(doc_no_parent, 0, "Warning without parent")

    # Builtin module parent (filepath=None raises BuiltinModuleError on relative_filepath)
    builtin_mod = Module("builtins", filepath=None)
    doc_builtin = Docstring("Hello", lineno=1, parent=builtin_mod)
    docstring_warning(doc_builtin, 0, "Warning on builtin module")

    # Regular module parent with filepath in cwd
    regular_mod = Module("mod", filepath=Path.cwd() / "mod.py")
    doc_regular = Docstring("Hello", lineno=1, parent=regular_mod)
    docstring_warning(doc_regular, 0, "Warning on regular module")


def test_parse_docstring_annotation() -> None:
    """Test `parse_docstring_annotation` with valid, empty, and invalid annotations."""
    mod = Module("mod", filepath=Path.cwd() / "mod.py")
    doc = Docstring("Hello", lineno=1, parent=mod)

    parsed = parse_docstring_annotation("int", doc)
    assert isinstance(parsed, ExprName)
    assert parsed.name == "int"

    # SyntaxError in annotation returns string unchanged
    assert parse_docstring_annotation("int[", doc) == "int["
    assert parse_docstring_annotation("", doc) == ""
