# src/odoo_doctor/core/baseline.py
"""Baseline mode: suppress pre-existing findings, fail only on new ones."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo_doctor.core.diagnostics import Diagnostic


def _file_lines(path: str) -> list[str]:
    try:
        return Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _snippet(diag: Diagnostic) -> str:
    """Whitespace-normalized content of the finding's line (empty if unreadable).

    Using line *content* rather than line *number* makes the identity stable
    under edits elsewhere in the file, while still distinguishing two findings
    of the same rule in the same file (their code differs). Reads are not cached
    across calls: a baseline run is a single short-lived CLI invocation and the
    file may legitimately be re-read after an edit (the tests rely on this).
    """
    lines = _file_lines(diag.file_path)
    idx = diag.line - 1
    if 0 <= idx < len(lines):
        return " ".join(lines[idx].split())
    return ""


def _identity(diag: Diagnostic, *parts: str, root: Path | None = None) -> str:
    norm_path = diag.file_path.replace("\\", "/")
    if root is not None:
        try:
            norm_path = Path(
                os.path.relpath(Path(norm_path).resolve(), root.resolve())
            ).as_posix()
        except ValueError:  # different Windows drives: retain the absolute path
            pass
    key = "\0".join((diag.rule, diag.module, norm_path, _snippet(diag), *parts))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def finding_identity(diag: Diagnostic, root: Path | None = None) -> str:
    """Stable identity for a finding: rule + module + path + line snippet + title.

    Line/column numbers are deliberately excluded so an edit elsewhere does not
    invalidate the baseline entry. The snippet (normalized line content) keeps
    distinct findings distinct even within one file; the title keeps findings of
    one rule at one location apart (the manifest rules report every finding at
    line 1, and the title names the field or file). Messages are not hashed:
    several embed line numbers. When the file cannot be read, the snippet is
    empty and identity falls back to rule+module+path+title.
    """
    return _identity(diag, diag.title, root=root)


def _legacy_identity(diag: Diagnostic) -> str:
    """Version 1 identity (no title): only used to read old baseline files."""
    return _identity(diag)


class Baseline(set):
    """Loaded ids and their identity format; v3 paths are relative to the scan root."""

    version = 2
    root: Path | None = None


def write_baseline(
    diagnostics: list[Diagnostic], path: Path, root: Path | None = None
) -> None:
    root = Path(root or path.parent).resolve()
    ids = sorted({finding_identity(d, root=root) for d in diagnostics})
    Path(path).write_text(
        json.dumps({"version": 3, "ids": ids}, indent=2), encoding="utf-8"
    )


def load_baseline(path: Path) -> Baseline:
    loaded = Baseline()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        version = data.get("version", 2)
        if version not in (1, 2, 3):
            return loaded
        loaded.update(data["ids"])
        loaded.version = version
        loaded.root = path.parent.resolve()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return Baseline()
    return loaded


def filter_against_baseline(
    diagnostics: list[Diagnostic], baseline_ids: set[str], root: Path | None = None
) -> list[Diagnostic]:
    # shortcut: a plain set is treated as version 2 (no old-style matching).
    version = getattr(baseline_ids, "version", 2)
    identity_root = (
        (root or getattr(baseline_ids, "root", None)) if version == 3 else None
    )
    return [
        d
        for d in diagnostics
        if finding_identity(d, root=identity_root) not in baseline_ids
        and not (version == 1 and _legacy_identity(d) in baseline_ids)
    ]
