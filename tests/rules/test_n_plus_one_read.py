"""n-plus-one-read flags reads on a record browsed one id at a time inside a loop.

Odoo prefetches: iterating a recordset and reading `line.product_id.name` costs one query
per field for the whole recordset, not one per record. The prefetch is lost when each
iteration builds its own singleton with `browse(<one id>)`, which is the real N+1.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.performance.n_plus_one_read import check_n_plus_one_read


def _lines(tmp_path: Path, src: str, name: str = "models/m.py") -> list[int]:
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(dedent(src))
    return [d.line for d in check_n_plus_one_read(f, "m", "19.0")]


def test_iterating_a_recordset_is_prefetched_and_not_flagged(tmp_path: Path):
    src = """\
        class M:
            def f(self, order):
                for line in order.line_ids:
                    name = line.product_id.name
                for rec in self:
                    rec.partner_id.country_id.code
        """
    assert _lines(tmp_path, src) == []


def test_browse_one_id_per_iteration_then_read_is_flagged(tmp_path: Path):
    src = """\
        class M:
            def f(self, ids):
                for rec_id in ids:
                    rec = self.env["res.partner"].browse(rec_id)
                    name = rec.country_id.name
        """
    assert _lines(tmp_path, src) == [5]


def test_inline_browse_read_is_flagged(tmp_path: Path):
    src = """\
        class M:
            def f(self, vals_list):
                for vals in vals_list:
                    vals["name"] = self.env["ir.actions.actions"].browse(vals["action_id"]).name
        """
    assert _lines(tmp_path, src) == [4]


def test_comprehension_over_ids_is_flagged(tmp_path: Path):
    src = """\
        class M:
            def f(self, ids):
                return [self.env["res.partner"].browse(i).name for i in ids]
        """
    assert _lines(tmp_path, src) == [3]


def test_id_derived_inside_the_loop_still_counts(tmp_path: Path):
    src = """\
        class M:
            def f(self, rows):
                for row in rows:
                    partner_id = row[0]
                    self.env["res.partner"].browse(partner_id).name
        """
    assert _lines(tmp_path, src) == [5]


def test_recordset_preserving_methods_keep_the_singleton(tmp_path: Path):
    src = """\
        class M:
            def f(self, ids):
                for i in ids:
                    self.env["res.partner"].browse(i).sudo().with_context(lang="fr").name
        """
    assert _lines(tmp_path, src) == [4]


def test_with_prefetch_is_the_remedy_and_is_not_flagged(tmp_path: Path):
    src = """\
        class M:
            def f(self, ids):
                for i in ids:
                    rec = self.env["res.partner"].browse(i).with_prefetch(ids)
                    rec.name
        """
    assert _lines(tmp_path, src) == []


def test_with_prefetch_before_browse_is_also_the_remedy(tmp_path: Path):
    src = """\
        class M:
            def f(self, ids):
                for i in ids:
                    self.env["res.partner"].with_prefetch(ids).browse(i).name
        """
    assert _lines(tmp_path, src) == []


def test_browse_of_a_collection_or_a_loop_independent_id_is_not_flagged(
    tmp_path: Path,
):
    src = """\
        class M:
            def f(self, ids, fixed_id):
                for i in range(3):
                    self.env["res.partner"].browse(ids).name
                    self.env["res.partner"].browse([i, 1]).name
                    self.env["res.partner"].browse(fixed_id).name
        """
    assert _lines(tmp_path, src) == []


def test_browse_before_the_loop_and_the_iterable_are_not_in_the_loop(tmp_path: Path):
    src = """\
        class M:
            def f(self, ids):
                rec = self.env["res.partner"].browse(ids[0])
                for x in self.env["res.partner"].browse(ids[1]).child_ids:
                    rec.name
        """
    assert _lines(tmp_path, src) == []


def test_methods_and_non_query_attributes_are_not_reads(tmp_path: Path):
    src = """\
        class M:
            def f(self, ids):
                for i in ids:
                    rec = self.env["res.partner"].browse(i)
                    rec.write({"name": "x"})
                    rec.unlink()
                    rec.id
                    rec.env
                    rec._name
                    rec.exists()
        """
    assert _lines(tmp_path, src) == []


def test_test_files_are_skipped(tmp_path: Path):
    src = """\
        class M:
            def f(self, ids):
                for i in ids:
                    self.env["res.partner"].browse(i).name
        """
    assert _lines(tmp_path, src, "tests/test_x.py") == []
    assert _lines(tmp_path, src, "models/x.py") == [4]
