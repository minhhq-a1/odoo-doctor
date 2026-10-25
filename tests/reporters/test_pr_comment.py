import json
import subprocess

from odoo_doctor.core.scoring import ScoreResult
from odoo_doctor.reporters.pr_comment import (
    choose_comment_action,
    post_pr_comment,
    pr_target,
    render_pr_comment_body,
)


def test_body_contains_marker():
    scores = {"m1": ScoreResult(100.0, "A", [], [], 0)}
    body = render_pr_comment_body([], scores)
    assert body.startswith("<!-- odoo-doctor -->")


def test_body_contains_scores():
    scores = {"my_addon": ScoreResult(85.5, "B", [], [], 0)}
    body = render_pr_comment_body([], scores)
    assert "85.5" in body
    assert "my_addon" in body


def test_body_includes_delta_when_provided():
    scores = {"m1": ScoreResult(100.0, "A", [], [], 0)}
    body = render_pr_comment_body([], scores, delta="+3.0")
    assert "+3.0" in body


def test_choose_action_updates_when_marker_present():
    comments = [
        {"id": "123", "body": "some comment"},
        {"id": "456", "body": "<!-- odoo-doctor -->\nScore: 80.0"},
    ]
    action, comment_id = choose_comment_action(comments, "<!-- odoo-doctor -->")
    assert action == "update"
    assert comment_id == "456"


def test_choose_action_creates_when_absent():
    comments = [
        {"id": "123", "body": "some comment"},
    ]
    action, comment_id = choose_comment_action(comments, "<!-- odoo-doctor -->")
    assert action == "create"
    assert comment_id is None


def test_post_pr_comment_handles_missing_gh(monkeypatch):
    def mock_run(*args, **kwargs):
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Should not raise
    post_pr_comment("body", "<!-- odoo-doctor -->")


def test_hostile_names_cannot_break_out_of_the_markdown_structure():
    from odoo_doctor.core.diagnostics import Diagnostic

    d = Diagnostic(
        module="m",
        file_path="/r/a\n## injected `x|\n.py",
        line=3,
        column=1,
        rule="r",
        category="c",
        severity="error",
        tier="P1",
        source="native",
        confidence="high",
        title="t\n## title",
        message="m",
        help="h",
        odoo_version="17",
    )
    scores = {"mod|\n## cell": ScoreResult(50.0, "Needs work", [], [], 0)}
    body = render_pr_comment_body([d], scores)
    lines = body.splitlines()
    assert not [
        x for x in lines if x.startswith("## ") and x != "## Odoo Doctor Report"
    ]
    # the table keeps exactly one row per module, the finding exactly one line
    assert len([x for x in lines if x.startswith("| mod")]) == 1
    assert len([x for x in lines if x.startswith("- **ERROR**")]) == 1
    assert sum(1 for x in lines if x.startswith("- ")) == 1


def test_an_at_mention_in_repo_text_does_not_notify():
    from odoo_doctor.core.diagnostics import Diagnostic

    d = Diagnostic(
        module="@octocat",
        file_path="a.py",
        line=1,
        column=0,
        rule="r",
        category="c",
        severity="error",
        tier="P1",
        source="native",
        confidence="high",
        title="ping @octocat and @org/team",
        message="m",
        help="h",
        odoo_version="17",
    )
    scores = {"@octocat": ScoreResult(90.0, "A", [], [], 0)}
    body = render_pr_comment_body([d], scores)
    assert "@octocat" not in body and "@org/team" not in body
    assert "@\u200boctocat" in body


def _fake_gh(monkeypatch, responses):
    """Record every gh call; ``responses`` maps the subcommand to (returncode, stdout)."""
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("cwd")))
        code, out = responses.get(cmd[1], (0, ""))
        return subprocess.CompletedProcess(cmd, code, out, "boom" if code else "")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def _in_pr(monkeypatch, tmp_path, number=7):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": number}}))
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/addons")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.delenv("GITHUB_REF", raising=False)


def test_pr_target_reads_the_event_then_the_merge_ref(monkeypatch, tmp_path):
    _in_pr(monkeypatch, tmp_path)
    assert pr_target() == ("acme/addons", "7")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setenv("GITHUB_REF", "refs/pull/12/merge")
    assert pr_target() == ("acme/addons", "12")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    assert pr_target() is None
    monkeypatch.setenv("GITHUB_REPOSITORY", "not a repo")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/12/merge")
    assert pr_target() is None


def test_in_a_pr_the_comment_is_created_with_repo_and_number(monkeypatch, tmp_path):
    _in_pr(monkeypatch, tmp_path)
    calls = _fake_gh(monkeypatch, {"api": (0, '{"id": 5, "body": "unrelated"}\n')})
    post_pr_comment("body", "<!-- m -->")
    assert calls[0][0][:4] == [
        "gh",
        "api",
        "--paginate",
        "repos/acme/addons/issues/7/comments",
    ]
    assert calls[1][0] == [
        "gh",
        "pr",
        "comment",
        "7",
        "--repo",
        "acme/addons",
        "-b",
        "body",
    ]
    assert all(cwd != "" and cwd is not None for _, cwd in calls)


def test_in_a_pr_the_sticky_comment_is_patched_by_numeric_id(monkeypatch, tmp_path):
    _in_pr(monkeypatch, tmp_path)
    listing = '{"id": 5, "body": "x"}\n{\n  "id": 99,\n  "body": "<!-- m --> old"\n}\n'
    calls = _fake_gh(monkeypatch, {"api": (0, listing)})
    post_pr_comment("body", "<!-- m -->")
    assert calls[1][0][:4] == ["gh", "api", "-X", "PATCH"]
    assert calls[1][0][4] == "repos/acme/addons/issues/comments/99"


def test_a_failing_gh_is_reported_on_stderr(monkeypatch, tmp_path, capsys):
    _in_pr(monkeypatch, tmp_path)
    _fake_gh(monkeypatch, {"api": (1, "")})
    post_pr_comment("body", "<!-- m -->")
    assert "[WARN] PR comment not posted: boom" in capsys.readouterr().err
