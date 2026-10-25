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

# Tests for scripts/update_coverage_shields.py.

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
if _ROOT not in sys.path:  # pragma: no cover
    sys.path.insert(0, _ROOT)

from scripts.update_coverage_shields import (  # noqa: E402
    _badge_color,
    _format_percentage,
    build_doc_badge,
    build_test_badge,
    compute_doc_coverage,
    compute_test_coverage,
    main,
    update_readme_content,
)


@pytest.mark.parametrize(
    ("pct", "expected"),
    [
        (100.0, "brightgreen"),
        (95.0, "brightgreen"),
        (92.5, "green"),
        (85.0, "yellowgreen"),
        (75.0, "yellow"),
        (65.0, "orange"),
        (50.0, "red"),
    ],
)
def test_badge_color(pct: float, expected: str) -> None:
    """Badge color matches coverage thresholds."""
    assert _badge_color(pct) == expected


@pytest.mark.parametrize(
    ("pct", "expected"),
    [
        (100.0, "100"),
        (88.341, "88.34"),
        (90.001, "90"),
        (90.5, "90.50"),
    ],
)
def test_format_percentage(pct: float, expected: str) -> None:
    """Percentage formatting omits .00 for integers and uses 2 decimals otherwise."""
    assert _format_percentage(pct) == expected


def test_update_readme_content_inserts_and_updates() -> None:
    """Badges are inserted after existing badges and updated in-place when present."""
    initial = """# Project

[![ci](https://example.com/ci.svg)](https://example.com/ci)

Some description.
"""
    inserted = update_readme_content(initial, 100.0, 88.34)
    assert build_doc_badge(100.0) in inserted
    assert build_test_badge(88.34) in inserted

    updated = update_readme_content(inserted, 94.25, 96.0)
    assert build_doc_badge(94.25) in updated
    assert build_test_badge(96.0) in updated
    assert build_doc_badge(100.0) not in updated
    assert build_test_badge(88.34) not in updated


def test_compute_test_coverage_and_main(tmp_path: Path) -> None:
    """Test coverage computation from JSON and end-to-end README update."""
    cov_json = tmp_path / "coverage.json"
    cov_json.write_text(
        json.dumps({"totals": {"percent_covered": 91.234}}),
        encoding="utf-8",
    )
    assert compute_test_coverage([cov_json]) == 91.234

    with pytest.raises(FileNotFoundError):
        compute_test_coverage([tmp_path / "missing.json"])

    readme = tmp_path / "README.md"
    readme.write_text(
        """# Griffe

[![ci](https://example.com/badge.svg)](https://example.com)
""",
        encoding="utf-8",
    )
    assert main(readme_path=readme, coverage_paths=[cov_json]) == 0
    text = readme.read_text(encoding="utf-8")
    assert "doc_coverage-100%25-brightgreen" in text
    assert "test_coverage-91.23%25-green" in text


def test_compute_doc_coverage() -> None:
    """Public API doc coverage is 100%."""
    assert compute_doc_coverage() == 100.0
