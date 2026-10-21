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
import os
import stat
import tokenize
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

import typer

from odoo_doctor.core.text import safe_text

# Enough for the file being scanned plus the few neighbours parsers touch in turn.
_CACHE_SIZE = 16

_Signature = tuple[str, int, int]

# Skipped-input warnings: one stderr line per file (never stdout, the LSP speaks on it),
# at most _WARN_CAP lines per scan, then one summary line from flush_skipped().
_WARN_CAP = 20
_skipped: set[str] = set()


def warn_skipped(path: Path | str, reason: str, *, read_anyway: bool = False) -> None:
    """Say once per scan, on stderr, that a file was skipped (or only partly read) and why.

    Nothing is parsed on a ``--cache`` hit, so the warnings appear once per change of
    the project; run without ``--cache`` to see them again.
    """
    key = str(path)
    if key in _skipped:
        return
    _skipped.add(key)
    if len(_skipped) <= _WARN_CAP:
        what = f"{key}: {reason}" if read_anyway else f"skipped {key}: {reason}"
        typer.echo(f"[WARN] {safe_text(what)}", err=True)


# A scanned file larger than this is skipped with a warning; real addon sources are far smaller.
MAX_FILE_BYTES = 16 * 1024 * 1024


def is_scannable(path: Path | str, root: Path | str | None = None) -> bool:
    """True when ``path`` is a regular file that is safe to open and read.

    Looks at the type with ``os.stat`` *before* any ``open`` (opening a FIFO blocks
    forever, ``/dev/zero`` never ends). A FIFO, device or socket, a file over
    :data:`MAX_FILE_BYTES`, and (with ``root``) a symlink or ``..`` path that leaves
    ``root`` are skipped with a :func:`warn_skipped` line. A directory or a missing or
    broken path is skipped silently.
    """
    try:
        st = os.stat(path)
    except OSError:
        return False
    if stat.S_ISDIR(st.st_mode):
        return False
    if not stat.S_ISREG(st.st_mode):
        warn_skipped(path, "not a regular file")
        return False
    if st.st_size > MAX_FILE_BYTES:
        warn_skipped(path, f"larger than {MAX_FILE_BYTES // 2**20} MiB")
        return False
    if root is not None and not path_within(path, root):
        warn_skipped(path, "points outside the scanned directory")
        return False
    return True


def path_within(path: Path | str, root: Path | str) -> bool:
    """True when ``path`` (symlinks resolved) lies inside ``root`` (symlinks resolved).

    Lexically inside and no symlink or ``..`` involved is the cheap common case; an
    absolute path outside ``root`` (``root / "/etc/x"``) takes the resolving branch.
    """
    try:
        if (
            not os.path.islink(path)
            and ".." not in Path(path).parts
            and os.path.commonpath([os.path.abspath(path), os.path.abspath(root)])
            == os.path.abspath(root)
        ):
            return True
        real_root = os.path.realpath(root)
        return os.path.commonpath([os.path.realpath(path), real_root]) == real_root
    except ValueError:  # another drive (Windows)
        return False


def scannable_files(root: Path, pattern: str = "*.py") -> Iterator[Path]:
    """``root.rglob(pattern)`` limited to files :func:`is_scannable` accepts."""
    for path in root.rglob(pattern):
        if is_scannable(path, root):
            yield path


_LINT_SUFFIXES = (".py", ".pyi", ".pyw", ".ipynb")


def lint_targets(root: Path) -> list[Path]:
    """What to hand an external linter (ruff, pylint): ``[root]``, or the regular ``.py`` files.

    A linter walks the directory and opens everything it finds, so a FIFO named ``x.py``
    would hang it. When the tree holds such a file (see :func:`is_scannable`) the linter
    gets the other ``.py`` files one by one instead; an ordinary tree is unchanged.
    """
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            path = Path(dirpath, name)
            if name.endswith(_LINT_SUFFIXES) and not is_scannable(path, root):
                return sorted(scannable_files(root))
    return [root]


def flush_skipped() -> None:
    """End of a scan: summarise the warnings the cap held back."""
    extra = len(_skipped) - _WARN_CAP
    if extra > 0:
        typer.echo(f"[WARN] ... and {extra} more skipped", err=True)


def skipped_count() -> int:
    """How many files this scan has warned about so far."""
    return len(_skipped)


def reset_skipped() -> None:
    """Start of a scan (the CLI and the LSP's repeated scans share one process)."""
    _skipped.clear()


# shortcut: best effort, NOT a proof. CPython's AST conversion recurses once per link of a
# left-nested chain (`1 + 1 + ...`, `a.b.b...`, `a[0][0]...`, `f(1)(2)...`, also inside
# brackets). 3.10 segfaults at ~136k links (an uncatchable crash, measured for ~20 shapes);
# 3.12+ raises RecursionError from ~10k, which _parse catches. A chain that long needs at
# least ~270k chars, so only files of _GUARD_MIN_SIZE chars are tokenized, and one chain
# (counted per bracket depth, reset by `, ; = :` at that depth) over _MAX_CHAIN links
# (2.7x below the crash) is skipped. On Python < 3.12 an f-string is one STRING token, so
# its operator characters are counted as a whole. Known residual risk: a shape this count
# does not model (found by a new fuzz, an exotic token mix) can still crash 3.10.
_GUARD_MIN_SIZE = 100_000
_MAX_CHAIN = 50_000
_CHAIN_OPS = frozenset(
    ("+", "-", "*", "/", "//", "%", "@", "|", "&", "^", "<<", ">>", "**", ".")
)
_OPENERS = frozenset("([{")
_CLOSERS = frozenset(")]}")
_RESETS = frozenset((",", ";", "=", ":"))
_FSTRING_OP_CHARS = "+-*/.([|&^%@<>"


def chain_too_long(source: str) -> bool:
    """True when one expression chains more than _MAX_CHAIN links (see above)."""
    if len(source) < _GUARD_MIN_SIZE:
        return False
    depth = [0]  # chain links seen so far at each open bracket depth
    prev = ""
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            kind, text = tok.type, tok.string
            if kind == tokenize.NEWLINE:
                depth = [0]
            elif kind == tokenize.STRING:
                head = text[:3].lower()
                if (
                    "f" in head.split('"')[0].split("'")[0]
                    and sum(map(text.count, _FSTRING_OP_CHARS)) > _MAX_CHAIN
                ):
                    return True
            elif kind == tokenize.OP:
                if text in _OPENERS:
                    if text != "{" and prev in (")", "]"):
                        depth[-1] += 1  # f(..)(..) / a[..][..]: one more link
                    depth.append(0)
                elif text in _CLOSERS:
                    if len(depth) > 1:
                        depth.pop()
                elif text in _RESETS:
                    depth[-1] = 0
                elif text in _CHAIN_OPS:
                    depth[-1] += 1
                if depth[-1] > _MAX_CHAIN:
                    return True
            prev = text
    except (tokenize.TokenError, SyntaxError):
        return False  # let ast.parse report it
    return False


def _signature(path: Path, root: Path | None = None) -> _Signature | None:
    if not is_scannable(path, root):
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), st.st_mtime_ns, st.st_size)


def _open_regular(path: str) -> int | None:
    """A read descriptor, or None when ``path`` is not (any longer) a regular file.

    ``is_scannable`` and the read are two steps: a file swapped for a FIFO in between
    would block ``open``. Opening non-blocking and checking ``fstat`` on the descriptor
    closes that window.
    """
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    if stat.S_ISREG(os.fstat(fd).st_mode):
        return fd
    os.close(fd)
    warn_skipped(path, "not a regular file")
    return None


def read_bytes(path: Path | str, root: Path | str | None = None) -> bytes | None:
    """The bytes of a regular file up to :data:`MAX_FILE_BYTES`, else None (never blocks)."""
    if not is_scannable(path, root):
        return None
    try:
        fd = _open_regular(str(path))
        if fd is None:
            return None
        with os.fdopen(fd, "rb") as fh:
            data = fh.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    return data if len(data) <= MAX_FILE_BYTES else None


@lru_cache(maxsize=_CACHE_SIZE)
def _read(signature: _Signature) -> str | None:
    try:
        fd = _open_regular(signature[0])
        if fd is None:
            return None
        # bounded even if the file grew or lies about its size since is_scannable
        with os.fdopen(fd, encoding="utf-8", errors="replace") as fh:
            text = fh.read(MAX_FILE_BYTES + 1)
    except OSError:
        return None
    if len(text) > MAX_FILE_BYTES:
        warn_skipped(signature[0], f"larger than {MAX_FILE_BYTES // 2**20} MiB")
        return None
    return text


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


def read_source(path: Path, root: Path | None = None) -> str | None:
    """Read a text file for static analysis without ever raising on content.

    Decodes as UTF-8 with undecodable bytes replaced (U+FFFD), so a non-UTF-8
    file never raises UnicodeDecodeError. Returns None only when the file
    cannot be read at all (OSError), so callers skip it instead of aborting. With
    ``root`` a path that resolves outside it (a symlinked manifest) is skipped too.
    """
    signature = _signature(Path(path), root)
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
