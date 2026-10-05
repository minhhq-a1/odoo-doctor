# src/odoo_doctor/cli/app.py
"""Odoo Doctor CLI — main entry point."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

import odoo_doctor.rules.correctness.compute_missing_depends
import odoo_doctor.rules.correctness.field_no_string_on_required
import odoo_doctor.rules.correctness.hardcoded_company_or_currency
import odoo_doctor.rules.correctness.missing_translation
import odoo_doctor.rules.correctness.monetary_missing_currency_field
import odoo_doctor.rules.correctness.override_missing_super
import odoo_doctor.rules.data_integrity.data_noupdate_risk
import odoo_doctor.rules.data_integrity.missing_ondelete
import odoo_doctor.rules.frontend.asset_bundle_missing
import odoo_doctor.rules.manifest.data_order_risk
import odoo_doctor.rules.manifest.external_dependencies

# Import fixer modules to trigger fixer registration.
import odoo_doctor.rules.manifest.fixers
import odoo_doctor.rules.manifest.license_compatibility
import odoo_doctor.rules.manifest.missing_dependency

# Import all rule modules to trigger @rule registration
import odoo_doctor.rules.manifest.missing_required_fields
import odoo_doctor.rules.manifest.vendored_python_code
import odoo_doctor.rules.performance.create_write_in_loop
import odoo_doctor.rules.performance.expensive_nonstored_compute
import odoo_doctor.rules.performance.n_plus_one_read
import odoo_doctor.rules.performance.search_in_loop
import odoo_doctor.rules.performance.unbounded_search
import odoo_doctor.rules.security.eval_usage
import odoo_doctor.rules.security.missing_access_csv
import odoo_doctor.rules.security.missing_multicompany_rule
import odoo_doctor.rules.security.public_controller_sudo
import odoo_doctor.rules.security.raw_sql_interpolation
import odoo_doctor.rules.security.record_rule_without_domain
import odoo_doctor.rules.security.sudo_without_comment
import odoo_doctor.rules.security.unknown_model_in_access_csv
import odoo_doctor.rules.upgrade_safety.deprecated_api_usage
import odoo_doctor.rules.upgrade_safety.removed_model_still_referenced
import odoo_doctor.rules.xml.button_method_not_found
import odoo_doctor.rules.xml.duplicate_xml_id
import odoo_doctor.rules.xml.missing_xml_ref
import odoo_doctor.rules.xml.orphan_view
import odoo_doctor.rules.xml.view_field_not_in_model  # noqa: F401
from odoo_doctor.core.config import OdooDoctorConfig, SurfaceConfig, load_config
from odoo_doctor.core.config_edit import set_rule_ignored
from odoo_doctor.core.diagnostics import CATEGORIES, Diagnostic
from odoo_doctor.core.fixer import compute_fixes, default_fixers
from odoo_doctor.core.pipeline import derive_capabilities, rule_is_enabled
from odoo_doctor.core.scanner import collect_scores as _collect_scores
from odoo_doctor.core.suppression_stats import rule_noise
from odoo_doctor.core.surfaces import filter_for_surface
from odoo_doctor.reporters.json_report import render_json
from odoo_doctor.reporters.rule_stats import render_rule_stats, render_rule_stats_json
from odoo_doctor.reporters.terminal import render_terminal
from odoo_doctor.rules.docs_gen import render_html, render_markdown, render_rule_text
from odoo_doctor.rules.registry import default_registry

app = typer.Typer(
    name="odoo-doctor", help="Unified health scoring for Odoo custom addons."
)


@app.command()
def scan(
    path: str | None = typer.Argument(
        None, help="Path to scan for addons; omit to use config addons_paths"
    ),
    odoo_version: str | None = typer.Option(
        None, "--odoo-version", help="Target Odoo version"
    ),
    module: str | None = typer.Option(None, "--module", help="Scan only this module"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    format_opt: str | None = typer.Option(
        None, "--format", help="Output format (terminal, json, github, sarif)"
    ),
    fail_on: str | None = typer.Option(
        None, "--fail-on", help="Fail if severity found (error|warning)"
    ),
    diff: str | None = typer.Option(
        None, "--diff", help="Only scan files changed vs this branch"
    ),
    score_delta: str | None = typer.Option(
        None, "--score-delta", help="Compute score difference vs this base ref"
    ),
    min_score: int | None = typer.Option(
        None, "--min-score", help="Exit 2 if any module scores below this (0-100)"
    ),
    cache_enabled: bool = typer.Option(
        False, "--cache", help="Reuse the cached result when nothing relevant changed"
    ),
    baseline: str | None = typer.Option(
        None, "--baseline", help="Suppress findings present in this baseline file"
    ),
    write_baseline_path: str | None = typer.Option(
        None, "--write-baseline", help="Write current findings as a baseline and exit 0"
    ),
    history_path: str | None = typer.Option(
        None, "--history", help="Append this scan's scores to a JSONL history file"
    ),
    badge_path: str | None = typer.Option(
        None,
        "--badge",
        help="Write a score badge: *.svg (image) or *.json (shields.io endpoint)",
    ),
) -> None:
    """Scan Odoo addons and report health score."""
    if (history_path or badge_path) and diff:
        typer.echo(
            "[ERROR] --history/--badge need a full scan; they cannot be combined "
            "with --diff (partial scores would corrupt the trend).",
            err=True,
        )
        raise typer.Exit(code=3)
    config_root = (Path(path) if path is not None else Path.cwd()).resolve()

    # Load config
    cfg = load_config(config_root)
    if odoo_version:
        cfg.odoo_version = odoo_version
    _validate_min_score(min_score, "--min-score")
    _validate_min_score(cfg.min_score, "min_score in odoo-doctor.toml")
    if module:
        cfg.target_modules = [module]
    if (history_path or badge_path) and cfg.target_modules:
        typer.echo(
            "[ERROR] --history/--badge need a full scan; they cannot be combined "
            "with --module / target_modules (a partial score would corrupt the trend).",
            err=True,
        )
        raise typer.Exit(code=3)
    addons_paths = _resolve_addons_paths(path, config_root, cfg)

    if cfg.enable_plugins:
        from odoo_doctor.rules.plugins import load_rule_plugins

        load_rule_plugins(allow=cfg.plugin_allowlist)  # opt-in only

    # Determine changed files for --diff
    changed_files: set[str] | None = None
    if diff:
        changed_files = _get_changed_files(config_root, diff)
        if changed_files is None:
            typer.echo(
                f"[ERROR] --diff: could not resolve changed files for ref '{diff}'. "
                "Ensure this is a git repository and the ref exists.",
                err=True,
            )
            raise typer.Exit(code=3)

    output_format = "terminal"
    if json_output:
        output_format = "json"
    if format_opt:
        output_format = format_opt

    version = cfg.odoo_version or "unknown"

    cache = None
    if cache_enabled and not diff:
        from odoo_doctor.core.cache import ScanCache

        cache = ScanCache(config_root / ".odoo_doctor_cache")
        cache.load()

    diags, scores = _collect_scores(
        addon_paths=addons_paths,
        cfg=cfg,
        version=version,
        changed_files=changed_files,
        config_root=config_root,
        cache=cache,
    )
    if cache is not None:
        cache.save()

    if write_baseline_path:
        from odoo_doctor.core.baseline import write_baseline

        write_baseline(diags, Path(write_baseline_path))
        typer.echo(
            f"Wrote baseline with {len(diags)} finding(s) to {write_baseline_path}"
        )
        return

    if baseline:
        from odoo_doctor.core.baseline import filter_against_baseline, load_baseline
        from odoo_doctor.core.scanner import _score_per_module  # added in plan 04

        ids = load_baseline(Path(baseline))
        diags = filter_against_baseline(diags, ids)

        # Re-score with the suppressed set so score + exit code reflect only new
        # findings. Reuse the SAME scoring helper that collect_scores uses, so
        # eligibility (mark_score_eligibility) and in-scope logic cannot drift.
        stats = {m: s.suppression_stats for m, s in scores.items()}
        scores = _score_per_module(diags, cfg, version, stats=stats)

    if not scores:
        if output_format == "json":
            typer.echo(render_json([], {}))
        elif output_format == "github":
            typer.echo("")
        elif output_format == "sarif":
            from odoo_doctor.reporters.sarif import render_sarif

            typer.echo(render_sarif([], config_root))
        else:
            typer.echo("No addons found.")
        return

    delta_str = None
    if score_delta:
        _base_diags, base_scores = _scan_base_ref(
            config_root=config_root,
            base_ref=score_delta,
            addon_paths=addons_paths,
            cfg=cfg,
            version=version,
        )
        delta_str = _compute_aggregate_delta(scores, base_scores)
        if output_format == "terminal":
            typer.echo(f"Score Delta: {delta_str} (vs base {score_delta})")

    if history_path or badge_path:
        _write_score_artifacts(
            scores, config_root, history_path=history_path, badge_path=badge_path
        )

    # Output
    if output_format == "json":
        typer.echo(render_json(diags, scores))
    elif output_format == "github":
        from odoo_doctor.reporters.github_annotations import render_github_annotations

        typer.echo(render_github_annotations(diags, config_root))
    elif output_format == "sarif":
        from odoo_doctor.reporters.sarif import render_sarif

        typer.echo(render_sarif(diags, config_root))

        # In github output, we also want to post PR comment
        from odoo_doctor.reporters.pr_comment import (
            post_pr_comment,
            render_pr_comment_body,
        )

        body = render_pr_comment_body(
            diags, scores, delta=delta_str, surfaces=cfg.surfaces.get("pr_comment")
        )
        post_pr_comment(body)
    else:
        typer.echo(render_terminal(diags, scores))

    # Fail on severity
    if fail_on:
        ci_policy = cfg.surfaces.get("ci_failure", SurfaceConfig())
        gating = filter_for_surface(diags, ci_policy)
        if _has_severity_at_or_above(gating, fail_on):
            raise typer.Exit(code=1)
        if output_format == "terminal" and _has_severity_at_or_above(diags, fail_on):
            typer.echo(
                f"[INFO] Findings at or above '{fail_on}' did not fail the build: "
                "[surfaces.ci_failure] only counts "
                f"{'/'.join(ci_policy.tiers) or 'all tiers'} at "
                f"{ci_policy.min_confidence or 'any'} confidence.",
                err=True,
            )

    # Fail on min_score: CLI flag overrides config value
    effective_min = min_score if min_score is not None else cfg.min_score
    if effective_min > 0:
        from odoo_doctor.core.scoring import ScoreResult

        failed_modules = [
            (name, score)
            for name, score in scores.items()
            if isinstance(score, ScoreResult) and score.overall < effective_min
        ]
        if failed_modules:
            if output_format not in ("json", "github"):
                for name, score in failed_modules:
                    typer.echo(
                        f"[FAIL] {name}: score {score.overall:.1f} < min {effective_min}",
                        err=True,
                    )
            raise typer.Exit(code=2)


@app.command("fix")
def fix_cmd(
    path: str | None = typer.Argument(
        None, help="Path to scan and fix; omit to use config addons_paths"
    ),
    odoo_version: str | None = typer.Option(
        None, "--odoo-version", help="Target Odoo version"
    ),
    apply: bool = typer.Option(False, "--fix", help="Apply fixes in place"),
    dry_run: bool = typer.Option(
        False, "--fix-dry-run", help="Print a unified diff without writing"
    ),
) -> None:
    """Apply deterministic, high-confidence fixes for fixable rules."""
    if apply == dry_run:
        # Neither or both: ambiguous.
        typer.echo(
            "[ERROR] fix requires exactly one of --fix or --fix-dry-run.",
            err=True,
        )
        raise typer.Exit(code=3)

    config_root = (Path(path) if path is not None else Path.cwd()).resolve()
    cfg = load_config(config_root)
    if odoo_version:
        cfg.odoo_version = odoo_version
    addons_paths = _resolve_addons_paths(path, config_root, cfg)
    version = cfg.odoo_version or "unknown"

    if cfg.enable_plugins:
        from odoo_doctor.rules.plugins import load_rule_plugins

        load_rule_plugins(allow=cfg.plugin_allowlist)  # opt-in only

    diags, _scores = _collect_scores(
        addon_paths=addons_paths,
        cfg=cfg,
        version=version,
        config_root=config_root,
    )

    fixable_rules = {
        meta.name for meta, _ in default_registry.get_rules() if meta.fixable
    }
    result, originals = compute_fixes(
        diags, fixable_rules, default_fixers, root=config_root
    )

    if dry_run:
        diff = result.unified_diff(originals, root=config_root)
        typer.echo(diff if diff else "No fixes available.")
        return

    # apply (file_path is absolute; resolve defensively against config_root)
    for file_path, new_text in result.changed_files.items():
        target = Path(file_path)
        if not target.is_absolute():
            target = config_root / target
        target.write_text(new_text, encoding="utf-8")
    typer.echo(
        f"Applied {result.fixed_count} fix(es) across "
        f"{len(result.changed_files)} file(s); {result.skipped_count} skipped."
    )


def _load_lsp_runner():
    from odoo_doctor.lsp.server import run

    return run


@app.command()
def lsp() -> None:
    """Run the language server on stdio (experimental; needs odoo-doctor[lsp])."""
    try:
        run = _load_lsp_runner()
    except ImportError:
        typer.echo(
            "[ERROR] The language server needs pygls: pip install 'odoo-doctor[lsp]'",
            err=True,
        )
        raise typer.Exit(code=3)
    run()


def _rules_stats(path: str, cache_enabled: bool, json_output: bool) -> None:
    """Scan like `scan` and print per-rule suppression counts and noise."""
    config_root = Path(path).resolve()
    cfg = load_config(config_root)
    addons_paths = _resolve_addons_paths(path, config_root, cfg)
    version = cfg.odoo_version or "unknown"

    if cfg.enable_plugins:
        from odoo_doctor.rules.plugins import load_rule_plugins

        load_rule_plugins(allow=cfg.plugin_allowlist)  # opt-in only

    cache = None
    if cache_enabled:
        from odoo_doctor.core.cache import ScanCache

        cache = ScanCache(config_root / ".odoo_doctor_cache")
        cache.load()

    _diags, scores = _collect_scores(
        addon_paths=addons_paths,
        cfg=cfg,
        version=version,
        config_root=config_root,
        cache=cache,
    )
    if cache is not None:
        cache.save()

    rows = rule_noise({m: s.suppression_stats for m, s in scores.items()})
    typer.echo(
        render_rule_stats_json(rows) if json_output else render_rule_stats(rows),
        nl=json_output,
    )


@app.command("rules")
def rules_cmd(
    action: str = typer.Argument(
        "list", help="list, explain, disable, enable, docs or stats"
    ),
    rule_name: str | None = typer.Argument(
        None, help="Rule name (explain, disable, enable)"
    ),
    path: str = typer.Option(
        ".", "--path", help="Directory holding odoo-doctor.toml (list/disable/enable)"
    ),
    out: str | None = typer.Option(
        None, "--out", help="docs: write the page here instead of stdout"
    ),
    docs_format: str = typer.Option(
        "markdown", "--format", help="docs: markdown or html"
    ),
    check: bool = typer.Option(
        False, "--check", help="docs: exit 1 if --out is not up to date"
    ),
    cache_enabled: bool = typer.Option(
        False, "--cache", help="stats: reuse the cached scan when nothing changed"
    ),
    json_output: bool = typer.Option(False, "--json", help="stats: output JSON"),
) -> None:
    """List, explain, disable or enable rules, generate the rules docs, or show suppression stats."""
    if action == "list":
        disabled = set(load_config(Path(path).resolve()).ignore_rules)
        for meta, _ in default_registry.get_rules():
            mark = "  (disabled)" if meta.name in disabled else ""
            typer.echo(f"  {meta.name:40s} [{meta.category}, {meta.tier}]{mark}")
    elif action == "explain" and rule_name:
        if rule_name in default_registry:
            meta, _ = default_registry.get(rule_name)
            typer.echo(render_rule_text(meta))
        else:
            typer.echo(f"Unknown rule: {rule_name}")
    elif action in ("disable", "enable") and rule_name:
        if rule_name not in default_registry:
            typer.echo(f"[ERROR] Unknown rule: {rule_name}", err=True)
            raise typer.Exit(code=3)
        config_path = Path(path) / "odoo-doctor.toml"
        changed = set_rule_ignored(config_path, rule_name, action == "disable")
        verb = "Disabled" if action == "disable" else "Enabled"
        if changed:
            typer.echo(f"{verb} {rule_name} in {config_path}")
        else:
            typer.echo(f"{rule_name} already {verb.lower()} in {config_path}")
    elif action == "stats":
        _rules_stats(path, cache_enabled, json_output)
    elif action == "docs":
        if docs_format not in ("markdown", "html"):
            typer.echo("[ERROR] --format must be markdown or html.", err=True)
            raise typer.Exit(code=3)
        rendered = render_markdown() if docs_format == "markdown" else render_html()
        if out is None:
            typer.echo(rendered, nl=False)
            return
        target = Path(out)
        if check:
            current = target.read_text(encoding="utf-8") if target.exists() else None
            if current != rendered:
                typer.echo(
                    f"[ERROR] {target} is out of date. "
                    f"Run: odoo-doctor rules docs --out {target}",
                    err=True,
                )
                raise typer.Exit(code=1)
            typer.echo(f"{target} is up to date.")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        typer.echo(f"Wrote {target}")
    else:
        typer.echo(
            "[ERROR] Usage: rules list | explain <rule> | disable <rule> | "
            "enable <rule> | docs [--out FILE] [--format markdown|html] [--check] | "
            "stats [--path DIR] [--cache] [--json]",
            err=True,
        )
        raise typer.Exit(code=3)


@app.command()
def init(
    path: str = typer.Option(".", "--path", help="Where to create odoo-doctor.toml"),
) -> None:
    """Create a default odoo-doctor.toml config file."""
    config_path = Path(path) / "odoo-doctor.toml"
    if config_path.exists():
        typer.echo(f"Config already exists at {config_path}")
        return

    config_path.write_text("""\
[odoo-doctor]
# odoo_version = "17.0"
# addons_paths = ["."]
# odoo_source_path = ""
# min_score = 60

[adapters]
ruff = true
pylint_odoo = true

[severity]
# "search-in-loop" = "warning"

[ignore]
rules = []
files = ["**/migrations/**"]
modules = []

[category_weights]
# Security = 1.0
# Performance = 1.5
""")
    typer.echo(f"Created {config_path}")


@app.command()
def install() -> None:
    """Install agent skills and optional git hooks."""
    import shutil
    from importlib.resources import as_file, files

    try:
        skills_traversable = files("odoo_doctor.skills")
    except ModuleNotFoundError:
        typer.echo("Skills package not found. Reinstall odoo-doctor.")
        raise typer.Exit(code=1)

    dest = Path.cwd() / ".odoo-doctor" / "skills"
    dest.mkdir(parents=True, exist_ok=True)

    with as_file(skills_traversable) as skills_src:
        if not skills_src.exists():
            typer.echo("Skills directory not found in package. Reinstall odoo-doctor.")
            raise typer.Exit(code=1)

        for skill_dir in skills_src.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                target = dest / skill_dir.name
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(skill_dir, target)
                typer.echo(f"  Installed skill: {skill_dir.name}")

    typer.echo(f"Skills installed to {dest}")
    typer.echo("Run 'odoo-doctor scan --diff --json' from your agent.")


def _write_score_artifacts(
    scores: dict[str, object],
    config_root: Path,
    *,
    history_path: str | None,
    badge_path: str | None,
) -> None:
    """Persist --history / --badge outputs. Messages go to stderr."""
    from odoo_doctor import __version__
    from odoo_doctor.core.history import append_record, build_record, git_info
    from odoo_doctor.core.scoring import ScoreResult, project_score

    results = {k: v for k, v in scores.items() if isinstance(v, ScoreResult)}
    if history_path:
        info = git_info(config_root)
        record = build_record(
            results,
            tool_version=__version__,
            commit=info["commit"],
            branch=info["branch"],
        )
        append_record(Path(history_path), record)
        typer.echo(f"Appended score history to {history_path}", err=True)
    if badge_path:
        from odoo_doctor.reporters.badge import (
            render_badge_endpoint,
            render_badge_svg,
        )

        overall = float(project_score(results)["overall"])
        target = Path(badge_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix.lower() == ".json":
            target.write_text(render_badge_endpoint(overall), encoding="utf-8")
        else:
            target.write_text(render_badge_svg(overall), encoding="utf-8")
        typer.echo(f"Wrote badge to {badge_path}", err=True)


history_app = typer.Typer(help="Score history: trend, regressions, legacy import.")
app.add_typer(history_app, name="history")


@history_app.command("show")
def history_show(
    file: str = typer.Argument(..., help="History file (JSONL)"),
    last: int = typer.Option(10, "--last", help="Show the last N records (0 = all)"),
    max_drop: float | None = typer.Option(
        None,
        "--max-drop",
        help="Exit 2 if the newest score dropped by more than this many points",
    ),
) -> None:
    """Show the score trend and flag regressions vs the previous comparable scan."""
    from odoo_doctor.core.history import detect_regressions, load_history, tail

    records, skipped = load_history(Path(file))
    if skipped:
        typer.echo(f"[WARN] skipped {skipped} unreadable line(s) in {file}", err=True)
    if not records:
        typer.echo(f"No history records in {file}.")
        return

    typer.echo(f"{'when (UTC)':26s}{'branch':16s}{'commit':10s}{'score':>7s}  schema")
    for r in tail(records, last):
        note = "*" if r.get("score_schema_inferred") else ""
        typer.echo(
            f"{str(r.get('timestamp'))[:25]:26s}"
            f"{str(r.get('branch') or '-')[:15]:16s}"
            f"{str(r.get('commit') or '-')[:8]:10s}"
            f"{r['project']['overall']:>7.1f}  "
            f"v{r.get('score_schema_version')}{note} {r['project'].get('label', '')}"
        )
    if any(r.get("score_schema_inferred") for r in tail(records, last)):
        typer.echo("* schema inferred from a pre-0.4.0 report (not comparable to v2)")

    threshold = max_drop if max_drop is not None else 0.0
    regressions = detect_regressions(records, threshold)
    for reg in regressions:
        typer.echo(
            f"[REGRESSION] {reg['scope']}: {reg['previous']:.1f} -> "
            f"{reg['latest']:.1f} (-{reg['drop']:.1f})",
            err=True,
        )
    if regressions and max_drop is not None:
        raise typer.Exit(code=2)


@history_app.command("import")
def history_import(
    file: str = typer.Argument(..., help="History file to append to (JSONL)"),
    reports: list[str] = typer.Argument(..., help="scan --json report file(s)"),
    commit: str | None = typer.Option(None, "--commit"),
    branch: str | None = typer.Option(None, "--branch"),
    timestamp: str | None = typer.Option(
        None,
        "--timestamp",
        help="ISO-8601 time to assign (default: each report file's mtime)",
    ),
) -> None:
    """Import `scan --json` reports of any version (incl. <= 0.3.0) into history."""
    import json as _json
    from datetime import datetime, timezone

    from odoo_doctor.core.history import append_record, normalize_report, to_utc_iso

    try:
        forced_ts = to_utc_iso(timestamp) if timestamp else None
    except ValueError:
        typer.echo(f"[ERROR] invalid --timestamp: {timestamp!r}", err=True)
        raise typer.Exit(code=3)

    imported = 0
    for report_file in reports:
        rp = Path(report_file)
        try:
            data = _json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            typer.echo(f"[WARN] {report_file}: unreadable ({exc})", err=True)
            continue
        ts = forced_ts or datetime.fromtimestamp(
            rp.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds")
        record = (
            normalize_report(data, commit=commit, branch=branch, timestamp=ts)
            if isinstance(data, dict)
            else None
        )
        if record is None:
            typer.echo(f"[WARN] {report_file}: no scored modules, skipped", err=True)
            continue
        append_record(Path(file), record)
        imported += 1
        inferred = (
            " (schema inferred as v1)" if record.get("score_schema_inferred") else ""
        )
        typer.echo(f"Imported {report_file}: {record['project']['overall']}{inferred}")
    if imported == 0:
        raise typer.Exit(code=3)


def _scan_base_ref(
    config_root: Path,
    base_ref: str,
    addon_paths: list[Path],
    cfg: OdooDoctorConfig,
    version: str,
) -> tuple[list[Diagnostic], dict[str, object]]:
    import tempfile

    root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=config_root,
        timeout=30,
        check=False,
    )
    if root_result.returncode != 0:
        typer.echo("[ERROR] --score-delta: Not a git repository.", err=True)
        raise typer.Exit(code=3)
    git_root = Path(root_result.stdout.strip()).resolve()

    tmpdir = Path(tempfile.mkdtemp(prefix="odoo-doctor-base-"))
    try:
        wt_add = subprocess.run(
            ["git", "worktree", "add", "--detach", str(tmpdir), base_ref],
            cwd=git_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if wt_add.returncode != 0:
            typer.echo(
                f"[ERROR] --score-delta: Could not resolve base ref '{base_ref}'.",
                err=True,
            )
            typer.echo(wt_add.stderr, err=True)
            raise typer.Exit(code=3)

        # Map addon paths from config_root to tmpdir
        base_addon_paths = []
        for p in addon_paths:
            try:
                rel = p.resolve().relative_to(git_root)
                base_addon_paths.append(tmpdir / rel)
            except ValueError:
                pass

        base_cfg_root = (
            tmpdir / config_root.relative_to(git_root)
            if config_root.is_relative_to(git_root)
            else tmpdir
        )

        return _collect_scores(
            base_addon_paths, cfg, version, config_root=base_cfg_root
        )
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(tmpdir)],
            cwd=git_root,
            capture_output=True,
            check=False,
        )


def _compute_aggregate_delta(
    scores: dict[str, object], base_scores: dict[str, object]
) -> str:
    from odoo_doctor.core.scoring import ScoreResult

    def agg(sc: dict[str, object]) -> float:
        valid = [s for s in sc.values() if isinstance(s, ScoreResult)]
        if not valid:
            return 100.0
        return sum(s.overall for s in valid) / len(valid)

    head_score = agg(scores)
    base_score = agg(base_scores)
    diff = round(head_score - base_score, 1)
    if diff > 0:
        return f"+{diff}"
    elif diff < 0:
        return f"{diff}"
    return "0.0"


def _resolve_addons_paths(
    path_arg: str | None,
    config_root: Path,
    cfg: OdooDoctorConfig,
) -> list[Path]:
    """Resolve scan roots.

    An omitted CLI path means "use configured addons_paths". An explicit path
    means "scan exactly this target", even when the target is '.'.
    """
    if path_arg is not None:
        return [Path(path_arg).resolve()]
    return [(config_root / p).resolve() for p in cfg.addons_paths]


def _get_changed_files(repo_path: Path, base_branch: str) -> set[str] | None:
    try:
        root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=30,
            check=False,
        )
        if root_result.returncode != 0:
            return None
        git_root = Path(root_result.stdout.strip()).resolve()

        result = subprocess.run(
            ["git", "diff", "--name-only", base_branch],
            capture_output=True,
            text=True,
            cwd=git_root,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return None
        return {
            str((git_root / line.strip()).resolve())
            for line in result.stdout.splitlines()
            if line.strip()
        }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _path_is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _has_severity_at_or_above(diagnostics: list[Diagnostic], threshold: str) -> bool:
    ranks = {"info": 1, "warning": 2, "error": 3}
    threshold_rank = ranks.get(threshold)
    if threshold_rank is None:
        return False
    return any(ranks.get(d.severity, 0) >= threshold_rank for d in diagnostics)


def _validate_min_score(value: int | None, source: str) -> None:
    """Reject a min_score outside 0–100 with a clear error (exit 3)."""
    if value is None:
        return
    if not (0 <= value <= 100):
        typer.echo(
            f"[ERROR] {source} must be between 0 and 100, got {value}.",
            err=True,
        )
        raise typer.Exit(code=3)


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


if __name__ == "__main__":
    app()
