#!/usr/bin/env python3
"""Print the CHANGELOG.md section of one version (the body of its GitHub Release).

Used by ``.github/workflows/release.yml`` and ``publish.yml``. Exits 1 when the
version has no entry or an empty one, so a release can never go out without notes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def notes(changelog: str, version: str) -> str:
    """The text between ``## [version]`` and the next ``---`` rule or ``## [`` heading."""
    match = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^---$|^## \[|\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="for example 0.12.1 (no leading v)")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "CHANGELOG.md",
    )
    args = parser.parse_args(argv)
    text = notes(args.changelog.read_text(encoding="utf-8"), args.version)
    if not text:
        print(f"error: no CHANGELOG entry for {args.version}", file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
