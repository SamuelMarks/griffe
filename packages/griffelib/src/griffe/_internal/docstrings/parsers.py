# This module imports all the defined parsers
# and provides a generic function to parse docstrings.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from griffe._internal.docstrings.auto import AutoOptions, parse_auto
from griffe._internal.docstrings.cdd_parser import parse_cdd
from griffe._internal.docstrings.models import DocstringSection, DocstringSectionText
from griffe._internal.enumerations import Parser

if TYPE_CHECKING:
    from collections.abc import Callable

    from griffe._internal.models import Docstring


DocstringStyle = Literal["google", "numpy", "sphinx", "rest", "auto"]
"""The supported docstring styles (literal values of the Parser enumeration)."""
DocstringOptions = AutoOptions
"""The options for each docstring style."""


parsers: dict[Parser, Callable[[Docstring], list[DocstringSection]]] = {
    Parser.auto: parse_auto,
    Parser.google: parse_cdd,
    Parser.sphinx: parse_cdd,
    Parser.numpy: parse_cdd,
    Parser.rest: parse_cdd,
}


def parse(
    docstring: Docstring,
    parser: DocstringStyle | Parser | None,
    **options: Any,
) -> list[DocstringSection]:
    """Parse the docstring.

    Parameters:
        docstring: The docstring to parse.
        parser: The docstring parser to use. If None, return a single text section.
        **options: The options accepted by the parser.

    Returns:
        A list of docstring sections.
    """
    if parser:
        if not isinstance(parser, Parser):
            parser = Parser(parser)
        return parsers[parser](docstring, **options)
    return [DocstringSectionText(docstring.value)] if docstring.value else []
