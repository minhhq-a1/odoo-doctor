# src/odoo_doctor/lsp/engine.py
"""Scan one project folder the way `odoo-doctor scan` does, grouped by file."""

from __future__ import annotations

from pathlib import Path

import odoo_doctor.cli.app  # noqa: F401  (importing it registers every native rule)
from odoo_doctor.core.config import load_config
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scanner import collect_scores

_plugins_loaded = False


def _load_plugins_once(allow: list[str] | None) -> None:
    """Plugins register into a process-wide registry, so load them one time only."""
    global _plugins_loaded
    if _plugins_loaded:
        return
    from odoo_doctor.rules.plugins import load_rule_plugins

    load_rule_plugins(allow=allow)
    _plugins_loaded = True


def scan_project(root: Path) -> dict[str, list[Diagnostic]]:
    """Run a full scan of *root* (its config applies) and group findings by file path.

    Whole-project on purpose: cross-module rules need every addon, so a partial scan
    would lose sibling models and report false findings.
    """
    root = Path(root).resolve()
    cfg = load_config(root)
    if cfg.enable_plugins:
        _load_plugins_once(cfg.plugin_allowlist)
    addons_paths = [(root / p).resolve() for p in cfg.addons_paths]
    diagnostics, _scores = collect_scores(
        addon_paths=addons_paths,
        cfg=cfg,
        version=cfg.odoo_version or "unknown",
        config_root=root,
    )
    by_file: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        by_file.setdefault(d.file_path, []).append(d)
    for findings in by_file.values():
        findings.sort(key=lambda d: (d.line, d.rule))
    return by_file
