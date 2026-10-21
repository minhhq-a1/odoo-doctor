# src/odoo_doctor/core/fixer.py
"""Fixer registry and driver for `odoo-doctor fix`.

A fixer is a callable (diagnostic, file_text) -> new_text | None. Returning
None means "this fixer cannot fix this particular diagnostic" (leave the file
untouched). Fixers must be deterministic and idempotent: applying twice yields
the same result as applying once.

Fixers that locate their target by ``diagnostic.line`` must re-check the content at
that place and return None when it no longer matches: ``compute_fixes`` applies the
diagnostics of a file from the last line to the first, but one fixer can still shift
lines for a later one in the same record. Fixers that rewrite a whole file must not
depend on line numbers at all.
"""

from __future__ import annotations

import ast
import difflib
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import chain_too_long, is_scannable, path_within
from odoo_doctor.core.text import safe_text

Fixer = Callable[[Diagnostic, str], "str | None"]


class FixerRegistry:
    def __init__(self) -> None:
        self._by_rule: dict[str, Fixer] = {}
        self._migration: set[str] = set()
        self._applies: dict[str, Callable[[Diagnostic], bool]] = {}

    def register(
        self,
        rule_name: str,
        fixer: Fixer,
        *,
        migration: bool = False,
        applies: Callable[[Diagnostic], bool] | None = None,
    ) -> None:
        """Register *fixer* for *rule_name*.

        ``migration`` fixers change code for a newer Odoo version and only run when the
        caller opts in (``include_migration``). ``applies`` narrows a rule to the
        findings its fixer really handles (a rule can mix mechanical and manual ones).
        """
        self._by_rule[rule_name] = fixer
        self._migration.discard(rule_name)
        self._applies.pop(rule_name, None)
        if migration:
            self._migration.add(rule_name)
        if applies is not None:
            self._applies[rule_name] = applies

    def get(self, rule_name: str) -> Fixer | None:
        return self._by_rule.get(rule_name)

    def is_migration(self, rule_name: str) -> bool:
        return rule_name in self._migration

    def can_fix(self, d: Diagnostic, *, include_migration: bool) -> bool:
        """Does a fixer handle this finding? Only ``high`` confidence ones qualify."""
        if d.rule not in self._by_rule or d.confidence != "high":
            return False
        if d.rule in self._migration and not include_migration:
            return False
        applies = self._applies.get(d.rule)
        return applies is None or applies(d)

    def __contains__(self, rule_name: str) -> bool:
        return rule_name in self._by_rule


default_fixers = FixerRegistry()


@dataclass
class FixResult:
    """Outcome of a fix run over a set of diagnostics."""

    changed_files: dict[str, str]  # path -> new content
    fixed_count: int
    skipped_count: int  # fixable rule, but fixer returned None for that diag
    skipped_diags: list[Diagnostic] = field(default_factory=list)

    def unified_diff(self, original: dict[str, str], root: Path | None = None) -> str:
        """Render a unified diff. Paths are shown relative to *root* when given,
        so the diff is readable regardless of where the repo lives on disk."""
        chunks: list[str] = []
        for path, new_text in sorted(self.changed_files.items()):
            old_text = original.get(path, "")
            display = safe_text(_display_path(path, root))
            diff = difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{display}",
                tofile=f"b/{display}",
            )
            chunks.append("".join(diff))
        return "".join(chunks)


def _display_path(path: str, root: Path | None) -> str:
    norm = path.replace("\\", "/")
    if root is not None:
        try:
            return Path(norm).resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return norm
    return norm


_XML_PARSER_ARGS = {"resolve_entities": False, "no_network": True}


def validate_text(path: str, text: str) -> bool:
    """Is *text* still a well-formed file of the kind its extension says?

    ``.xml`` must parse and ``.py`` must compile to an AST; other files are not checked.
    This is the engine's guarantee that a fixer never leaves a broken file behind.
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".xml":
        try:
            etree.fromstring(text.encode("utf-8"), etree.XMLParser(**_XML_PARSER_ARGS))
        except (etree.XMLSyntaxError, ValueError):
            return False
    elif suffix == ".py":
        if chain_too_long(text):
            return False
        try:
            ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            return False
    return True


def write_fixed(path: Path, text: str) -> None:
    """Write *text* to *path* byte for byte (no newline translation), via a temporary
    file and a rename so an interrupted write never leaves half a file."""
    target = Path(os.path.realpath(path))
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".odoo-doctor-fix-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
        shutil.copymode(target, tmp)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def compute_fixes(
    diagnostics: list[Diagnostic],
    fixable_rules: set[str],
    registry: FixerRegistry,
    root: Path | None = None,
    read_text: Callable[[str], str] | None = None,
    allowed_roots: list[Path] | None = None,
    include_migration: bool = False,
) -> tuple[FixResult, dict[str, str]]:
    """Apply fixers for fixable, high-confidence diagnostics.

    Fixers registered with ``migration=True`` are skipped unless *include_migration*.

    Returns (FixResult, originals) where originals maps path -> original text
    for every file that changed (so callers can render diffs).

    Path contract: Diagnostic.file_path is absolute today (every scan root is
    .resolve()d in _resolve_addons_paths, so ctx.path and thus file_path are
    absolute). We therefore read/write via the path directly, but resolve it
    defensively against *root* so a future relative-path rule cannot silently
    write to the wrong place. *root* is also used only for diff display.

    With *allowed_roots* (the scanned directories) a file that resolves outside all of
    them (a symlink) is never read, fixed or written; it counts as skipped.

    Diagnostics are grouped by file and applied from the last line to the first (ties
    by rule name), so an edit that adds or removes lines cannot move the target of the
    ones still to come. Each fixer receives the running text for its file, enabling
    multiple fixes per file. A result that no longer parses (``validate_text``) is
    dropped and counted as skipped. Files are read and kept byte for byte (CRLF, BOM).
    """

    def _resolve(p: str) -> Path:
        pp = Path(p)
        if not pp.is_absolute() and root is not None:
            pp = Path(root) / pp
        return pp

    if read_text is None:

        def read_text(p):
            target = _resolve(p)
            if not is_scannable(target):
                raise OSError(f"not a readable regular file: {target}")
            return target.read_bytes().decode("utf-8")  # no newline translation

    # Group fixable, high-confidence diagnostics by file.
    by_file: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        if d.rule not in fixable_rules:
            continue
        if not registry.can_fix(d, include_migration=include_migration):
            continue
        by_file.setdefault(d.file_path, []).append(d)

    originals: dict[str, str] = {}
    changed: dict[str, str] = {}
    fixed = 0
    skipped = 0
    skipped_diags: list[Diagnostic] = []

    for path, diags in by_file.items():
        if allowed_roots is not None and not any(
            path_within(_resolve(path), r) for r in allowed_roots
        ):
            skipped += len(diags)
            skipped_diags += diags
            continue
        try:
            text = read_text(path)
        except (OSError, UnicodeDecodeError):
            skipped += len(diags)
            skipped_diags += diags
            continue
        original = text
        for d in sorted(diags, key=lambda x: (-x.line, x.rule)):
            fixer = registry.get(d.rule)
            assert fixer is not None  # filtered above
            new_text = fixer(d, text)
            if new_text is None or (
                new_text != text and not validate_text(path, new_text)
            ):
                skipped += 1
                skipped_diags.append(d)
                continue
            if new_text != text:
                text = new_text
                fixed += 1
        if text != original:
            originals[path] = original
            changed[path] = text

    return FixResult(
        changed_files=changed,
        fixed_count=fixed,
        skipped_count=skipped,
        skipped_diags=skipped_diags,
    ), originals
