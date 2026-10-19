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
import subprocess
from pathlib import Path

# HOME and XDG_CONFIG_HOME stay: the user's own global config (``safe.directory``,
# identity) is trusted, only the repository's is not. Tokens and ``GIT_*`` variables
# (``GIT_DIR``, ``GIT_CONFIG_PARAMETERS`` ...) from the caller are not passed on.
# shortcut: /etc/gitconfig is still read; it is admin-owned (Docker images put
# ``safe.directory`` there) and cannot come from the scanned repo.
_ENV_KEEP = (
    "PATH",
    "HOME",
    "XDG_CONFIG_HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
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


def git_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    return env


def _run(
    args: list[str], cwd: Path | str, timeout: float | None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        check=False,
        env=git_env(),
    )


def _filter_overrides(cwd: Path | str) -> list[str]:
    """``-c`` pairs that blank every configured ``filter.<name>`` driver.

    ``.gitattributes`` selects a clean/smudge/process driver by name and git runs the
    command on ``status`` (clean) and on a checkout such as ``worktree add`` (smudge),
    so a driver defined in the repo's config is code the repo chooses. Blanking all of
    them also blanks the user's own (git-lfs): a base-ref checkout then holds LFS
    pointer files, which does not matter to a source scan.
    """
    out = _run(
        ["config", "--null", "--get-regexp", r"^filter\..*\.(smudge|clean|process)$"],
        cwd,
        30,
    )
    args: list[str] = []
    for entry in out.stdout.split("\0") if out.returncode == 0 else []:
        key = entry.split("\n", 1)[0]
        name = key[len("filter.") : key.rfind(".")]
        for var in ("smudge", "clean", "process"):
            args += ["-c", f"filter.{name}.{var}="]
        args += ["-c", f"filter.{name}.required=false"]
    return args


def run_git(
    args: list[str], cwd: Path | str, timeout: float | None = 30
) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` in ``cwd`` without letting the repo's config or hooks run code.

    Never raises on a non-zero exit; raises ``OSError`` (no git) or
    ``subprocess.TimeoutExpired`` like ``subprocess.run``.
    """
    return _run([*_HARDENING, *_filter_overrides(cwd), *args], cwd, timeout)
