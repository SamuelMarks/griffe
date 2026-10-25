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

"""Update doc coverage and test coverage shields in README.md."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import griffe

try:
    import griffecli
except ModuleNotFoundError:
    griffecli = None

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from types import ModuleType


PROJECT_DIR = Path(__file__).resolve().parent.parent
README_PATH = PROJECT_DIR / "README.md"
COVERAGE_JSON_PATHS = (
    PROJECT_DIR / "htmlcov" / "coverage.json",
    PROJECT_DIR / "coverage.json",
)
TESTED_MODULES: tuple[ModuleType, ...] = (griffe, griffecli) if griffecli else (griffe,)

DOC_BADGE_RE = re.compile(
    r"\[!\[doc coverage\]\(https://img\.shields\.io/badge/doc_coverage-[^)]+\)\]\([^)]+\)",
)
TEST_BADGE_RE = re.compile(
    r"\[!\[test coverage\]\(https://img\.shields\.io/badge/test_coverage-[^)]+\)\]\([^)]+\)",
)


def _badge_color(percentage: float) -> str:
    """Return a shields.io color name for a coverage percentage.

    Parameters:
        percentage: Coverage percentage between 0 and 100.

    Returns:
        The shields.io color string.
    """
    if percentage >= 95:  # noqa: PLR2004
        return "brightgreen"
    if percentage >= 90:  # noqa: PLR2004
        return "green"
    if percentage >= 80:  # noqa: PLR2004
        return "yellowgreen"
    if percentage >= 70:  # noqa: PLR2004
        return "yellow"
    if percentage >= 60:  # noqa: PLR2004
        return "orange"
    return "red"


def _format_percentage(percentage: float) -> str:
    """Format a percentage value concisely for a badge.

    Parameters:
        percentage: Coverage percentage between 0 and 100.

    Returns:
        Formatted string without trailing `.00` if integral, or two decimals.
    """
    rounded = float(round(percentage, 2))
    if rounded.is_integer():
        return f"{int(rounded)}"
    return f"{rounded:.2f}"


def _load_modules(*modules: ModuleType) -> griffe.GriffeLoader:
    """Load target modules into a GriffeLoader with standard extensions.

    Parameters:
        *modules: Python modules to load.

    Returns:
        Configured and populated GriffeLoader instance.
    """
    extensions = ["unpack_typeddict"]
    try:
        import griffe_inherited_docstrings  # noqa: F401, PLC0415

        extensions.append("griffe_inherited_docstrings")
    except ImportError:
        pass
    loader = griffe.GriffeLoader(
        extensions=griffe.load_extensions(*extensions),
    )
    for module in modules:
        loader.load(module.__name__)
    loader.resolve_aliases()
    return loader


def _get_reexported_names(module: ModuleType) -> Iterable[str]:
    """Return names re-exported from external packages on a module.

    Parameters:
        module: The inspected module.

    Returns:
        An iterable of re-exported attribute names.
    """
    return getattr(module, "_REEXPORTED_EXTERNAL_API", ())


def _yield_public_objects(
    obj: griffe.Module | griffe.Class,
    *,
    modules: bool = False,
    modulelevel: bool = True,
    inherited: bool = False,
    special: bool = False,
) -> Iterator[griffe.Object | griffe.Alias]:
    """Yield public objects recursively from a Griffe module or class.

    Parameters:
        obj: The root module or class.
        modules: Whether to yield submodule objects.
        modulelevel: Whether to stop at module-level objects.
        inherited: Whether to include inherited class members.
        special: Whether to include dunder/special members.

    Yields:
        Public Griffe objects or aliases.
    """
    for member in obj.all_members.values() if inherited else obj.members.values():
        try:
            if member.is_module:
                if member.is_alias:
                    continue
                if member.is_public:
                    if modules:
                        yield member
                    yield from _yield_public_objects(
                        member,  # ty:ignore[invalid-argument-type]
                        modules=modules,
                        modulelevel=modulelevel,
                        inherited=inherited,
                        special=special,
                    )
            elif member.is_public and (special or not member.is_special):
                yield member
            if member.is_class and not modulelevel:
                yield from _yield_public_objects(
                    member,  # ty:ignore[invalid-argument-type]
                    modules=modules,
                    modulelevel=False,
                    inherited=inherited,
                    special=special,
                )
        except (griffe.AliasResolutionError, griffe.CyclicAliasError):
            continue


def compute_doc_coverage(modules: Sequence[ModuleType] = TESTED_MODULES) -> float:
    """Compute public API docstring coverage percentage using Griffe.

    Parameters:
        modules: The modules whose public API should be checked.

    Returns:
        The docstring coverage percentage (0.0 to 100.0).
    """
    loader = _load_modules(*modules)
    total = 0
    covered = 0
    for tested_module in modules:
        public_api = loader.modules_collection[tested_module.__name__]
        reexported = set(_get_reexported_names(tested_module))
        objs = [
            public_api,
            *[
                obj
                for obj in _yield_public_objects(public_api, modulelevel=False, inherited=True, special=False)
                if obj.name not in reexported
            ],
        ]
        for obj in objs:
            total += 1
            if obj.has_docstring:
                covered += 1
    return (covered / total * 100.0) if total else 100.0


def compute_test_coverage(coverage_paths: Iterable[Path] = COVERAGE_JSON_PATHS) -> float:
    """Read test coverage percentage from coverage.py JSON report.

    Parameters:
        coverage_paths: Candidate paths to `coverage.json`.

    Returns:
        The test coverage percentage (0.0 to 100.0).

    Raises:
        FileNotFoundError: If no coverage JSON file is found.
    """
    for path in coverage_paths:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            totals = data["totals"]
            if "percent_covered" in totals:
                return float(totals["percent_covered"])
            return float(totals["percent_covered_display"])
    msg = f"Coverage JSON report not found in: {[str(p) for p in coverage_paths]}"
    raise FileNotFoundError(msg)


def build_doc_badge(percentage: float) -> str:
    """Build the Markdown shield for documentation coverage.

    Parameters:
        percentage: Documentation coverage percentage.

    Returns:
        Markdown badge string.
    """
    pct_str = _format_percentage(percentage)
    color = _badge_color(percentage)
    return (
        f"[![doc coverage](https://img.shields.io/badge/doc_coverage-{pct_str}%25-{color}.svg?style=flat)]"
        "(https://mkdocstrings.github.io/griffe/reference/api/)"
    )


def build_test_badge(percentage: float) -> str:
    """Build the Markdown shield for test coverage.

    Parameters:
        percentage: Test coverage percentage.

    Returns:
        Markdown badge string.
    """
    pct_str = _format_percentage(percentage)
    color = _badge_color(percentage)
    return (
        f"[![test coverage](https://img.shields.io/badge/test_coverage-{pct_str}%25-{color}.svg?style=flat)]"
        "(https://github.com/mkdocstrings/griffe/actions?query=workflow%3Aci)"
    )


def update_readme_content(content: str, doc_pct: float, test_pct: float) -> str:
    """Insert or update doc and test coverage badges in README content.

    Parameters:
        content: Current README.md text.
        doc_pct: Documentation coverage percentage.
        test_pct: Test coverage percentage.

    Returns:
        Updated README.md text.
    """
    doc_badge = build_doc_badge(doc_pct)
    test_badge = build_test_badge(test_pct)

    has_doc = bool(DOC_BADGE_RE.search(content))
    has_test = bool(TEST_BADGE_RE.search(content))

    if has_doc:
        content = DOC_BADGE_RE.sub(doc_badge, content, count=1)
    if has_test:
        content = TEST_BADGE_RE.sub(test_badge, content, count=1)

    if not has_doc or not has_test:
        lines = content.splitlines()
        insert_idx = 0
        for idx, line in enumerate(lines):
            if line.startswith("[!["):
                insert_idx = idx + 1
            elif insert_idx > 0 and not line.startswith("[!["):
                break
        new_badges: list[str] = []
        if not has_doc:
            new_badges.append(doc_badge)
        if not has_test:
            new_badges.append(test_badge)
        lines[insert_idx:insert_idx] = new_badges
        content = "\n".join(lines) + "\n"

    return content


def main(
    readme_path: Path = README_PATH,
    coverage_paths: Iterable[Path] = COVERAGE_JSON_PATHS,
) -> int:
    """Update coverage shields in README.md.

    Parameters:
        readme_path: Path to README.md.
        coverage_paths: Candidate paths to `coverage.json`.

    Returns:
        Exit code (0 on success).
    """
    doc_pct = compute_doc_coverage()
    test_pct = compute_test_coverage(coverage_paths)
    original = readme_path.read_text(encoding="utf-8")
    updated = update_readme_content(original, doc_pct, test_pct)
    if updated != original:
        readme_path.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
