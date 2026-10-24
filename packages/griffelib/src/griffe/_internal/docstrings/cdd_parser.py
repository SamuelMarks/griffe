# This module defines functions to parse docstrings into structured data using cdd-python.

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, TypedDict, TypeVar

import cdd.docstring.emit
import cdd.docstring.parse
import cdd.shared.types

from griffe._internal.docstrings.models import (
    DocstringParameter,
    DocstringReturn,
    DocstringSection,
    DocstringSectionParameters,
    DocstringSectionReturns,
    DocstringSectionText,
)
from griffe._internal.docstrings.utils import docstring_warning  # noqa: F401

if TYPE_CHECKING:
    from typing import Any

    from griffe._internal.models import Docstring


T = TypeVar("T", DocstringParameter, DocstringReturn)
CddDocstringFormat = Literal["rest", "numpydoc", "google"]


class CddOptions(TypedDict, total=False):
    """Options for parsing docstrings with cdd-python."""

    ignore_init_summary: bool
    """Whether to ignore the summary in `__init__` methods' docstrings."""
    trim_doctest_flags: bool
    """Whether to remove doctest flags from Python example blocks."""
    returns_multiple_items: bool
    """Whether to parse multiple items in `Yields` and `Returns` sections."""
    returns_named_value: bool
    """Whether to parse `Yields` and `Returns` section items as name and description, rather than type and description."""
    returns_type_in_property_summary: bool
    """Whether to parse the return type of properties at the beginning of their summary."""
    receives_multiple_items: bool
    """Whether to parse multiple items in `Receives` sections."""
    receives_named_value: bool
    """Whether to parse `Receives` section items as name and description, rather than type and description."""
    warn_unknown_params: bool
    """Warn about documented parameters not appearing in the signature."""
    warn_missing_types: bool
    """Warn about missing types/annotations for parameters, return values, etc."""
    warnings: bool
    """Whether to log warnings at all."""


GoogleOptions = CddOptions
"""Options for parsing Google-style docstrings."""
NumpyOptions = CddOptions
"""Options for parsing Numpy-style docstrings."""
SphinxOptions = CddOptions
"""Options for parsing Sphinx-style docstrings."""


def ir_param_to_griffe_param(
    ir_param: OrderedDict[str, cdd.shared.types.ParamVal],
    cls: type[T],
) -> list[T]:
    """Convert an OrderedDict of cdd-python ParamVal to a list of griffe elements.

    Parameters:
        ir_param: The OrderedDict to convert.
        cls: The docstring model class.

    Returns:
        The list of docstring elements.
    """
    return [
        cls(
            name=name if cls is not DocstringReturn else "",
            description=param.get("doc") or "",
            annotation=param.get("typ") or None,
            value=param.get("default") or None,
        )
        for name, param in ir_param.items()
    ]


def ir_to_griffe(ir: cdd.shared.types.IntermediateRepr) -> list[DocstringSection]:
    """Convert cdd-python IR to a list of griffe DocstringSections.

    Parameters:
        ir: The intermediate representation.

    Returns:
        The list of sections.
    """
    sections: list[DocstringSection] = []
    doc = ir.get("doc")
    params = ir.get("params")
    returns = ir.get("returns")

    if doc:
        sections.append(DocstringSectionText(doc))
    elif params or returns:
        sections.append(DocstringSectionText(""))

    if params:
        sections.append(
            DocstringSectionParameters(
                ir_param_to_griffe_param(params, DocstringParameter),
            ),
        )

    if returns:
        sections.append(
            DocstringSectionReturns(
                ir_param_to_griffe_param(returns, DocstringReturn),
            ),
        )
    return sections


def parse_cdd(
    docstring: Docstring,
    *,
    ignore_init_summary: bool = False,  # noqa: ARG001
    trim_doctest_flags: bool = True,  # noqa: ARG001
    returns_multiple_items: bool = True,  # noqa: ARG001
    returns_named_value: bool = True,  # noqa: ARG001
    returns_type_in_property_summary: bool = False,  # noqa: ARG001
    receives_multiple_items: bool = True,  # noqa: ARG001
    receives_named_value: bool = True,  # noqa: ARG001
    warn_unknown_params: bool = True,  # noqa: ARG001
    warn_missing_types: bool = True,  # noqa: ARG001
    warnings: bool = True,  # noqa: ARG001
    **options: Any,  # noqa: ARG001
) -> list[DocstringSection]:
    """Parse a docstring using cdd-python.

    Parameters:
        docstring: The docstring to parse.
        ignore_init_summary: Whether to ignore the summary in `__init__` methods' docstrings.
        trim_doctest_flags: Whether to remove doctest flags from Python example blocks.
        returns_multiple_items: Whether to parse multiple items in `Yields` and `Returns` sections.
        returns_named_value: Whether to parse `Yields` and `Returns` section items as name and description, rather than type and description.
        returns_type_in_property_summary: Whether to parse the return type of properties at the beginning of their summary.
        receives_multiple_items: Whether to parse multiple items in `Receives` sections.
        receives_named_value: Whether to parse `Receives` section items as name and description, rather than type and description.
        warn_unknown_params: Warn about documented parameters not appearing in the signature.
        warn_missing_types: Warn about missing types/annotations for parameters, return values, etc.
        warnings: Whether to log warnings at all.
        **options: Additional parsing options.

    Returns:
        A list of docstring sections.
    """
    ir: cdd.shared.types.IntermediateRepr = cdd.docstring.parse.docstring(
        docstring.value,
    )
    return ir_to_griffe(ir)


parse_google = parse_cdd
parse_numpy = parse_cdd
parse_sphinx = parse_cdd


def griffe_param_to_ir_param(
    elements: Sequence[DocstringParameter | DocstringReturn],
) -> OrderedDict[str, cdd.shared.types.ParamVal]:
    """Convert a sequence of griffe docstring elements to an OrderedDict of cdd-python ParamVal.

    Parameters:
        elements: The sequence of docstring elements to convert.

    Returns:
        The OrderedDict of cdd-python ParamVal.
    """
    result: OrderedDict[str, cdd.shared.types.ParamVal] = OrderedDict()
    for elem in elements:
        key = elem.name if isinstance(elem, DocstringParameter) and elem.name else "return_type"
        param_val: cdd.shared.types.ParamVal = {
            "typ": str(elem.annotation) if elem.annotation is not None else "",
            "doc": elem.description or None,
            "default": elem.value,
        }
        if not param_val["typ"]:
            del param_val["typ"]  # ty:ignore[invalid-argument-type]
        if param_val["doc"] is None:
            del param_val["doc"]  # ty:ignore[invalid-argument-type]
        if param_val["default"] is None:
            del param_val["default"]  # ty:ignore[invalid-argument-type]
        result[key] = param_val
    return result


def griffe_to_ir(sections: Sequence[DocstringSection]) -> cdd.shared.types.IntermediateRepr:
    """Convert a sequence of griffe DocstringSections to cdd-python IR.

    Parameters:
        sections: The sequence of docstring sections.

    Returns:
        The intermediate representation.
    """
    doc_parts: list[str] = []
    params: OrderedDict[str, cdd.shared.types.ParamVal] = OrderedDict()
    returns: OrderedDict[str, cdd.shared.types.ParamVal] | None = None

    for section in sections:
        if isinstance(section, DocstringSectionText):
            if section.value:
                doc_parts.append(section.value)
        elif isinstance(section, DocstringSectionParameters):
            params.update(griffe_param_to_ir_param(section.value))
        elif isinstance(section, DocstringSectionReturns):
            returns = griffe_param_to_ir_param(section.value)

    return {
        "name": None,
        "type": "static",
        "doc": "\n\n".join(doc_parts) if doc_parts else "",
        "params": params,
        "returns": returns,
    }


def emit_cdd(
    docstring_or_sections: Docstring | Sequence[DocstringSection],
    *,
    docstring_format: CddDocstringFormat = "rest",
    purpose: Literal["class", "function"] = "function",
    word_wrap: bool = True,
    indent_level: int = 0,
    emit_separating_tab: bool = True,
    emit_types: bool = True,
    emit_original_whitespace: bool = False,
    emit_default_doc: bool = True,
) -> str:
    """Emit a docstring string from a Docstring or sequence of DocstringSections using cdd-python.

    Parameters:
        docstring_or_sections: The docstring or parsed docstring sections to emit.
        docstring_format: Target docstring format (`"rest"`, `"numpydoc"`, or `"google"`).
        purpose: Whether the docstring is for a `"function"` or a `"class"`.
        word_wrap: Whether to word-wrap.
        indent_level: Indentation level.
        emit_separating_tab: Whether to put a tab between param/return and description.
        emit_types: Whether to show type lines.
        emit_original_whitespace: Whether to emit original whitespace or strip it out.
        emit_default_doc: Whether help/docstring should include 'With default' text.

    Returns:
        The emitted docstring string.
    """
    sections = docstring_or_sections if isinstance(docstring_or_sections, Sequence) else docstring_or_sections.parsed
    ir = griffe_to_ir(sections)
    return cdd.docstring.emit.docstring(
        ir,
        docstring_format=docstring_format,
        purpose=purpose,
        word_wrap=word_wrap,
        indent_level=indent_level,
        emit_separating_tab=emit_separating_tab,
        emit_types=emit_types,
        emit_original_whitespace=emit_original_whitespace,
        emit_default_doc=emit_default_doc,
    )


def emit_google(
    docstring_or_sections: Docstring | Sequence[DocstringSection],
    **options: Any,
) -> str:
    """Emit a Google-style docstring using cdd-python.

    Parameters:
        docstring_or_sections: The docstring or parsed docstring sections to emit.
        **options: Additional emission options forwarded to `emit_cdd`.

    Returns:
        The emitted Google-style docstring string.
    """
    return emit_cdd(docstring_or_sections, docstring_format="google", **options)


def emit_numpy(
    docstring_or_sections: Docstring | Sequence[DocstringSection],
    **options: Any,
) -> str:
    """Emit a Numpy-style docstring using cdd-python.

    Parameters:
        docstring_or_sections: The docstring or parsed docstring sections to emit.
        **options: Additional emission options forwarded to `emit_cdd`.

    Returns:
        The emitted Numpy-style docstring string.
    """
    return emit_cdd(docstring_or_sections, docstring_format="numpydoc", **options)


def emit_sphinx(
    docstring_or_sections: Docstring | Sequence[DocstringSection],
    **options: Any,
) -> str:
    """Emit a Sphinx/ReST-style docstring using cdd-python.

    Parameters:
        docstring_or_sections: The docstring or parsed docstring sections to emit.
        **options: Additional emission options forwarded to `emit_cdd`.

    Returns:
        The emitted Sphinx/ReST-style docstring string.
    """
    return emit_cdd(docstring_or_sections, docstring_format="rest", **options)


emit_rest = emit_sphinx


__all__ = [
    "CddDocstringFormat",
    "CddOptions",
    "GoogleOptions",
    "NumpyOptions",
    "SphinxOptions",
    "emit_cdd",
    "emit_google",
    "emit_numpy",
    "emit_rest",
    "emit_sphinx",
    "griffe_param_to_ir_param",
    "griffe_to_ir",
    "ir_param_to_griffe_param",
    "ir_to_griffe",
    "parse_cdd",
    "parse_google",
    "parse_numpy",
    "parse_sphinx",
]
