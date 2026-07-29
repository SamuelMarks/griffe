# This module defines functions to parse docstrings into structured data using cdd-python.

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

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
            description=param["doc"] if param.get("doc") else "",
            annotation=param["typ"] if param.get("typ") else None,
            value=param["default"] if param.get("default") else None,
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

    if ir.get("doc"):
        sections.append(DocstringSectionText(ir["doc"]))
    elif ir.get("params") or ir.get("returns"):
        sections.append(DocstringSectionText(""))

    if ir.get("params"):
        sections.append(
            DocstringSectionParameters(
                ir_param_to_griffe_param(ir["params"], DocstringParameter),
            ),
        )

    if ir.get("returns"):
        sections.append(
            DocstringSectionReturns(
                ir_param_to_griffe_param(ir["returns"], DocstringReturn),
            ),
        )
    return sections


def parse_cdd(
    docstring: Docstring,
    *,
    ignore_init_summary: bool = False,  # noqa: ARG001
    trim_doctest_flags: bool = True,  # noqa: ARG001
    warn_unknown_params: bool = True,  # noqa: ARG001
    warnings: bool = True,  # noqa: ARG001
    **options: Any,  # noqa: ARG001
) -> list[DocstringSection]:
    """Parse a docstring using cdd-python.

    Parameters:
        docstring: The docstring to parse.
        ignore_init_summary: Whether to ignore the summary in __init__ methods' docstrings.
        trim_doctest_flags: Whether to remove doctest flags from Python example blocks.
        warn_unknown_params: Warn about documented parameters not appearing in the signature.
        warnings: Whether to log warnings at all.
        **options: Additional parsing options.

    Returns:
        A list of docstring sections.
    """
    ir: cdd.shared.types.IntermediateRepr = cdd.docstring.parse.docstring(
        docstring.value,
    )
    return ir_to_griffe(ir)


__all__ = ["parse_cdd"]
