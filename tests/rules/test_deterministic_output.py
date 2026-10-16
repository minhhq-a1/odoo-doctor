"""A scan prints the same findings whatever PYTHONHASHSEED is (set iteration order)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

SEEDS = ("0", "1", "2", "3", "4", "5")


def _scan(root: Path, seed: str) -> list[tuple[str, str, int]]:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "from odoo_doctor.cli.app import app; app()",
            "scan",
            str(root),
            "--json",
            "--odoo-version",
            "17.0",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert done.returncode in (0, 1), done.stderr
    return [
        (d["rule"], d["title"], d["line"])
        for m in json.loads(done.stdout)["modules"].values()
        for d in m["diagnostics"]
    ]


def test_compute_missing_depends_names_the_same_field_for_every_hash_seed(
    tmp_path: Path,
):
    mod = tmp_path / "my_mod"
    mod.mkdir()
    (mod / "__init__.py").write_text("")
    (mod / "__manifest__.py").write_text(
        '{"name": "M", "version": "17.0.1.0.0", "depends": ["base"], "license": "LGPL-3"}'
    )
    (mod / "m.py").write_text(
        dedent("""\
        from odoo import models, fields, api

        class MyModel(models.Model):
            _name = "my.model"

            a = fields.Char()
            b = fields.Char(compute="_compute_b")
            c = fields.Char()
            d = fields.Char()
            e = fields.Char()
            f = fields.Char()

            @api.depends("a")
            def _compute_b(self):
                for rec in self:
                    rec.b = rec.a + rec.c + rec.d + rec.e + rec.f
        """)
    )
    runs = {seed: _scan(tmp_path, seed) for seed in SEEDS}
    first = runs[SEEDS[0]]
    assert any(rule == "compute-missing-depends" for rule, _, _ in first)
    for seed, found in runs.items():
        assert found == first, f"PYTHONHASHSEED={seed} differs"
