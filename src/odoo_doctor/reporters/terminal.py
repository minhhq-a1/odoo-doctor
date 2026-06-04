# src/odoo_doctor/reporters/terminal.py
"""Terminal reporter using rich."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.text import Text

from odoo_doctor.core.scoring import score_label

if TYPE_CHECKING:
    from odoo_doctor.core.diagnostics import Diagnostic
    from odoo_doctor.core.scoring import ScoreResult


_LABEL_COLORS = {
    "Excellent": "green",
    "Good": "blue",
    "Needs work": "yellow",
    "Critical": "red",
}


def render_terminal(
    diagnostics: list[Diagnostic],
    scores: dict[str, ScoreResult],
) -> str:
    """Render diagnostics and scores to a string for terminal output."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=120)

    if not diagnostics and not scores:
        console.print("[green]No diagnostics found. All clean![/green]")
        return buf.getvalue()

    # Score summary per module
    for module, score in scores.items():
        color = _LABEL_COLORS.get(score.label, "white")
        console.print(
            f"\n[bold]{module}[/bold]  Score: [{color}]{score.overall:.0f}/100 ({score.label})[/{color}]"
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

    # Diagnostics grouped by module
    by_module: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        by_module.setdefault(d.module, []).append(d)

    for module, diags in by_module.items():
        console.print(f"\n[bold underline]Findings for {module}[/bold underline]")
        sorted_diags = sorted(diags, key=lambda d: (d.tier, d.file_path, d.line))
        for d in sorted_diags:
            sev_color = "red" if d.severity == "error" else "yellow"
            conf_mark = "" if d.confidence == "high" else f" [{d.confidence}]"
            console.print(
                f"  [{sev_color}]{d.tier}[/{sev_color}] "
                f"{d.file_path}:{d.line} "
                f"[bold]{d.title}[/bold]{conf_mark}"
            )
            console.print(f"      {d.message}")
            console.print(f"      [dim]{d.help}[/dim]")

    if len(scores) > 1:
        overall = sum(score.overall for score in scores.values()) / len(scores)
        label = score_label(overall)
        color = _LABEL_COLORS.get(label, "white")
        console.print(
            f"\n[bold]Project Score:[/bold] [{color}]{overall:.0f}/100 ({label})[/{color}]"
        )

    return buf.getvalue()
