# src/odoo_doctor/core/baseline.py
"""Baseline mode: suppress pre-existing findings, fail only on new ones."""

from __future__ import annotations

import hashlib
import json
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


def _identity(diag: Diagnostic, *parts: str) -> str:
    norm_path = diag.file_path.replace("\\", "/")
    key = "\0".join((diag.rule, diag.module, norm_path, _snippet(diag), *parts))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def finding_identity(diag: Diagnostic) -> str:
    """Stable identity for a finding: rule + module + path + line snippet + title.

    Line/column numbers are deliberately excluded so an edit elsewhere does not
    invalidate the baseline entry. The snippet (normalized line content) keeps
    distinct findings distinct even within one file; the title keeps findings of
    one rule at one location apart (the manifest rules report every finding at
    line 1, and the title names the field or file). Messages are not hashed:
    several embed line numbers. When the file cannot be read, the snippet is
    empty and identity falls back to rule+module+path+title.
    """
    return _identity(diag, diag.title)


def _legacy_identity(diag: Diagnostic) -> str:
    """Version 1 identity (no title): only used to read old baseline files."""
    return _identity(diag)


class Baseline(set):
    """Loaded baseline ids; `legacy` is True for a version 1 file."""

    legacy = False


def write_baseline(diagnostics: list[Diagnostic], path: Path) -> None:
    ids = sorted({finding_identity(d) for d in diagnostics})
    Path(path).write_text(
        json.dumps({"version": 2, "ids": ids}, indent=2), encoding="utf-8"
    )


def load_baseline(path: Path) -> Baseline:
    loaded = Baseline()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        loaded.update(data["ids"])
        loaded.legacy = data.get("version") == 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return Baseline()
    return loaded


def filter_against_baseline(
    diagnostics: list[Diagnostic], baseline_ids: set[str]
) -> list[Diagnostic]:
    # shortcut: a plain set is treated as version 2 (no old-style matching).
    legacy = getattr(baseline_ids, "legacy", False)
    return [
        d
        for d in diagnostics
        if finding_identity(d) not in baseline_ids
        and not (legacy and _legacy_identity(d) in baseline_ids)
    ]
