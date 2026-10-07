"""raw-sql-string-interpolation: trusted identifiers and scripts that never see requests."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.security.raw_sql_interpolation import (
    check_raw_sql_interpolation,
)


def _lines(tmp_path: Path, src: str, name: str = "models/m.py") -> list[int]:
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(dedent(src))
    return [d.line for d in check_raw_sql_interpolation(f, "m", "19.0")]


def test_table_of_any_model_is_a_trusted_identifier(tmp_path: Path):
    """`_table` is set by the model's author and validated by the registry, whichever
    recordset, variable or env lookup it is read from."""
    src = """\
        class M:
            def f(self, attachments, model):
                self.env.cr.execute(f"DELETE FROM {attachments._table} WHERE id IN %s", [(1,)])
                self.env.cr.execute("SELECT 1 FROM {}".format(model._table))
                self.env.cr.execute("SELECT 1 FROM %s" % self.env["res.partner"]._table)
        """
    assert _lines(tmp_path, src) == []


def test_other_attributes_stay_untrusted(tmp_path: Path):
    src = """\
        class M:
            def f(self, model):
                self.env.cr.execute(f"DELETE FROM {model._name} WHERE id = 1")
        """
    assert _lines(tmp_path, src) == [3]


def test_upgrade_scripts_are_skipped_like_migrations(tmp_path: Path):
    """Odoo 18 renamed `migrations/` to `upgrades/`: both run on an admin's database."""
    src = """\
        def migrate(cr, table):
            cr.execute(f"UPDATE {table} SET active = TRUE")
        """
    assert _lines(tmp_path, src, "upgrades/1.0.2/post-x.py") == []
    assert _lines(tmp_path, src, "migrations/1.0.2/post-x.py") == []
    assert _lines(tmp_path, src, "models/x.py") == [2]
