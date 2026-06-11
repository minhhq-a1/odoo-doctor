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


def _snippet(diag: "Diagnostic") -> str:
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


def finding_identity(diag: "Diagnostic") -> str:
    """Stable identity for a finding: rule + module + path + line snippet.

    Line/column numbers are deliberately excluded so an edit elsewhere does not
    invalidate the baseline entry. The snippet (normalized line content) keeps
    distinct findings distinct even within one file. When the file cannot be
    read, the snippet is empty and identity falls back to rule+module+path —
    acceptable because that only collapses findings of the same rule in an
    unreadable file, which is rare and fails safe (over-suppress, not crash).
    """
    norm_path = diag.file_path.replace("\\", "/")
    key = f"{diag.rule}\0{diag.module}\0{norm_path}\0{_snippet(diag)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def write_baseline(diagnostics: list["Diagnostic"], path: Path) -> None:
    ids = sorted({finding_identity(d) for d in diagnostics})
    Path(path).write_text(
        json.dumps({"version": 1, "ids": ids}, indent=2), encoding="utf-8"
    )


def load_baseline(path: Path) -> set[str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return set(data.get("ids", []))


def filter_against_baseline(
    diagnostics: list["Diagnostic"], baseline_ids: set[str]
) -> list["Diagnostic"]:
    return [d for d in diagnostics if finding_identity(d) not in baseline_ids]
