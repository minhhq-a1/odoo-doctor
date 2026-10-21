# src/odoo_doctor/core/scanner.py
"""Scan orchestration: build graph, run rules, filter, score.

Extracted from cli/app.py so the same pipeline can be reused by the fix
command, baseline mode, and (future) remote service without duplicating logic.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo_doctor.core.cache import ScanCache
    from odoo_doctor.core.reuse import ScanReuse

import typer

from odoo_doctor.adapters.pylint_odoo.adapter import PylintOdooAdapter
from odoo_doctor.adapters.ruff.adapter import RuffAdapter
from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.git import reset_git_cache
from odoo_doctor.core.pipeline import (
    derive_capabilities,
    mark_score_eligibility,
    rule_is_enabled,
    run_pipeline_with_stats,
)
from odoo_doctor.core.reuse import Stamper
from odoo_doctor.core.roi import rank_fixes
from odoo_doctor.core.scoring import CATEGORIES, score_diagnostics
from odoo_doctor.core.source import (
    clear_source_cache,
    flush_skipped,
    is_scannable,
    reset_skipped,
    scannable_files,
    skipped_count,
)
from odoo_doctor.core.text import safe_text
from odoo_doctor.discovery.addons import discover_addons
from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.graph.source_index import build_source_index, index_signature
from odoo_doctor.rules.registry import default_registry
from odoo_doctor.rules.suppression import (
    scan_python_suppressions,
    scan_xml_suppressions,
)


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


def _config_repr(cfg: OdooDoctorConfig) -> str:
    """A stable string capturing config fields that affect results."""
    import dataclasses
    import json

    if not dataclasses.is_dataclass(cfg):
        return repr(cfg)
    # sorted keys and sets: repr() of a set follows the per-process hash seed
    return json.dumps(
        dataclasses.asdict(cfg),
        sort_keys=True,
        default=lambda o: sorted(o) if isinstance(o, (set, frozenset)) else repr(o),
    )


def _identity_inputs(
    cfg: OdooDoctorConfig, version: str, force_version: bool
) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    """Everything but the files that decides what a scan reports: the resolved config, the
    version, the active ruleset, plugin rules and linter versions (see ``project_fingerprint``)."""
    from odoo_doctor.core.cache import adapter_identities, plugin_identities

    ruleset = tuple(
        f"{meta.name}@{meta.min_version}" for meta, _ in default_registry.get_rules()
    )
    extra = (
        *plugin_identities(default_registry.get_rules()),
        *adapter_identities(cfg.adapters),
    )
    return (
        _config_repr(cfg),
        f"{version}+forced" if force_version else version,
        ruleset,
        extra,
    )


def _lint_signature(ctx, modules: dict, module_sigs: dict[str, str]) -> str:
    """What a linter run on one addon can see: its files and those of the addons it depends on
    (transitively), since a linter may follow an import into a sibling addon."""
    closure: dict[str, None] = {}
    pending = [ctx.name]
    while pending:
        name = pending.pop()
        if name in closure or name not in modules:
            continue
        closure[name] = None
        pending.extend(modules[name].depends)
    return repr(sorted((n, module_sigs.get(str(modules[n].path), "")) for n in closure))


def _is_native(func: object) -> bool:
    """A rule shipped with odoo-doctor: only these are known to read nothing but their input."""
    mod = getattr(func, "__module__", None) or ""
    return mod == "odoo_doctor" or mod.startswith("odoo_doctor.")


def _is_fixable_rule(rule_name: str) -> bool:
    entry = default_registry.get(rule_name)
    return bool(entry and entry[0].fixable)


def _score_module(
    mod_diags: list[Diagnostic],
    mod_elig: list[bool],
    cfg: OdooDoctorConfig,
    in_scope: list[str],
    stats: dict | None = None,
    python_lines: int = 0,
):
    """Score one module and attach its fix priorities, suppression stats and the inputs
    of the secondary project numbers (score counting medium findings, Python lines)."""
    result = score_diagnostics(
        mod_diags,
        mod_elig,
        category_weights=cfg.category_weights,
        in_scope_categories=in_scope,
    )
    result.fix_priorities = rank_fixes(
        mod_diags,
        mod_elig,
        category_weights=cfg.category_weights,
        in_scope_categories=in_scope,
        is_fixable=_is_fixable_rule,
    )
    result.suppression_stats = stats or {}
    result.python_lines = python_lines
    result.overall_with_medium = score_diagnostics(
        mod_diags,
        mark_score_eligibility(mod_diags, include_medium=True),
        category_weights=cfg.category_weights,
        in_scope_categories=in_scope,
    ).overall
    return result


def _score_per_module(
    diags: list[Diagnostic],
    cfg: OdooDoctorConfig,
    version: str,
    stats: dict | None = None,
    extra_modules=(),
    lines: dict | None = None,
) -> dict[str, object]:
    """Score every module that has findings, plus *extra_modules* (e.g. modules whose
    findings were all suppressed). *stats* is the full {module: {rule: counts}} map."""
    eligible = mark_score_eligibility(diags)
    in_scope = _in_scope_categories(version, cfg)
    scores: dict[str, object] = {}
    # *extra_modules* first (the scan's module order), then any other module with findings:
    # a set here would order the report by the process's hash seed, not as the live scan does.
    modules = dict.fromkeys([*extra_modules, *(d.module for d in diags)])
    for name in modules:
        mod_diags = [d for d in diags if d.module == name]
        mod_elig = [e for d, e in zip(diags, eligible) if d.module == name]
        scores[name] = _score_module(
            mod_diags,
            mod_elig,
            cfg,
            in_scope,
            (stats or {}).get(name),
            (lines or {}).get(name, 0),
        )
    return scores


def detect_scan_version(addon_paths: list[Path], cfg: OdooDoctorConfig) -> str:
    """The Odoo version a scan runs as: config/CLI, else the first addon's manifest."""
    if cfg.odoo_version:
        return cfg.odoo_version
    from odoo_doctor.discovery.addons import discover_addons
    from odoo_doctor.discovery.odoo_version import detect_odoo_version
    from odoo_doctor.parsers.manifest import parse_manifest

    for addon in discover_addons(
        addon_paths, target_modules=cfg.target_modules or None
    ):
        manifest = parse_manifest(addon.path)
        if manifest is not None:
            return detect_odoo_version(manifest_version=manifest.version)
    return "unknown"


def manifest_versions(addon_paths: list[Path], cfg: OdooDoctorConfig) -> dict[str, str]:
    """Module -> Odoo version its own manifest declares (only recognised ``NN.0`` ones).

    Rules are gated on this version, not on the configured one (see build_project_graph).
    """
    from odoo_doctor.discovery.addons import discover_addons
    from odoo_doctor.discovery.odoo_version import detect_odoo_version
    from odoo_doctor.parsers.manifest import parse_manifest

    found: dict[str, str] = {}
    for addon in discover_addons(
        addon_paths, target_modules=cfg.target_modules or None
    ):
        manifest = parse_manifest(addon.path)
        if manifest is not None:
            ver = detect_odoo_version(manifest_version=manifest.version)
            if ver != "unknown":
                found[addon.name] = ver
    return found


def collect_scores(
    addon_paths: list[Path],
    cfg: OdooDoctorConfig,
    version: str,
    changed_files: set[str] | None = None,
    config_root: Path | None = None,
    cache: ScanCache | None = None,
    force_version: bool = False,
    reuse: ScanReuse | None = None,
) -> tuple[list[Diagnostic], dict[str, object]]:
    """Scan *addon_paths* and return the findings and one score per module.

    *reuse* (the language server's) carries results from the previous scan of the project
    (see :mod:`odoo_doctor.core.reuse`); the result is the same as without it.
    """
    from dataclasses import asdict

    from odoo_doctor.core.cache import project_fingerprint

    reset_skipped()  # skipped-file warnings are per scan
    reset_git_cache()
    if changed_files is not None:
        reuse = None  # a --diff scan filters by file: nothing to carry over
    fingerprint: str | None = None
    if cache is not None and changed_files is None:
        config_repr, fp_version, ruleset, extra = _identity_inputs(
            cfg, version, force_version
        )
        fingerprint = project_fingerprint(
            addon_paths=addon_paths,
            config_repr=config_repr,
            version=fp_version,
            ruleset=ruleset,
            extra=extra,
        )
        hit = cache.lookup(fingerprint)
        if hit is not None:
            # the version the live scan ended up with (detected from the manifests)
            version = cache.lookup_version(fingerprint) or version
            diags = [Diagnostic(**d) for d in hit]
            stats = cache.lookup_stats(fingerprint)
            lines = cache.lookup_lines(fingerprint)
            scores = _score_per_module(
                diags,
                cfg,
                version,
                stats=stats,
                extra_modules=[*lines, *stats],
                lines=lines,
            )
            return diags, scores

    stamper: Stamper | None = None
    module_sigs: dict[str, str] = {}
    project_key = ""
    source_index = None
    if reuse is not None:
        reuse.begin(
            hashlib.sha256(
                repr(_identity_inputs(cfg, version, force_version)).encode()
            ).hexdigest()
        )
        stamper = Stamper(reuse.racy)
        for addon in discover_addons(
            addon_paths, target_modules=cfg.target_modules or None, warn=False
        ):
            module_sigs[str(addon.path)] = stamper.tree(addon.path)
        index_sig = (
            index_signature(cfg.odoo_source_path, stamper)
            if cfg.odoo_source_path
            else ""
        )
        project_key = repr((sorted(module_sigs.items()), index_sig))
        if reuse.last is not None and reuse.last[0] == project_key:
            reuse.racy = stamper.racy
            return list(reuse.last[1]), dict(reuse.last[2])
        if cfg.odoo_source_path:
            if reuse.source_index is None or reuse.source_index[0] != index_sig:
                index = build_source_index(cfg.odoo_source_path)
                reuse.source_index = (index_sig, index)
            source_index = reuse.source_index[1]

    graph = build_project_graph(
        addon_paths=addon_paths,
        odoo_version=version,
        target_modules=cfg.target_modules or None,
        odoo_source_path=cfg.odoo_source_path or None,
        force_version=force_version,
        source_index=source_index,
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
            except Exception as exc:  # noqa: BLE001 - a crashing rule must not abort the scan
                typer.echo(
                    f"[WARN] rule {safe_text(meta.name)} crashed on {safe_text(ctx.name)}: {safe_text(exc)}",
                    err=True,
                )

    # Run native file-based rules. Files are the outer loop so each file is read and
    # parsed once and shared by every rule (see core.source) instead of once per
    # rule. Diagnostics are bucketed per rule and concatenated in rule order, so the
    # output order is the same as running the rules one after another.
    file_rules = list(default_registry.get_rules(needs_context=False))
    by_rule: list[list[Diagnostic]] = [[] for _ in file_rules]
    kept_files: dict[tuple, tuple] = {}
    for ctx in graph.modules.values():
        derived_caps = derive_capabilities(ctx.odoo_version, cfg.capabilities)
        enabled = [
            i
            for i, (meta, _) in enumerate(file_rules)
            if rule_is_enabled(meta, ctx.odoo_version, derived_caps)
        ]
        if not enabled:
            continue
        enabled_names = tuple(file_rules[i][0].name for i in enabled)
        for py_file in scannable_files(ctx.path):
            if py_file.name == "__manifest__.py":
                continue
            if (
                changed_files is not None
                and str(py_file.resolve()) not in changed_files
            ):
                continue
            key = (str(py_file), ctx.name, ctx.odoo_version, enabled_names)
            file_sig = None
            if stamper is not None:
                file_sig = stamper.file(py_file)
                hit = reuse.files.get(key)
                if hit is not None and hit[0] == file_sig:
                    kept_files[key] = hit
                    for i in enabled:
                        by_rule[i].extend(hit[1].get(file_rules[i][0].name, ()))
                    continue
            mark = skipped_count()
            clean = True
            produced_by: dict[str, tuple[Diagnostic, ...]] = {}
            for i in enabled:
                meta, func = file_rules[i]
                produced: list[Diagnostic] = []
                try:
                    # extend keeps what a generator rule yielded before it crashed
                    produced.extend(func(py_file, ctx.name, ctx.odoo_version))
                except Exception as exc:  # noqa: BLE001 - a crashing rule must not abort the scan
                    clean = False
                    typer.echo(
                        f"[WARN] rule {safe_text(meta.name)} crashed on {safe_text(py_file.name)}: {safe_text(exc)}",
                        err=True,
                    )
                by_rule[i].extend(produced)
                if _is_native(func):
                    produced_by[meta.name] = tuple(produced)
                else:
                    clean = False  # a plugin may read anything: it runs on every scan
            # a file that made the scan warn is run again, so the warning is repeated
            if reuse is not None and clean and skipped_count() == mark:
                kept_files[key] = (file_sig, produced_by)
    for bucket in by_rule:
        all_diags.extend(bucket)
    clear_source_cache()  # release the parsed trees of the last files

    # Run adapters
    adapters = []
    if cfg.adapters.get("ruff", True):
        adapters.append(RuffAdapter())
    if cfg.adapters.get("pylint_odoo", True):
        adapters.append(PylintOdooAdapter())

    kept_adapters: dict[tuple, tuple[Diagnostic, ...]] = {}
    for adapter in adapters:
        if (
            not adapter.is_available()
            and adapter.config_key not in cfg.explicit_adapters
        ):
            continue
        for ctx in graph.modules.values():
            key = None
            if reuse is not None:
                key = (
                    adapter.name,
                    str(ctx.path),
                    ctx.odoo_version,
                    _lint_signature(ctx, graph.modules, module_sigs),
                )
                hit = reuse.adapters.get(key)
                if hit is not None:
                    kept_adapters[key] = hit
                    all_diags.extend(hit)
                    continue
            try:
                produced = adapter.run(ctx.path, ctx.odoo_version)
            except Exception as exc:  # noqa: BLE001 - a crashing rule must not abort the scan
                typer.echo(
                    f"[WARN] {safe_text(adapter.name)} adapter crashed on {safe_text(ctx.name)}: {safe_text(exc)}",
                    err=True,
                )
                continue
            all_diags.extend(produced)
            # a missing tool, a timeout or a bad output is retried on the next scan
            if key is not None and not any(
                d.rule.startswith("adapter-") and d.rule.endswith("-warning")
                for d in produced
            ):
                kept_adapters[key] = tuple(produced)

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
    python_lines: dict[str, int] = {}
    for ctx in graph.modules.values():
        python_lines[ctx.name] = 0
        for py_file in scannable_files(ctx.path):
            suppressions |= scan_python_suppressions(py_file)
            try:
                python_lines[ctx.name] += len(
                    py_file.read_bytes().decode("utf-8", "replace").splitlines()
                )
            except OSError:
                pass
        for data_file in ctx.manifest.data:
            xml_path = ctx.path / data_file
            if xml_path.suffix == ".xml" and is_scannable(xml_path, ctx.path):
                suppressions |= scan_xml_suppressions(xml_path)

    # Run pipeline
    active_rules = default_registry.active_rules_map()
    diags, eligible, stats = run_pipeline_with_stats(
        all_diags,
        cfg,
        suppressions,
        active_rules,
        version,
        base_path=config_root,
    )
    if changed_files is not None:
        stats = {}  # a --diff scan sees only some files: partial numbers would mislead

    if cache is not None and fingerprint is not None:
        cache.store(
            fingerprint, [asdict(d) for d in diags], stats, python_lines, version
        )

    # Determine in-scope categories
    in_scope = _in_scope_categories(version, cfg)

    # Score per module
    scores: dict[str, object] = {}
    for module_name in graph.modules:
        mod_diags = [d for d in diags if d.module == module_name]
        mod_elig = [elig for d, elig in zip(diags, eligible) if d.module == module_name]
        scores[module_name] = _score_module(
            mod_diags,
            mod_elig,
            cfg,
            in_scope,
            stats.get(module_name),
            python_lines.get(module_name, 0),
        )

    flush_skipped()  # after every stage that can skip a file
    if reuse is not None:
        reuse.files = (
            kept_files  # what this scan did not see (deleted files) is dropped
        )
        reuse.adapters = kept_adapters
        reuse.last = (project_key, list(diags), dict(scores))
    return diags, scores
