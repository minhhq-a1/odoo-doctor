# src/odoo_doctor/core/scanner.py
"""Scan orchestration: build graph, run rules, filter, score.

Extracted from cli/app.py so the same pipeline can be reused by the fix
command, baseline mode, and (future) remote service without duplicating logic.
"""

from __future__ import annotations

from pathlib import Path

import typer

from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.pipeline import (
    derive_capabilities,
    rule_is_enabled,
    run_pipeline,
)
from odoo_doctor.core.scoring import score_diagnostics, CATEGORIES
from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.registry import default_registry
from odoo_doctor.rules.suppression import (
    scan_python_suppressions,
    scan_xml_suppressions,
)
from odoo_doctor.adapters.ruff.adapter import RuffAdapter
from odoo_doctor.adapters.pylint_odoo.adapter import PylintOdooAdapter


def _path_is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _in_scope_categories(
    detected_version: str,
    cfg: OdooDoctorConfig,
) -> list[str]:
    """Determine which categories have at least one active rule."""
    derived_caps = derive_capabilities(detected_version, cfg.capabilities)
    rule_categories: set[str] = set()
    for meta, _ in default_registry.get_rules():
        if rule_is_enabled(meta, detected_version, derived_caps):
            rule_categories.add(meta.category)
    return [c for c in CATEGORIES if c in rule_categories]


def collect_scores(
    addon_paths: list[Path],
    cfg: OdooDoctorConfig,
    version: str,
    changed_files: set[str] | None = None,
    config_root: Path | None = None,
) -> tuple[list[Diagnostic], dict[str, object]]:
    graph = build_project_graph(
        addon_paths=addon_paths,
        odoo_version=version,
        target_modules=cfg.target_modules or None,
        odoo_source_path=cfg.odoo_source_path or None,
    )
    if not graph.modules:
        return [], {}

    # Detect version from first module if still unknown
    if version == "unknown" and graph.modules:
        first_ctx = next(iter(graph.modules.values()))
        version = first_ctx.odoo_version

    # Collect all diagnostics
    all_diags: list[Diagnostic] = []
    context_diags: list[Diagnostic] = []

    # Run native context-based rules
    for meta, func in default_registry.get_rules(needs_context=True):
        for ctx in graph.modules.values():
            derived_caps = derive_capabilities(ctx.odoo_version, cfg.capabilities)
            if not rule_is_enabled(meta, ctx.odoo_version, derived_caps):
                continue
            try:
                produced = func(ctx)
                context_diags.extend(produced)
                all_diags.extend(produced)
            except Exception as exc:
                typer.echo(
                    f"[WARN] rule {meta.name} crashed on {ctx.name}: {exc}",
                    err=True,
                )

    # Run native file-based rules
    for meta, func in default_registry.get_rules(needs_context=False):
        for ctx in graph.modules.values():
            derived_caps = derive_capabilities(ctx.odoo_version, cfg.capabilities)
            if not rule_is_enabled(meta, ctx.odoo_version, derived_caps):
                continue
            for py_file in ctx.path.rglob("*.py"):
                if py_file.name.startswith("__"):
                    continue
                if (
                    changed_files is not None
                    and str(py_file.resolve()) not in changed_files
                ):
                    continue
                try:
                    all_diags.extend(func(py_file, ctx.name, ctx.odoo_version))
                except Exception as exc:
                    typer.echo(
                        f"[WARN] rule {meta.name} crashed on {py_file.name}: {exc}",
                        err=True,
                    )

    # Run adapters
    adapters = []
    if cfg.adapters.get("ruff", True):
        adapters.append(RuffAdapter())
    if cfg.adapters.get("pylint_odoo", True):
        adapters.append(PylintOdooAdapter())

    for adapter in adapters:
        if (
            not adapter.is_available()
            and adapter.config_key not in cfg.explicit_adapters
        ):
            continue
        for ctx in graph.modules.values():
            try:
                all_diags.extend(adapter.run(ctx.path, ctx.odoo_version))
            except Exception as exc:
                typer.echo(
                    f"[WARN] {adapter.name} adapter crashed on {ctx.name}: {exc}",
                    err=True,
                )

    # Filter context-based and adapter diagnostics by changed files if --diff
    if changed_files is not None:
        abs_changed = {str(Path(cf).resolve()) for cf in changed_files}
        changed_modules = {
            name
            for name, ctx in graph.modules.items()
            if any(_path_is_relative_to(Path(cf), ctx.path) for cf in abs_changed)
        }
        context_diag_ids = {id(d) for d in context_diags}
        all_diags = [
            d
            for d in all_diags
            if str(Path(d.file_path).resolve()) in abs_changed
            or (id(d) in context_diag_ids and d.module in changed_modules)
        ]

    # Collect suppressions
    suppressions: set[tuple[str, int, str]] = set()
    for ctx in graph.modules.values():
        for py_file in ctx.path.rglob("*.py"):
            suppressions |= scan_python_suppressions(py_file)
        for data_file in ctx.manifest.data:
            xml_path = ctx.path / data_file
            if xml_path.suffix == ".xml" and xml_path.exists():
                suppressions |= scan_xml_suppressions(xml_path)

    # Run pipeline
    active_rules = default_registry.active_rules_map()
    diags, eligible = run_pipeline(
        all_diags,
        cfg,
        suppressions,
        active_rules,
        version,
        base_path=config_root,
    )

    # Determine in-scope categories
    in_scope = _in_scope_categories(version, cfg)

    # Score per module
    scores: dict[str, object] = {}
    for module_name in graph.modules:
        mod_diags = [d for d in diags if d.module == module_name]
        mod_elig = [elig for d, elig in zip(diags, eligible) if d.module == module_name]
        scores[module_name] = score_diagnostics(
            mod_diags,
            mod_elig,
            category_weights=cfg.category_weights,
            in_scope_categories=in_scope,
        )

    return diags, scores
