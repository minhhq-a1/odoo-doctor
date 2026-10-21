# src/odoo_doctor/reporters/terminal.py
"""Terminal reporter using rich."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape as _rich_escape
from rich.table import Table

from odoo_doctor.core.fixer import default_fixers
from odoo_doctor.core.scoring import score_label, secondary_scores
from odoo_doctor.core.suppression_stats import actionable_count
from odoo_doctor.core.text import safe_text

if TYPE_CHECKING:
    from odoo_doctor.core.diagnostics import Diagnostic
    from odoo_doctor.core.scoring import ScoreResult


def escape(text: str) -> str:
    """Rich-escape repo-derived text after :func:`safe_text` (control characters, ``::``)."""
    return _rich_escape(safe_text(text))


_LABEL_COLORS = {
    "Excellent": "green",
    "Good": "blue",
    "Needs work": "yellow",
    "Critical": "red",
}


# Fixes listed per module in the "Fix first" section.
_FIX_FIRST = 5


def _noise_hint(scores: dict[str, ScoreResult]) -> str:
    """One line when some rule is both noisy and has advice to give (else empty)."""
    stats = {m: getattr(s, "suppression_stats", {}) for m, s in scores.items()}
    count = actionable_count(stats)
    if not count:
        return ""
    return (
        f"\n[yellow]{count} rule(s) look noisy[/yellow] (many suppressions). "
        "Run: odoo-doctor rules stats"
    )


def render_terminal(
    diagnostics: list[Diagnostic],
    scores: dict[str, ScoreResult],
    hidden: int = 0,
) -> str:
    """Render diagnostics and scores to a string for terminal output."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=120)

    if not diagnostics and not scores and not hidden:
        console.print("[green]No diagnostics found. All clean![/green]")
        return buf.getvalue()

    # Score summary per module
    for module, score in scores.items():
        color = _LABEL_COLORS.get(score.label, "white")
        console.print(
            f"\n[bold]{escape(module)}[/bold]  Score: [{color}]{score.overall:.1f}/100 ({score.label})[/{color}]"
        )

        if score.categories:
            table = Table(show_header=True, header_style="bold")
            table.add_column("Category")
            table.add_column("Score", justify="right")
            table.add_column("Findings", justify="right")
            for cs in score.categories:
                if cs.category not in score.in_scope_categories:
                    continue
                table.add_row(cs.category, str(cs.score), str(cs.finding_count))
            console.print(table)

        fixes = getattr(score, "fix_priorities", [])[:_FIX_FIRST]
        if fixes:
            console.print("  [bold]Fix first[/bold] [dim](best score per effort)[/dim]")
            for rank, fp in enumerate(fixes, 1):
                auto = (
                    " [dim]auto-fix (fix --upgrade-to)[/dim]"
                    if fp.fixable and default_fixers.is_migration(fp.rule)
                    else " [dim]auto-fix[/dim]"
                    if fp.fixable
                    else ""
                )
                console.print(
                    f"   {rank}. [bold]{escape(fp.rule)}[/bold] "
                    f"{escape(fp.file_path)}:{fp.line}  "
                    f"[dim]->[/dim] {fp.projected_score:.1f}/100 "
                    f"[dim](+{fp.score_gain:.1f})[/dim]{auto}"
                )

    # Diagnostics grouped by module
    by_module: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        by_module.setdefault(d.module, []).append(d)

    for module, diags in by_module.items():
        console.print(
            f"\n[bold underline]Findings for {escape(module)}[/bold underline]"
        )
        sorted_diags = sorted(diags, key=lambda d: (d.tier, d.file_path, d.line))
        for d in sorted_diags:
            sev_color = "red" if d.severity == "error" else "yellow"
            conf_mark = "" if d.confidence == "high" else escape(f" [{d.confidence}]")
            console.print(
                f"  [{sev_color}]{d.tier}[/{sev_color}] "
                f"{escape(d.file_path)}:{d.line} "
                f"[bold]{escape(d.title)}[/bold]{conf_mark}"
            )
            console.print(f"      {escape(d.message)}")
            console.print(f"      [dim]{escape(d.help)}[/dim]")
            if d.url:
                console.print(f"      [dim]docs: {escape(d.url)}[/dim]")

    # Top findings across project (multi-module only)
    if len(scores) > 1 and diagnostics:
        top = sorted(diagnostics, key=lambda d: (d.tier, d.file_path, d.line))[:5]
        console.print("\n[bold underline]Top Findings[/bold underline]")
        for d in top:
            sev_color = "red" if d.severity == "error" else "yellow"
            console.print(
                f"  [{sev_color}]{d.tier}[/{sev_color}] "
                f"[dim]{escape(d.module)}[/dim] {escape(d.file_path)}:{d.line} "
                f"[bold]{escape(d.title)}[/bold]"
            )

    if len(scores) > 1:
        overall = sum(score.overall for score in scores.values()) / len(scores)
        label = score_label(overall)
        color = _LABEL_COLORS.get(label, "white")
        console.print(
            f"\n[bold]Project Score:[/bold] [{color}]{overall:.1f}/100 ({label})[/{color}]"
        )
        extra = secondary_scores(scores)
        parts = [
            f"{text}: {extra[key]:.1f}"
            for key, text in (
                ("weighted", "Weighted by code size"),
                ("with_medium", "Counting medium findings"),
            )
            if round(abs(round(extra[key], 1) - round(overall, 1)), 1) >= 0.1
        ]
        if parts:
            console.print(f"[dim]{' · '.join(parts)}[/dim]", highlight=False)

    hint = _noise_hint(scores)
    if hint:
        console.print(hint, highlight=False)  # keep rich from styling the digits

    if hidden:
        console.print(
            f"\n{hidden} finding(s) hidden by [surfaces.terminal]. "
            "Show all with --show-low.",
            markup=False,
            highlight=False,
        )

    return buf.getvalue()
