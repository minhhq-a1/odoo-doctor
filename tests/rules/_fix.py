"""Run a rule and its fixer over a one-module project and return the fixed texts."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.fixer import FixerRegistry, compute_fixes
from tests.rules._module import module_ctx


def fix_files(
    tmp_path: Path, files: dict[str, str], check, fixer, version: str = "19.0"
):
    """``(diagnostics, {relative file: text after the fix}, FixResult)``.

    Unchanged files keep their original text, so a test can compare any file.
    """
    ctx = module_ctx(tmp_path, files, version=version)
    diags = check(ctx)
    registry = FixerRegistry()
    for rule in {d.rule for d in diags}:
        registry.register(rule, fixer, migration=True)
    result, _ = compute_fixes(
        diags, {d.rule for d in diags}, registry, include_migration=True
    )
    addon = tmp_path / "mod"
    texts = {name: (addon / name).read_text(newline="") for name in files}
    for path, new in result.changed_files.items():
        texts[Path(path).relative_to(addon).as_posix()] = new
    return diags, texts, result
