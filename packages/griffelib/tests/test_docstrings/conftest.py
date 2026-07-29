"""Pytest fixture for docstrings tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from griffe._internal.docstrings import cdd_parser
from tests.test_docstrings.helpers import ParserType, parser

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def parse_google() -> Iterator[ParserType]:
    """Yield a function to parse Google docstrings.

    Yields:
        A parser function.
    """
    yield from parser(cdd_parser)


@pytest.fixture
def parse_numpy() -> Iterator[ParserType]:
    """Yield a function to parse Numpy docstrings.

    Yields:
        A parser function.
    """
    yield from parser(cdd_parser)


@pytest.fixture
def parse_rest() -> Iterator[ParserType]:
    """Yield a function to parse ReST docstrings.

    Yields:
        A parser function.
    """
    yield from parser(cdd_parser)


@pytest.fixture
def parse_sphinx() -> Iterator[ParserType]:
    """Yield a function to parse Sphinx docstrings.

    Yields:
        A parser function.
    """
    yield from parser(cdd_parser)
