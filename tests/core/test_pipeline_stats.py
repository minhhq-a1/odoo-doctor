"""run_pipeline_with_stats: which channel dropped which finding."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.pipeline import run_pipeline, run_pipeline_with_stats


def _diag(path: Path, rule: str, line: int = 1, module: str = "m") -> Diagnostic:
    return Diagnostic(
        module=module,
        file_path=str(path),
        line=line,
        column=0,
        rule=rule,
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="t",
        message="msg",
        help="h",
        odoo_version="17.0",
    )


def _counts(**kw: int) -> dict[str, int]:
    return {"surfaced": 0, "inline": 0, "ignore_rule": 0, "severity_off": 0, **kw}


def _run(diags, cfg=None, suppressions=None, active=None, version="17.0"):
    active = active if active is not None else {d.rule: None for d in diags}
    return run_pipeline_with_stats(
        diags, cfg or OdooDoctorConfig(), suppressions or set(), active, version
    )


def test_each_channel_is_counted(tmp_path: Path):
    f = tmp_path / "f.py"
    diags = [
        _diag(f, "keep"),
        _diag(f, "off_rule"),
        _diag(f, "ign_rule"),
        _diag(f, "inl_rule", line=3),
    ]
    cfg = OdooDoctorConfig(
        severity_overrides={"off_rule": "off"}, ignore_rules=["ign_rule"]
    )
    kept, eligible, stats = _run(diags, cfg, suppressions={(str(f), 3, "inl_rule")})
    assert [d.rule for d in kept] == ["keep"]
    assert eligible == [True]
    assert stats == {
        "m": {
            "keep": _counts(surfaced=1),
            "off_rule": _counts(severity_off=1),
            "ign_rule": _counts(ignore_rule=1),
            "inl_rule": _counts(inline=1),
        }
    }


def test_file_wide_suppression_counts_as_inline(tmp_path: Path):
    f = tmp_path / "f.py"
    diags = [_diag(f, "r", line=1), _diag(f, "r", line=2)]
    _, _, stats = _run(diags, suppressions={(str(f), 0, "r")})
    assert stats == {"m": {"r": _counts(inline=2)}}


def test_first_channel_wins(tmp_path: Path):
    f = tmp_path / "f.py"
    diags = [_diag(f, "x"), _diag(f, "y")]
    cfg = OdooDoctorConfig(severity_overrides={"x": "off"}, ignore_rules=["x", "y"])
    _, _, stats = _run(diags, cfg, suppressions={(str(f), 1, "y")})
    assert stats == {"m": {"x": _counts(severity_off=1), "y": _counts(ignore_rule=1)}}


def test_ignored_files_and_modules_are_not_counted(tmp_path: Path):
    vendor = tmp_path / "vendor" / "v.py"
    keep = tmp_path / "k.py"
    cfg = OdooDoctorConfig(ignore_files=["**/vendor/**"], ignore_modules=["skip"])
    diags = [
        _diag(keep, "keep"),
        _diag(vendor, "keep"),
        _diag(keep, "keep", module="skip"),
    ]
    _, _, stats = _run(diags, cfg)
    assert stats == {"m": {"keep": _counts(surfaced=1)}}


def test_findings_gated_out_by_version_are_not_counted(tmp_path: Path):
    f = tmp_path / "f.py"
    diags = [_diag(f, "gated"), _diag(f, "keep")]
    cfg = OdooDoctorConfig(severity_overrides={"gated": "off"})
    _, _, stats = _run(
        diags, cfg, active={"gated": "18.0", "keep": None}, version="17.0"
    )
    assert stats == {"m": {"keep": _counts(surfaced=1)}}


def test_run_pipeline_result_is_unchanged(tmp_path: Path):
    f = tmp_path / "f.py"
    diags = [_diag(f, "keep"), _diag(f, "ign")]
    cfg = OdooDoctorConfig(ignore_rules=["ign"])
    active = {"keep": None, "ign": None}
    kept, eligible, _ = run_pipeline_with_stats(diags, cfg, set(), active, "17.0")
    assert run_pipeline(diags, cfg, set(), active, "17.0") == (kept, eligible)


def test_scope_excluded_findings_are_not_counted_in_config_channels(tmp_path: Path):
    vendor = tmp_path / "vendor" / "v.py"
    keep = tmp_path / "k.py"
    cfg = OdooDoctorConfig(
        severity_overrides={"off_rule": "off"},
        ignore_rules=["ign_rule"],
        ignore_files=["**/vendor/**"],
        ignore_modules=["legacy"],
    )
    diags = [
        _diag(keep, "keep"),
        _diag(keep, "off_rule", module="legacy"),  # excluded module
        _diag(vendor, "off_rule"),  # excluded file
        _diag(keep, "ign_rule", module="legacy"),
        _diag(vendor, "ign_rule"),
        _diag(keep, "off_rule", line=5),  # in scope: still counted
    ]
    _, _, stats = _run(diags, cfg)
    assert stats == {
        "m": {
            "keep": _counts(surfaced=1),
            "off_rule": _counts(severity_off=1),
        }
    }
