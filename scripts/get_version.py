# SPDX-License-Identifier: ISC
#
# ISC License
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

# Get current project version from Git tags or changelog.

import os
import re
from contextlib import suppress
from pathlib import Path

from pdm.backend.hooks.version import (  # ty: ignore[unresolved-import]
    SCMVersion,
    Version,
    default_version_formatter,
    get_version_from_scm,
)

_root = Path(__file__).parent.parent
_changelog = _root / "CHANGELOG.md"
_changelog_version_re = re.compile(r"^## \[(\d+\.\d+\.\d+)\].*$")
_default_scm_version = SCMVersion(Version("0.0.0"), None, False, None, None)  # noqa: FBT003


def get_version() -> str:
    if bypass := (os.environ.get("UV_DYNAMIC_VERSIONING_BYPASS") or os.environ.get("PDM_BUILD_SCM_VERSION")):
        return bypass
    scm_version = get_version_from_scm(_root) or _default_scm_version
    with suppress(OSError, StopIteration):  # noqa: SIM117
        with _changelog.open("r", encoding="utf8") as file:
            match = next(filter(None, map(_changelog_version_re.match, file)))
            changelog_version = Version(match.group(1))
            if scm_version.version < changelog_version:
                scm_version = SCMVersion(changelog_version, None, False, None, None)  # noqa: FBT003
    return default_version_formatter(scm_version)


if __name__ == "__main__":
    print(get_version())
