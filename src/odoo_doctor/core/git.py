# src/odoo_doctor/core/git.py
"""The one place odoo-doctor runs git.

The scanned repository is untrusted: its ``.git/config`` and ``.git/hooks`` can name
programs that git itself runs (``core.fsmonitor`` on ``status`` and ``diff``,
``core.hooksPath`` and the repo's own hooks on ``worktree add``, ``core.sshCommand``,
``diff.external``/``textconv`` on ``diff``). Every call goes through :func:`run_git`,
which switches those off and hands git a minimal environment.
"""

from __future__ import annotations

import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import typer

# The environment git gets is a whitelist. HOME, XDG_CONFIG_HOME and GIT_CONFIG_GLOBAL stay:
# the user's own global config (``safe.directory``, identity) is trusted, only the
# repository's is not (``GIT_CONFIG_GLOBAL`` names a file the user or CI chose, never one
# inside the repo). Tokens and every other ``GIT_*`` variable (``GIT_DIR``,
# ``GIT_CONFIG_COUNT``/``PARAMETERS``, ``GIT_SSH_COMMAND`` ...) are not passed on.
# shortcut: /etc/gitconfig is still read; it is admin-owned (Docker images put
# ``safe.directory`` there) and cannot come from the scanned repo.
_ENV_KEEP = (
    "PATH",
    "HOME",
    "XDG_CONFIG_HOME",
    "GIT_CONFIG_GLOBAL",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
)

_HARDENING = (
    "--no-optional-locks",
    "-c",
    "core.fsmonitor=false",
    "-c",
    f"core.hooksPath={os.devnull}",
    "-c",
    "core.sshCommand=",
)


def git_env(extra_config: list[tuple[str, str]] | None = None) -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    # GIT_CONFIG_COUNT/KEY_n/VALUE_n (git 2.31): key and value are separate variables, so
    # a key holding `=` (a filter named `a=b`) cannot be split the way `-c key=value` is.
    for n, (key, value) in enumerate(extra_config or []):
        env[f"GIT_CONFIG_KEY_{n}"] = key
        env[f"GIT_CONFIG_VALUE_{n}"] = value
    if extra_config:
        env["GIT_CONFIG_COUNT"] = str(len(extra_config))
    return env


def _run(
    args: list[str],
    cwd: Path | str,
    timeout: float | None,
    extra_config: list[tuple[str, str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        # git output holds repo-controlled bytes (config values, file names): never raise
        encoding="utf-8",
        errors="surrogateescape",
        cwd=cwd,
        timeout=timeout,
        check=False,
        env=git_env(extra_config),
    )


@lru_cache(maxsize=1)
def _git_version() -> tuple[int, ...]:
    try:
        out = _run(["--version"], os.getcwd(), 30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return (99,)
    found = re.search(r"(\d+)\.(\d+)", out)
    return (int(found[1]), int(found[2])) if found else (99,)


_FILTER_KEY = r"^filter\..*\.(smudge|clean|process)$"


def _filter_names(cwd: Path | str) -> list[str]:
    """Names of the filter drivers the repo (not the user's global config) defines."""
    out = _run(
        ["config", "--show-scope", "--null", "--get-regexp", _FILTER_KEY], cwd, 30
    )
    scoped = out.returncode in (0, 1)
    if not scoped:  # git older than 2.26: no --show-scope; blank every driver
        out = _run(["config", "--null", "--get-regexp", _FILTER_KEY], cwd, 30)
    if out.returncode != 0:
        return []
    parts = out.stdout.split("\0")
    entries = zip(parts[0::2], parts[1::2]) if scoped else (("", p) for p in parts)
    names: list[str] = []
    for scope, entry in entries:
        key = entry.split("\n", 1)[0]
        name = key[len("filter.") : key.rfind(".")]
        if name and name not in names and scope not in ("system", "global"):
            names.append(name)
    return names


@lru_cache(maxsize=32)
def _filter_overrides(cwd: str) -> tuple[tuple[str, str], ...]:
    """``(key, "")`` pairs that blank every ``filter.<name>`` driver the repo defines.

    ``.gitattributes`` selects a clean/smudge/process driver by name and git runs the
    command on ``status`` (clean) and on a checkout such as ``worktree add`` (smudge),
    so a driver defined in the repo's config is code the repo chooses. The user's own
    drivers (global or system config, e.g. git-lfs) are left alone. Cached per
    directory for the scan; :func:`reset_git_cache` starts the next scan afresh.
    """
    pairs: list[tuple[str, str]] = []
    for name in _filter_names(cwd):
        pairs += [
            (f"filter.{name}.{var}", "") for var in ("smudge", "clean", "process")
        ]
        pairs.append((f"filter.{name}.required", "false"))
    return tuple(pairs)


def reset_git_cache() -> None:
    _filter_overrides.cache_clear()


def run_git(
    args: list[str], cwd: Path | str, timeout: float | None = 30
) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` in ``cwd`` without letting the repo's config or hooks run code.

    Never raises on a non-zero exit; raises ``OSError`` (no git) or
    ``subprocess.TimeoutExpired`` like ``subprocess.run``.
    """
    overrides = list(_filter_overrides(str(cwd)))
    command = [*_HARDENING]
    if _git_version() < (2, 31):
        # no GIT_CONFIG_COUNT: `-c`, which cannot express a name containing `=`: refuse
        if any("=" in key for key, _ in overrides):
            typer.echo(
                "[WARN] git skipped: the repository defines a filter driver whose name "
                "git < 2.31 cannot be told to ignore",
                err=True,
            )
            return subprocess.CompletedProcess(["git", *args], 128, "", "refused")
        for key, value in overrides:
            command += ["-c", f"{key}={value}"]
        overrides = []
    return _run([*command, *args], cwd, timeout, overrides)
