"""config_edit preserves everything except the [ignore] rules array."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.core.config import load_config
from odoo_doctor.core.config_edit import set_rule_ignored


def test_creates_file(tmp_path: Path):
    p = tmp_path / "odoo-doctor.toml"
    assert set_rule_ignored(p, "a-rule", True) is True
    assert load_config(tmp_path).ignore_rules == ["a-rule"]


def test_appends_section_to_existing_file_without_touching_it(tmp_path: Path):
    p = tmp_path / "odoo-doctor.toml"
    original = '[odoo-doctor]\n# keep me\nodoo_version = "17.0"\n'
    p.write_text(original, encoding="utf-8")
    set_rule_ignored(p, "a-rule", True)
    text = p.read_text(encoding="utf-8")
    assert text.startswith(original)
    assert load_config(tmp_path).ignore_rules == ["a-rule"]
    assert load_config(tmp_path).odoo_version == "17.0"


def test_updates_existing_array_and_keeps_other_keys(tmp_path: Path):
    p = tmp_path / "odoo-doctor.toml"
    p.write_text(
        '[ignore]\n# note\nrules = ["x"]\nfiles = ["**/migrations/**"]\n\n'
        "[category_weights]\nSecurity = 2.0\n",
        encoding="utf-8",
    )
    set_rule_ignored(p, "y", True)
    cfg = load_config(tmp_path)
    assert cfg.ignore_rules == ["x", "y"]
    assert cfg.ignore_files == ["**/migrations/**"]
    assert cfg.category_weights == {"Security": 2.0}
    assert "# note" in p.read_text(encoding="utf-8")


def test_multiline_array_and_remove(tmp_path: Path):
    p = tmp_path / "odoo-doctor.toml"
    p.write_text('[ignore]\nrules = [\n  "x",\n  "y",\n]\n', encoding="utf-8")
    assert set_rule_ignored(p, "x", False) is True
    assert load_config(tmp_path).ignore_rules == ["y"]


def test_section_without_rules_key(tmp_path: Path):
    p = tmp_path / "odoo-doctor.toml"
    p.write_text('[ignore]\nfiles = ["a"]\n', encoding="utf-8")
    set_rule_ignored(p, "x", True)
    cfg = load_config(tmp_path)
    assert cfg.ignore_rules == ["x"] and cfg.ignore_files == ["a"]


def test_noop_cases_return_false(tmp_path: Path):
    p = tmp_path / "odoo-doctor.toml"
    assert set_rule_ignored(p, "x", False) is False
    assert not p.exists()
    set_rule_ignored(p, "x", True)
    assert set_rule_ignored(p, "x", True) is False
