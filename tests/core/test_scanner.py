"""collect_scores in core.scanner must match the CLI's prior behavior."""

from __future__ import annotations

from pathlib import Path

import odoo_doctor.cli.app  # noqa: F401  (registers the rules)
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


def _eval_rule_files(root: Path) -> set[str]:
    diags, _ = collect_scores(
        addon_paths=[root],
        cfg=OdooDoctorConfig(odoo_version="17.0"),
        version="17.0",
        config_root=root,
    )
    return {Path(d.file_path).name for d in diags if d.rule == "eval-usage"}


def test_files_named_with_dunder_prefix_are_scanned(tmp_path: Path):
    root = _addon(tmp_path)
    mod = root / "my_addon"
    (mod / "__init__.py").write_text("def post_init(env):\n    eval(env.x)\n")
    (mod / "__foo.py").write_text("def f(x):\n    return eval(x)\n")
    # the manifest stays data: not parsed as model code (only the two sources above)
    assert _eval_rule_files(root) == {"__init__.py", "__foo.py"}


def test_manifest_is_never_handed_to_a_file_rule(tmp_path: Path):
    """`__manifest__.py` is data: no file-based rule may see it as code."""
    from odoo_doctor.rules.registry import default_registry, rule

    seen: list[str] = []

    @rule(
        name="zz-spy-file-rule",
        category="Correctness",
        tier="P3",
        severity="info",
        default_confidence="low",
        needs_context=False,
    )
    def spy(file_path, module_name, odoo_version):
        seen.append(Path(file_path).name)
        return []

    try:
        root = _addon(tmp_path)
        (root / "my_addon" / "__foo.py").write_text("x = 1\n")
        collect_scores(
            addon_paths=[root],
            cfg=OdooDoctorConfig(odoo_version="17.0"),
            version="17.0",
            config_root=root,
        )
    finally:
        default_registry.unregister("zz-spy-file-rule")
    assert "__foo.py" in seen and "__manifest__.py" not in seen
