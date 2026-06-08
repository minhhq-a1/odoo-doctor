from odoo_doctor.core.scoring import ScoreResult
from odoo_doctor.reporters.pr_comment import (
    render_pr_comment_body,
    choose_comment_action,
    post_pr_comment,
)
import subprocess


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
