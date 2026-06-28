# src/odoo_doctor/rules/upgrade_safety/deprecated_api_usage.py
"""Rule: deprecated-api-usage [Upgrade Safety, P1]."""

from __future__ import annotations

import re
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import read_source
from odoo_doctor.rules.registry import rule

_DEPRECATED_PATTERNS: list[tuple[re.Pattern, str, str, str]] = [
    (
        re.compile(r"^\s*from\s+openerp\b"),
        "Import from 'openerp' namespace",
        "The 'openerp' namespace was renamed to 'odoo' in Odoo 10.",
        "Replace 'from openerp' with 'from odoo'.",
    ),
    (
        re.compile(r"^\s*_columns\s*=\s*\{"),
        "Old-style _columns field definition",
        "_columns was removed in Odoo 10. Use new-style field declarations (fields.Char, etc.).",
        "Convert _columns dict entries to class-level field assignments.",
    ),
    (
        re.compile(r"\bosv\.osv\b|\bosv\.osv_memory\b"),
        "Old-style osv.osv base class",
        "osv.osv was removed in Odoo 10. Use models.Model or models.TransientModel.",
        "Replace osv.osv with models.Model and osv.osv_memory with models.TransientModel.",
    ),
    (
        re.compile(r"\.pool\s*\[|\.pool\.get\s*\("),
        "Old-style registry access via .pool",
        "self.pool was deprecated in Odoo 8. Use self.env['model.name'] instead.",
        "Replace self.pool['model'] or self.pool.get('model') with self.env['model'].",
    ),
]


@rule(
    name="deprecated-api-usage",
    category="Upgrade Safety",
    tier="P1",
    severity="warning",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_deprecated_api_usage(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    """Detect deprecated Odoo API patterns."""
    source = read_source(file_path)
    if source is None:
        return []

    diags: list[Diagnostic] = []
    for line_no, line_text in enumerate(source.splitlines(), start=1):
        for pattern, title, message, help_text in _DEPRECATED_PATTERNS:
            if pattern.search(line_text):
                diags.append(
                    Diagnostic(
                        module=module_name,
                        file_path=str(file_path),
                        line=line_no,
                        column=0,
                        rule="deprecated-api-usage",
                        category="Upgrade Safety",
                        severity="warning",
                        tier="P1",
                        source="native",
                        confidence="high",
                        title=title,
                        message=message,
                        help=help_text,
                        odoo_version=odoo_version,
                    )
                )
    return diags
