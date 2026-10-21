"""Inputs outside the addons that can change an external linter's findings."""

from __future__ import annotations

import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _tool_identity(executable: str, packages: tuple[str, ...]) -> str:
    path = shutil.which(executable)
    identity = [executable, path or "missing"]
    if path:
        try:
            stat = Path(path).stat()
            identity.extend((str(stat.st_mtime_ns), str(stat.st_size)))
        except OSError:
            identity.append("unavailable")
    for package in packages:
        try:
            identity.append(f"{package}={version(package)}")
        except PackageNotFoundError:
            identity.append(f"{package}=missing")
    return repr(identity)


def cache_dependencies(adapters: dict[str, bool]) -> tuple[str, ...]:
    """The linter executables and versions a result depends on.

    Neither adapter reads the scanned repo's or the user's linter configuration (ruff runs
    ``--isolated``, pylint with an empty rcfile and a scratch cwd), so no config file is an input.
    """
    identities: list[str] = []
    if adapters.get("ruff", True):
        identities.append(_tool_identity("ruff", ("ruff",)))
    if adapters.get("pylint_odoo", True):
        identities.append(
            _tool_identity("pylint", ("pylint", "pylint-odoo", "astroid"))
        )
    return tuple(identities)
