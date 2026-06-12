"""n-plus-one-read flags chained relational attribute access inside loops."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.performance.n_plus_one_read import check_n_plus_one_read


def _write(tmp_path: Path, src: str) -> Path:
    f = tmp_path / "m.py"
    f.write_text(dedent(src))
    return f


def test_chained_attr_access_in_loop_is_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class M:
            def f(self, order):
                for line in order.line_ids:
                    name = line.product_id.name
        """,
    )
    diags = check_n_plus_one_read(f, "m", "17.0")
    assert any(d.rule == "n-plus-one-read" for d in diags)


def test_simple_attr_access_is_not_flagged(tmp_path: Path):
    f = _write(
        tmp_path,
        """\
        class M:
            def f(self, order):
                for line in order.line_ids:
                    qty = line.quantity
        """,
    )
    diags = check_n_plus_one_read(f, "m", "17.0")
    assert not any(d.rule == "n-plus-one-read" for d in diags)
