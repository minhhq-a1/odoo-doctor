from __future__ import annotations

import json
import subprocess
from typing import Any

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import ScoreResult, score_label
from odoo_doctor.core.config import SurfaceConfig
from odoo_doctor.core.surfaces import filter_for_surface


def render_pr_comment_body(
    diagnostics: list[Diagnostic],
    scores: dict[str, ScoreResult],
    *,
    delta: str | None = None,
    surfaces: SurfaceConfig | None = None,
) -> str:
    """Render the PR comment body in Markdown."""
    lines = ["<!-- odoo-doctor -->"]
    lines.append("## Odoo Doctor Report")

    module_count = len(scores)
    if module_count == 0:
        overall = 100.0
    else:
        overall = sum(score.overall for score in scores.values()) / module_count
    overall = round(overall, 1)
    label = score_label(overall)

    delta_str = (
        f" (▲ {delta} vs base)"
        if delta and delta.startswith("+")
        else (f" ({delta} vs base)" if delta else "")
    )
    lines.append(f"**Project Score:** {overall} / 100 {label}{delta_str}")
    lines.append("")

    if scores:
        lines.append("### Modules")
        lines.append("| Module | Score |")
        lines.append("|---|---|")
        for mod, score in sorted(scores.items()):
            lines.append(f"| {mod} | {score.overall:.1f} {score.label} |")
        lines.append("")

    filtered = diagnostics
    if surfaces:
        filtered = filter_for_surface(diagnostics, surfaces)

    top = sorted(filtered, key=lambda d: (d.tier, d.file_path, d.line))[:10]
    if top:
        lines.append("### Top Findings")
        for d in top:
            lines.append(
                f"- **{d.severity.upper()}** `{d.file_path}:{d.line}`: {d.title} ({d.rule})"
            )

    return "\n".join(lines)


def choose_comment_action(
    existing_comments: list[dict[str, Any]], marker: str
) -> tuple[str, str | None]:
    """Decide whether to create a new comment or update an existing one."""
    for comment in existing_comments:
        if marker in comment.get("body", ""):
            return "update", str(comment.get("id"))
    return "create", None


def post_pr_comment(body: str, marker: str = "<!-- odoo-doctor -->") -> None:
    """Post or update the PR comment using the gh CLI."""
    try:
        # Fetch existing comments for the current PR
        result = subprocess.run(
            ["gh", "pr", "view", "--json", "comments"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return

        data = json.loads(result.stdout)
        comments = data.get("comments", [])
        action, comment_id = choose_comment_action(comments, marker)

        if action == "update" and comment_id:
            # We use gh api to patch the specific comment because gh pr comment edit is sometimes flaky
            subprocess.run(
                [
                    "gh",
                    "api",
                    "-X",
                    "PATCH",
                    f"repos/{{owner}}/{{repo}}/issues/comments/{comment_id}",
                    "-f",
                    f"body={body}",
                ],
                capture_output=True,
                timeout=10,
            )
        else:
            subprocess.run(
                ["gh", "pr", "comment", "-b", body],
                capture_output=True,
                timeout=10,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
