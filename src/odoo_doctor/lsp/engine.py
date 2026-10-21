# src/odoo_doctor/lsp/engine.py
"""Scan one project folder the way `odoo-doctor scan` does, grouped by file."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import odoo_doctor.cli.app  # noqa: F401  (importing it registers every native rule)
from odoo_doctor.core.config import load_config
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.reuse import ScanReuse
from odoo_doctor.core.scanner import collect_scores
from odoo_doctor.discovery.addons import discover_addons

_plugins_loaded = False

# What each folder's last scan left behind (see core/reuse.py); the lock keeps scans one at a
# time even for callers that do not go through the server's single worker.
_reuse: dict[Path, ScanReuse] = {}
_scan_lock = threading.Lock()


def reuse_enabled() -> bool:
    """Results are carried between scans unless ``ODOO_DOCTOR_LSP_REUSE=0`` is set."""
    return os.environ.get("ODOO_DOCTOR_LSP_REUSE", "1") != "0"


def forget(root: Path) -> None:
    """Drop what is kept for a folder the editor no longer has open."""
    with _scan_lock:
        _reuse.pop(Path(root).resolve(), None)


def _load_plugins_once(allow: list[str] | None) -> None:
    """Plugins register into a process-wide registry, so load them one time only."""
    global _plugins_loaded
    if _plugins_loaded:
        return
    from odoo_doctor.rules.plugins import load_rule_plugins

    load_rule_plugins(allow=allow)
    _plugins_loaded = True


def addons_found(root: Path) -> bool:
    """Whether a scan of *root* would see at least one addon.

    An empty scan result is ambiguous: a clean project and a folder where no addon was
    found (addons nested deeper than ``addons_paths`` reaches) both report no findings.
    """
    root = Path(root).resolve()
    cfg = load_config(root)
    return bool(
        discover_addons([(root / p).resolve() for p in cfg.addons_paths], warn=False)
    )


def scan_project(root: Path) -> dict[str, list[Diagnostic]]:
    """Run a full scan of *root* (its config applies) and group findings by file path.

    Whole-project on purpose: cross-module rules need every addon, so a partial scan
    would lose sibling models and report false findings. Results of unchanged files and
    addons are reused from the previous scan of the folder; they equal a scan from scratch.
    """
    root = Path(root).resolve()
    cfg = load_config(root)
    if cfg.enable_plugins:
        _load_plugins_once(cfg.plugin_allowlist)
    addons_paths = [(root / p).resolve() for p in cfg.addons_paths]
    with _scan_lock:
        reuse = None
        if reuse_enabled():
            reuse = _reuse.setdefault(root, ScanReuse())
        diagnostics, _scores = collect_scores(
            addon_paths=addons_paths,
            cfg=cfg,
            version=cfg.odoo_version or "unknown",
            config_root=root,
            reuse=reuse,
        )
    by_file: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        by_file.setdefault(d.file_path, []).append(d)
    for findings in by_file.values():
        findings.sort(key=lambda d: (d.line, d.rule))
    return by_file
