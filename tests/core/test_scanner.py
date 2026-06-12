"""collect_scores in core.scanner must match the CLI's prior behavior."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.scanner import collect_scores


def _addon(tmp_path: Path) -> Path:
    mod = tmp_path / "my_addon"
    mod.mkdir()
    (mod / "__init__.py").touch()
    (mod / "__manifest__.py").write_text(
        "{'name': 'My Addon', 'version': '1.0', 'depends': ['base'], "
        "'data': [], 'installable': True}"  # missing license -> a finding
    )
    return tmp_path


def test_collect_scores_returns_diags_and_scores(tmp_path: Path):
    root = _addon(tmp_path)
    cfg = OdooDoctorConfig(odoo_version="17.0")
    diags, scores = collect_scores(
        addon_paths=[root],
        cfg=cfg,
        version="17.0",
        config_root=root,
    )
    assert "my_addon" in scores
    assert any(d.rule == "manifest-missing-required-fields" for d in diags)
