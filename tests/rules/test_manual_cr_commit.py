"""manual-cr-commit: committing the transaction Odoo opened for the request."""

from __future__ import annotations

from pathlib import Path

import pytest

from odoo_doctor.rules.data_integrity.manual_cr_commit import check_manual_cr_commit


def _check(tmp_path: Path, body: str, where="models/m.py"):
    path = tmp_path / "mod" / where
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from odoo import api, models\n\n\nclass A(models.Model):\n    _name = 'x.a'\n\n"
        + body
    )
    return check_manual_cr_commit(path, "mod", "17.0")


def test_commit_inside_write_is_flagged_high(tmp_path: Path):
    diags = _check(
        tmp_path,
        "    def write(self, vals):\n"
        "        res = super().write(vals)\n"
        "        self.env.cr.commit()\n"
        "        return res\n",
    )
    assert len(diags) == 1
    d = diags[0]
    assert (d.rule, d.tier, d.category, d.confidence) == (
        "manual-cr-commit",
        "P1",
        "Data Integrity",
        "high",
    )
    assert d.line == 9
    assert "invalid-commit" in d.help


@pytest.mark.parametrize(
    "header",
    [
        "    def create(self, vals):",
        "    def _compute_total(self):",
        "    @api.constrains('name')\n    def _validate(self):",
        "    @api.onchange('name')\n    def _on_name(self):",
    ],
)
def test_commit_inside_orm_hooks_is_high(tmp_path: Path, header: str):
    diags = _check(tmp_path, f"{header}\n        self._cr.commit()\n")
    assert [d.confidence for d in diags] == ["high"]


def test_commit_in_an_ordinary_method_is_medium(tmp_path: Path):
    diags = _check(
        tmp_path, "    def action_sync(self):\n        self.env.cr.commit()\n"
    )
    assert [d.confidence for d in diags] == ["medium"]


def test_commit_on_a_cursor_the_code_opened_is_fine(tmp_path: Path):
    body = (
        "    def write(self, vals):\n"
        "        with self.pool.cursor() as cr:\n"
        "            cr.commit()\n"
        "        new_cr = self.pool.cursor()\n"
        "        new_cr.commit()\n"
        "        with registry.cursor() as cr2:\n"
        "            env = api.Environment(cr2, 1, {})\n"
        "            env.cr.commit()\n"
    )
    assert _check(tmp_path, body) == []


@pytest.mark.parametrize(
    "header",
    [
        "    def _cron_sync(self):\n        self.env.cr.commit()",
        "    def run_cron(self):\n        self.env.cr.commit()",
        "    def init(self):\n        self.env.cr.commit()",
        (
            "    def sync(self, auto_commit=False):\n        if auto_commit:\n"
            "            self.env.cr.commit()"
        ),
        "    def sync(self):\n        if self._can_commit():\n            self.env.cr.commit()",
        (
            "    def sync(self):\n        if self.env.context.get('commit_batch'):\n"
            "            self.env.cr.commit()"
        ),
        (
            "    def sync(self):\n        if not tools.config['test_enable']:\n"
            "            self.env.cr.commit()"
        ),
        "    def sync(self):\n        self.env.cr.commit()  # pylint: disable=invalid-commit",
        "    def sync(self):\n        self.env.cr.commit()  # pylint: disable=E8102",
    ],
)
def test_intended_commits_are_not_flagged(tmp_path: Path, header: str):
    assert _check(tmp_path, header + "\n") == []


def test_commit_on_other_objects_is_not_a_cursor_commit(tmp_path: Path):
    assert (
        _check(
            tmp_path,
            "    def sync(self, repo, conn):\n        repo.commit()\n        conn.commit()\n",
        )
        == []
    )


def test_tests_and_migrations_are_skipped(tmp_path: Path):
    body = "    def write(self, vals):\n        self.env.cr.commit()\n"
    assert _check(tmp_path, body, where="tests/test_a.py") == []
    assert _check(tmp_path, body, where="migrations/17.0.1.0/post.py") == []
