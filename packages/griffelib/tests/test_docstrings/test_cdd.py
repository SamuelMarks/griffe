"""Tests for cdd-python docstring parser integration."""

from griffe._internal.docstrings.models import DocstringSectionParameters, DocstringSectionReturns, DocstringSectionText
from tests.test_docstrings.helpers import ParserType


def test_parse_cdd_basic(parse_rest: ParserType) -> None:
    """Test basic functionality of cdd-python parser integration.

    Parameters:
        parse_rest: The parser fixture.
    """
    docstring = """
    A simple summary.

    :param int foo: A foo
    :param str bar: A bar
    :return: Something
    :rtype: bool
    """
    sections, _warnings = parse_rest(docstring)
    assert len(sections) == 3

    assert isinstance(sections[0], DocstringSectionText)
    assert isinstance(sections[1], DocstringSectionParameters)
    assert isinstance(sections[2], DocstringSectionReturns)
