# src/odoo_doctor/cli/app.py
"""Odoo Doctor CLI — main entry point."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import typer

from odoo_doctor.core.config import OdooDoctorConfig, load_config
from odoo_doctor.core.diagnostics import CATEGORIES
from odoo_doctor.core.pipeline import run_pipeline, derive_capabilities, rule_is_enabled
from odoo_doctor.core.scoring import score_diagnostics
from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.reporters.json_report import render_json
from odoo_doctor.reporters.terminal import render_terminal
from odoo_doctor.rules.suppression import (
    scan_python_suppressions,
    scan_xml_suppressions,
)

# Import all rule modules to trigger @rule registration
import odoo_doctor.rules.manifest.missing_required_fields  # noqa: F401
import odoo_doctor.rules.manifest.missing_dependency  # noqa: F401
import odoo_doctor.rules.manifest.data_order_risk  # noqa: F401
import odoo_doctor.rules.security.missing_access_csv  # noqa: F401
import odoo_doctor.rules.security.unknown_model_in_access_csv  # noqa: F401
import odoo_doctor.rules.security.raw_sql_interpolation  # noqa: F401
import odoo_doctor.rules.security.public_controller_sudo  # noqa: F401
import odoo_doctor.rules.xml.duplicate_xml_id  # noqa: F401
import odoo_doctor.rules.xml.missing_xml_ref  # noqa: F401
import odoo_doctor.rules.xml.view_field_not_in_model  # noqa: F401
import odoo_doctor.rules.xml.button_method_not_found  # noqa: F401
import odoo_doctor.rules.performance.search_in_loop  # noqa: F401
import odoo_doctor.rules.performance.unbounded_search  # noqa: F401
import odoo_doctor.rules.correctness.override_missing_super  # noqa: F401
import odoo_doctor.rules.correctness.compute_missing_depends  # noqa: F401

from odoo_doctor.rules.registry import default_registry
from odoo_doctor.adapters.ruff.adapter import RuffAdapter
from odoo_doctor.adapters.pylint_odoo.adapter import PylintOdooAdapter
from odoo_doctor.core.diagnostics import Diagnostic

app = typer.Typer(
    name="odoo-doctor", help="Unified health scoring for Odoo custom addons."
)


@app.command()
def scan(
    path: Optional[str] = typer.Argument(
        None, help="Path to scan for addons; omit to use config addons_paths"
    ),
    odoo_version: Optional[str] = typer.Option(
        None, "--odoo-version", help="Target Odoo version"
    ),
    module: Optional[str] = typer.Option(
        None, "--module", help="Scan only this module"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    format_opt: Optional[str] = typer.Option(
        None, "--format", help="Output format (terminal, json, github)"
    ),
    fail_on: Optional[str] = typer.Option(
        None, "--fail-on", help="Fail if severity found (error|warning)"
    ),
    diff: Optional[str] = typer.Option(
        None, "--diff", help="Only scan files changed vs this branch"
    ),
    score_delta: Optional[str] = typer.Option(
        None, "--score-delta", help="Compute score difference vs this base ref"
    ),
    min_score: Optional[int] = typer.Option(
        None, "--min-score", help="Exit 2 if any module scores below this (0-100)"
    ),
) -> None:
    """Scan Odoo addons and report health score."""
    config_root = (Path(path) if path is not None else Path.cwd()).resolve()

    # Load config
    cfg = load_config(config_root)
    if odoo_version:
        cfg.odoo_version = odoo_version
    _validate_min_score(min_score, "--min-score")
    _validate_min_score(cfg.min_score, "min_score in odoo-doctor.toml")
    if module:
        cfg.target_modules = [module]
    addons_paths = _resolve_addons_paths(path, config_root, cfg)

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
    diags, scores = _collect_scores(
        addon_paths=addons_paths,
        cfg=cfg,
        version=version,
        changed_files=changed_files,
        config_root=config_root,
    )

    if not scores:
        if output_format == "json":
            typer.echo(render_json([], {}))
        elif output_format == "github":
            typer.echo("")
        else:
            typer.echo("No addons found.")
        return

    delta_str = None
    if score_delta:
        base_diags, base_scores = _scan_base_ref(
            config_root=config_root,
            base_ref=score_delta,
            addon_paths=addons_paths,
            cfg=cfg,
            version=version,
        )
        delta_str = _compute_aggregate_delta(scores, base_scores)
        if output_format == "terminal":
            typer.echo(f"Score Delta: {delta_str} (vs base {score_delta})")

    # Output
    if output_format == "json":
        typer.echo(render_json(diags, scores))
    elif output_format == "github":
        from odoo_doctor.reporters.github_annotations import render_github_annotations

        typer.echo(render_github_annotations(diags, config_root))

        # In github output, we also want to post PR comment
        from odoo_doctor.reporters.pr_comment import (
            render_pr_comment_body,
            post_pr_comment,
        )

        body = render_pr_comment_body(
            diags, scores, delta=delta_str, surfaces=cfg.surfaces.get("pr_comment")
        )
        post_pr_comment(body)
    else:
        typer.echo(render_terminal(diags, scores))

    # Fail on severity
    if fail_on:
        if _has_severity_at_or_above(diags, fail_on):
            raise typer.Exit(code=1)

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


@app.command("rules")
def rules_cmd(
    action: str = typer.Argument("list", help="list or explain"),
    rule_name: Optional[str] = typer.Argument(None, help="Rule name to explain"),
) -> None:
    """List rules or explain a specific rule."""
    if action == "list":
        for meta, _ in default_registry.get_rules():
            typer.echo(f"  {meta.name:40s} [{meta.category}, {meta.tier}]")
    elif action == "explain" and rule_name:
        if rule_name in default_registry:
            meta, _ = default_registry.get(rule_name)
            typer.echo(f"Rule: {meta.name}")
            typer.echo(f"Category: {meta.category}")
            typer.echo(f"Tier: {meta.tier}")
            typer.echo(f"Severity: {meta.severity}")
            typer.echo(f"Confidence: {meta.default_confidence}")
            typer.echo(f"Needs module context: {meta.needs_context}")
            typer.echo(f"Min Odoo version: {meta.min_version or 'any'}")
        else:
            typer.echo(f"Unknown rule: {rule_name}")


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
    from importlib.resources import files, as_file

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


def _collect_scores(
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
