# This module defines functions to parse docstrings into structured data using cdd-python.

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, TypeVar

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
    from collections import OrderedDict
    from typing import Any

    from griffe._internal.models import Docstring


T = TypeVar("T", DocstringParameter, DocstringReturn)


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


__all__ = [
    "CddOptions",
    "GoogleOptions",
    "NumpyOptions",
    "SphinxOptions",
    "ir_param_to_griffe_param",
    "ir_to_griffe",
    "parse_cdd",
    "parse_google",
    "parse_numpy",
    "parse_sphinx",
]
