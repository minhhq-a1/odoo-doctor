#!/usr/bin/env python3
"""Fail unless the release tag is ``vX.Y.Z`` and equals the package version.

Used by ``.github/workflows/publish.yml`` before anything is built or uploaded:
the tag, ``pyproject.toml`` and ``odoo_doctor.__version__`` must all agree.
Reads the files as text so it runs before the package is installed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_TAG = re.compile(r"v(\d+\.\d+\.\d+)")


def _declared(path: Path, pattern: str) -> str | None:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def problems(tag: str, root: Path) -> list[str]:
    match = _TAG.fullmatch(tag)
    if not match:
        return [f"{tag!r} is not a release tag of the form vX.Y.Z"]
    wanted = match.group(1)
    found = {
        "pyproject.toml": _declared(root / "pyproject.toml", r'^version = "([^"]+)"'),
        "odoo_doctor.__version__": _declared(
            root / "src" / "odoo_doctor" / "__init__.py", r'^__version__ = "([^"]+)"'
        ),
    }
    return [
        f"tag {tag} says {wanted} but {name} says {version}"
        for name, version in found.items()
        if version != wanted
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="the git tag, for example v0.10.3")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args(argv)
    errors = problems(args.tag, args.root)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
