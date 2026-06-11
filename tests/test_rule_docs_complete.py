"""Every registered native rule must be documented in docs/rules.md."""

from __future__ import annotations

from pathlib import Path

import odoo_doctor.cli.app  # noqa: F401  (registers all built-in rules)
from odoo_doctor.rules.registry import default_registry

# write-in-loop is emitted by the create-in-loop detector and documented as an
# alias; it is intentionally not a separate registry entry.
_DOC_ONLY_ALIASES = {"write-in-loop"}


def test_all_rules_documented():
    docs = Path(__file__).resolve().parents[1] / "docs" / "rules.md"
    text = docs.read_text(encoding="utf-8")
    missing = [
        meta.name for meta, _ in default_registry.get_rules() if meta.name not in text
    ]
    assert not missing, f"Undocumented rules: {missing}"
