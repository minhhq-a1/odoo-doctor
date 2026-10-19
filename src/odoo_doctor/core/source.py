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
import io
import tokenize
from functools import lru_cache
from pathlib import Path

import typer

# Enough for the file being scanned plus the few neighbours parsers touch in turn.
_CACHE_SIZE = 16

_Signature = tuple[str, int, int]

# Skipped-input warnings: one stderr line per file (never stdout, the LSP speaks on it),
# at most _WARN_CAP lines per scan, then one summary line from flush_skipped().
_WARN_CAP = 20
_skipped: set[str] = set()


def warn_skipped(path: Path | str, reason: str) -> None:
    """Say once per scan, on stderr, that a file was skipped and why."""
    key = str(path)
    if key in _skipped:
        return
    _skipped.add(key)
    if len(_skipped) <= _WARN_CAP:
        typer.echo(f"[WARN] skipped {key}: {reason}", err=True)


def flush_skipped() -> None:
    """End of a scan: summarise the warnings the cap held back."""
    extra = len(_skipped) - _WARN_CAP
    if extra > 0:
        typer.echo(f"[WARN] ... and {extra} more skipped", err=True)


def reset_skipped() -> None:
    """Start of a scan (the CLI and the LSP's repeated scans share one process)."""
    _skipped.clear()


# shortcut: CPython's AST conversion recurses once per link of a left-nested chain
# (`1 + 1 + ...`, `a.b.b...`, `a[0][0]...`). 3.10 segfaults at ~134k links (an
# uncatchable crash); 3.12+ raises RecursionError from ~10k, which _parse catches. Only a
# file of at least _GUARD_MIN_SIZE chars can hold that many links, so smaller files are
# never tokenized. Revisit if a supported Python crashes lower.
_GUARD_MIN_SIZE = 200_000
_MAX_CHAIN = 50_000
_CHAIN_OPS = frozenset(
    ("+", "-", "*", "/", "//", "%", "@", "|", "&", "^", "<<", ">>", "**", ".")
)
_CHAIN_RESET = frozenset({",", ";", ":", "=", "{", "}"})


def chain_too_long(source: str) -> bool:
    """True when one expression chains more than _MAX_CHAIN operators (see above)."""
    if len(source) < _GUARD_MIN_SIZE:
        return False
    run = 0
    prev = ""
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            kind, text = tok.type, tok.string
            if kind in (tokenize.NEWLINE, tokenize.NL):
                if kind == tokenize.NEWLINE:
                    run = 0
            elif kind == tokenize.OP:
                if text in _CHAIN_RESET:
                    run = 0
                elif text in _CHAIN_OPS or (text in "([" and prev in (")", "]")):
                    run += 1
                    if run > _MAX_CHAIN:
                        return True
            prev = text
    except (tokenize.TokenError, SyntaxError):
        return False  # let ast.parse report it
    return False


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
    if chain_too_long(source):
        warn_skipped(signature[0], "expression too long to parse safely")
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None  # a known-bad user file: stay quiet
    except (ValueError, RecursionError, MemoryError) as exc:
        warn_skipped(signature[0], f"cannot parse ({type(exc).__name__})")
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
