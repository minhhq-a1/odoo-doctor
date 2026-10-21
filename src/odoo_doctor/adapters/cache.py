"""Inputs outside the addons that can change an external linter's findings."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from odoo_doctor.core.config import tomllib
from odoo_doctor.core.git import run_git
from odoo_doctor.core.source import MAX_FILE_BYTES, read_bytes

_RUFF_CONFIG_NAMES = ("pyproject.toml", "ruff.toml", ".ruff.toml")
_IGNORE_NAMES = (".gitignore", ".ignore")


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


def _ruff_configs(roots: list[Path]) -> set[Path]:
    """Include nested/ancestor configs, user defaults and recursive `extend` targets.

    Missing candidate files are retained so creating a nearer config invalidates the
    entry too. Reading all candidate configs is deliberately conservative: it also
    catches changes to config precedence and Python target-version inference.
    """
    candidates: set[Path] = set()
    for root in roots:
        root = root.resolve()
        for parent in (root, *root.parents):
            candidates.update(
                parent / name for name in (*_RUFF_CONFIG_NAMES, *_IGNORE_NAMES)
            )
            candidates.add(parent / ".git" / "info" / "exclude")
        candidates.update(root.rglob("*.toml"))
        for name in _IGNORE_NAMES:
            candidates.update(root.rglob(name))
        # Resolve worktree/common git dirs and explicitly configured global ignores.
        # These read-only commands do not execute repository hooks or project code.
        for args in (
            ["rev-parse", "--git-path", "info/exclude"],
            ["config", "--path", "--get", "core.excludesFile"],
        ):
            try:
                result = run_git(
                    args, root, timeout=10
                )  # the repo's config must not run code
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0 and result.stdout.strip():
                candidates.add(root / Path(result.stdout.strip()).expanduser())

    user_dirs = {
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ruff",
        Path.home() / "Library" / "Application Support" / "ruff",
    }
    if os.environ.get("APPDATA"):
        user_dirs.add(Path(os.environ["APPDATA"]) / "ruff")
    candidates.update(folder / "ruff.toml" for folder in user_dirs)
    candidates.add(
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "git"
        / "ignore"
    )

    pending = list(candidates)
    seen: set[Path] = set()
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        seen.add(path)
        raw = read_bytes(path)  # never opens a FIFO or a huge file in the scanned repo
        if raw is None:
            continue
        try:
            config = tomllib.loads(raw.decode("utf-8"))
        except ValueError:  # includes UnicodeDecodeError
            continue
        if path.name == "pyproject.toml":
            tool = config.get("tool", {})
            config = tool.get("ruff", {}) if isinstance(tool, dict) else {}
        if not isinstance(config, dict):
            continue
        extended = config.get("extend")
        if isinstance(extended, str):
            extended_path = Path(os.path.expandvars(extended)).expanduser()
            pending.append(path.parent / extended_path)
    return seen


def cache_dependencies(
    addon_paths: list[Path], config_root: Path | None, adapters: dict[str, bool]
) -> tuple[set[Path], tuple[str, ...]]:
    files: set[Path] = set()
    identities: list[str] = []
    if adapters.get("ruff", True):
        roots = [*addon_paths, config_root or Path.cwd()]
        files = _ruff_configs(roots)
        identities.append(_tool_identity("ruff", ("ruff",)))
    if adapters.get("pylint_odoo", True):
        # The adapter pins an empty rcfile and scratch cwd, so repository/user
        # pylint configs do not participate. Plugin/dependency versions still do.
        identities.append(
            _tool_identity("pylint", ("pylint", "pylint-odoo", "astroid"))
        )
    return files, tuple(identities)


def ruff_config_problem(module: Path) -> tuple[Path, str] | None:
    """Why ruff must not read the configuration it would find for *module*, else None.

    Ruff opens every config file and every ``extend`` target itself, so a FIFO or
    ``/dev/zero`` behind ``extend = "..."`` hangs it until the adapter's timeout. Walks the
    config files of *module* and its ancestors and their ``extend`` chains and returns
    (offending path, reason) for the first link that is not a regular file, is over
    :data:`MAX_FILE_BYTES` or cannot be read; missing files are fine (ruff reports those fast).
    """
    pending = [
        parent / name
        for parent in (module, *module.parents)
        for name in (*_RUFF_CONFIG_NAMES,)
    ]
    seen: set[str] = set()
    while pending:
        path = pending.pop(0)
        key = os.path.realpath(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            st = os.stat(path)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode):
            return path, "not a regular file"
        if st.st_size > MAX_FILE_BYTES:
            return path, f"larger than {MAX_FILE_BYTES // 2**20} MiB"
        raw = read_bytes(path)
        if raw is None:
            return path, "cannot be read"
        try:
            config = tomllib.loads(raw.decode("utf-8"))
        except ValueError:
            continue  # ruff reports a malformed file itself, quickly
        if path.name == "pyproject.toml":
            tool = config.get("tool", {})
            config = tool.get("ruff", {}) if isinstance(tool, dict) else {}
        extended = config.get("extend") if isinstance(config, dict) else None
        if isinstance(extended, str):
            pending.append(
                path.parent / Path(os.path.expandvars(extended)).expanduser()
            )
    return None
