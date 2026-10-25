from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any

from odoo_doctor.core.config import SurfaceConfig
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import ScoreResult, score_label
from odoo_doctor.core.surfaces import filter_for_surface
from odoo_doctor.core.text import safe_text


def _md(text: str) -> str:
    """Repo-derived text on one line, without markdown or HTML structure of its own."""
    one_line = " ".join(text.split())
    # a zero-width space after `@` keeps a repo-chosen name from mentioning (notifying) anyone
    return re.sub(r"([\\`|<>\[\]])", r"\\\1", one_line).replace("@", "@\u200b")


def _code(text: str) -> str:
    """A code span that a backtick or newline in ``text`` cannot end early."""
    one_line = " ".join(text.split())
    fence = "`" * (max((len(r) for r in re.findall("`+", one_line)), default=0) + 1)
    return f"{fence} {one_line} {fence}" if "`" in one_line else f"`{one_line}`"


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
            lines.append(f"| {_md(mod)} | {score.overall:.1f} {score.label} |")
        lines.append("")

    filtered = diagnostics
    if surfaces:
        filtered = filter_for_surface(diagnostics, surfaces)

    top = sorted(filtered, key=lambda d: (d.tier, d.file_path, d.line))[:10]
    if top:
        lines.append("### Top Findings")
        for d in top:
            rule_ref = f"[{d.rule}]({d.url})" if d.url else d.rule
            lines.append(
                f"- **{d.severity.upper()}** {_code(f'{d.file_path}:{d.line}')}: {_md(d.title)} ({rule_ref})"
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


def pr_target() -> tuple[str, str] | None:
    """``(owner/repo, number)`` of the pull request this CI run belongs to, None outside one.

    ``gh pr view`` without a number looks the branch up through git, which fails on the
    detached merge ref that Actions checks out; the run's own environment names the PR.
    """
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return None
    number = ""
    try:
        with open(os.environ.get("GITHUB_EVENT_PATH", ""), encoding="utf-8") as fh:
            number = str((json.load(fh).get("pull_request") or {}).get("number", ""))
    except (OSError, ValueError, AttributeError):
        pass
    if not number:  # refs/pull/<n>/merge
        match = re.fullmatch(
            r"refs/pull/(\d+)/(?:merge|head)", os.environ.get("GITHUB_REF", "")
        )
        number = match.group(1) if match else ""
    return (repo, number) if number.isdigit() else None


def _comments(stdout: str) -> list[dict[str, Any]]:
    """The JSON objects in ``stdout``, one after the other (``gh api --jq`` prints one per comment)."""
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    pos = 0
    while pos < len(stdout):
        if stdout[pos].isspace():
            pos += 1
            continue
        obj, pos = decoder.raw_decode(stdout, pos)
        if isinstance(obj, dict):
            found.append(obj)
    return found


def _why(stderr: str) -> str:
    lines = (stderr or "").strip().splitlines()
    return lines[-1][:200] if lines else "gh failed"


def post_pr_comment(body: str, marker: str = "<!-- odoo-doctor -->") -> None:
    """Post or update the PR comment using the gh CLI; say on stderr when that fails."""
    target = pr_target()
    if (
        target is None
    ):  # run by hand from a clone: gh finds the PR of the checked-out branch
        repo, number, cwd = "{owner}/{repo}", None, None
        list_cmd = ["gh", "pr", "view", "--json", "comments"]
        create_cmd = ["gh", "pr", "comment", "-b", body]
    else:
        repo, number = target
        cwd = (
            tempfile.gettempdir()
        )  # not the scanned repo: its git config does not apply
        list_cmd = [
            "gh", "api", "--paginate", f"repos/{repo}/issues/{number}/comments",
            "--jq", ".[] | {id: .id, body: .body}",
        ]  # fmt: skip
        create_cmd = ["gh", "pr", "comment", number, "--repo", repo, "-b", body]
    try:
        result = subprocess.run(
            list_cmd, capture_output=True, text=True, timeout=30, check=False, cwd=cwd
        )
        if result.returncode != 0:
            raise OSError(_why(result.stderr))
        comments = (
            json.loads(result.stdout).get("comments", [])
            if number is None
            else _comments(result.stdout)
        )
        action, comment_id = choose_comment_action(comments, marker)
        if action == "update" and comment_id and number is not None:
            cmd = [
                "gh", "api", "-X", "PATCH",
                f"repos/{repo}/issues/comments/{comment_id}", "-f", f"body={body}",
            ]  # fmt: skip
        else:
            cmd = create_cmd
        done = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False, cwd=cwd
        )
        if done.returncode != 0:
            raise OSError(_why(done.stderr))
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"[WARN] PR comment not posted: {safe_text(str(exc))}", file=sys.stderr)
