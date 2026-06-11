# src/odoo_doctor/core/fixer.py
"""Fixer registry and driver for `odoo-doctor fix`.

A fixer is a callable (diagnostic, file_text) -> new_text | None. Returning
None means "this fixer cannot fix this particular diagnostic" (leave the file
untouched). Fixers must be deterministic and idempotent: applying twice yields
the same result as applying once.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from odoo_doctor.core.diagnostics import Diagnostic

Fixer = Callable[[Diagnostic, str], "str | None"]


class FixerRegistry:
    def __init__(self) -> None:
        self._by_rule: dict[str, Fixer] = {}

    def register(self, rule_name: str, fixer: Fixer) -> None:
        self._by_rule[rule_name] = fixer

    def get(self, rule_name: str) -> Fixer | None:
        return self._by_rule.get(rule_name)

    def __contains__(self, rule_name: str) -> bool:
        return rule_name in self._by_rule


default_fixers = FixerRegistry()


@dataclass
class FixResult:
    """Outcome of a fix run over a set of diagnostics."""

    changed_files: dict[str, str]  # path -> new content
    fixed_count: int
    skipped_count: int  # fixable rule, but fixer returned None for that diag

    def unified_diff(self, original: dict[str, str], root: "Path | None" = None) -> str:
        """Render a unified diff. Paths are shown relative to *root* when given,
        so the diff is readable regardless of where the repo lives on disk."""
        chunks: list[str] = []
        for path, new_text in sorted(self.changed_files.items()):
            old_text = original.get(path, "")
            display = _display_path(path, root)
            diff = difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{display}",
                tofile=f"b/{display}",
            )
            chunks.append("".join(diff))
        return "".join(chunks)


def _display_path(path: str, root: "Path | None") -> str:
    norm = path.replace("\\", "/")
    if root is not None:
        try:
            return Path(norm).resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return norm
    return norm


def compute_fixes(
    diagnostics: list[Diagnostic],
    fixable_rules: set[str],
    registry: FixerRegistry,
    root: "Path | None" = None,
    read_text: Callable[[str], str] | None = None,
) -> tuple[FixResult, dict[str, str]]:
    """Apply fixers for fixable, high-confidence diagnostics.

    Returns (FixResult, originals) where originals maps path -> original text
    for every file that changed (so callers can render diffs).

    Path contract: Diagnostic.file_path is absolute today (every scan root is
    .resolve()d in _resolve_addons_paths, so ctx.path and thus file_path are
    absolute). We therefore read/write via the path directly, but resolve it
    defensively against *root* so a future relative-path rule cannot silently
    write to the wrong place. *root* is also used only for diff display.

    Diagnostics are grouped by file and applied in order. Each fixer receives
    the running text for its file, enabling multiple fixes per file.
    """

    def _resolve(p: str) -> Path:
        pp = Path(p)
        if not pp.is_absolute() and root is not None:
            pp = Path(root) / pp
        return pp

    if read_text is None:

        def read_text(p):
            return _resolve(p).read_text(encoding="utf-8")

    # Group fixable, high-confidence diagnostics by file.
    by_file: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        if d.rule not in fixable_rules:
            continue
        if d.confidence != "high":
            continue
        if registry.get(d.rule) is None:
            continue
        by_file.setdefault(d.file_path, []).append(d)

    originals: dict[str, str] = {}
    changed: dict[str, str] = {}
    fixed = 0
    skipped = 0

    for path, diags in by_file.items():
        try:
            text = read_text(path)
        except OSError:
            skipped += len(diags)
            continue
        original = text
        for d in diags:
            fixer = registry.get(d.rule)
            assert fixer is not None  # filtered above
            new_text = fixer(d, text)
            if new_text is None:
                skipped += 1
                continue
            if new_text != text:
                text = new_text
                fixed += 1
        if text != original:
            originals[path] = original
            changed[path] = text

    return FixResult(
        changed_files=changed, fixed_count=fixed, skipped_count=skipped
    ), originals
