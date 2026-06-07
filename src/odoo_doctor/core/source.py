# src/odoo_doctor/core/source.py
"""Crash-safe source reader shared by every file-reading parser and rule."""

from __future__ import annotations

from pathlib import Path


def read_source(path: Path) -> str | None:
    """Read a text file for static analysis without ever raising on content.

    Decodes as UTF-8 with undecodable bytes replaced (U+FFFD), so a non-UTF-8
    file never raises UnicodeDecodeError. Returns None only when the file
    cannot be read at all (OSError), so callers skip it instead of aborting.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
