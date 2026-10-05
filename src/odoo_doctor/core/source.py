# src/odoo_doctor/core/source.py
"""Crash-safe source reader and parser shared by every file-reading parser and rule.

Every rule used to read and ``ast.parse`` each file on its own (about 11 times per
file in a scan). :func:`read_source` and :func:`parse_python` now share a small
cache keyed by path *and* ``(mtime_ns, size)``, so a rewritten file is never served
stale. The cache is bounded (the scanner visits one file at a time and runs every
rule on it), so memory stays flat however large the repository is.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

# Enough for the file being scanned plus the few neighbours parsers touch in turn.
_CACHE_SIZE = 16

_Signature = tuple[str, int, int]


def _signature(path: Path) -> _Signature | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=_CACHE_SIZE)
def _read(signature: _Signature) -> str | None:
    try:
        return Path(signature[0]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


@lru_cache(maxsize=_CACHE_SIZE)
def _parse(signature: _Signature) -> ast.Module | None:
    source = _read(signature)
    if source is None:
        return None
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError):
        return None


def read_source(path: Path) -> str | None:
    """Read a text file for static analysis without ever raising on content.

    Decodes as UTF-8 with undecodable bytes replaced (U+FFFD), so a non-UTF-8
    file never raises UnicodeDecodeError. Returns None only when the file
    cannot be read at all (OSError), so callers skip it instead of aborting.
    """
    signature = _signature(Path(path))
    return None if signature is None else _read(signature)


def parse_python(path: Path) -> ast.Module | None:
    """Parse a Python file once; None if it is unreadable or has a syntax error.

    The returned tree is shared between callers: treat it as read-only.
    """
    signature = _signature(Path(path))
    return None if signature is None else _parse(signature)


def clear_source_cache() -> None:
    """Drop cached sources and trees (end of a scan, or between tests)."""
    _read.cache_clear()
    _parse.cache_clear()
