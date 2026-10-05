"""Stability contract (docs/stability.md): what users and CI may rely on.

Every check is a subset check: names that were promised must still exist. Adding a
command, flag, JSON key or rule never fails these tests. Removing or renaming one does,
and the fix is to follow the deprecation policy in docs/stability.md and then update the
frozen data below on purpose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

import odoo_doctor.cli.app  # noqa: F401  (registers every rule)
from odoo_doctor import plugin_api
from odoo_doctor.cli.app import app
from odoo_doctor.core.config import load_config
from odoo_doctor.core.history import HISTORY_SCHEMA_VERSION
from odoo_doctor.rules.registry import default_registry

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()

# --- rule IDs: never renamed, never reused for another rule -----------------

FROZEN_RULE_IDS = """
manifest-missing-required-fields manifest-data-order-risk manifest-missing-dependency
missing-access-csv eval-usage unknown-model-in-access-csv raw-sql-string-interpolation
public-controller-sudo-risk sudo-without-comment record-rule-without-domain
duplicate-xml-id missing-xml-ref view-field-not-in-model button-method-not-found
orphan-view search-in-loop create-in-loop write-in-loop n-plus-one-read
unbounded-search expensive-nonstored-compute override-missing-super
compute-missing-depends field-no-string-on-required missing-translation
missing-ondelete data-noupdate-risk deprecated-api-usage removed-model-still-referenced
asset-bundle-missing monetary-missing-currency-field hardcoded-company-or-currency
missing-multicompany-rule manifest-license-incompatible missing-external-dependency
vendored-python-code
""".split()

# --- CLI: command path -> flags that must keep existing ---------------------

FROZEN_CLI = {
    "fix": {"--fix", "--fix-dry-run", "--odoo-version"},
    "history import": {"--branch", "--commit", "--timestamp"},
    "history show": {"--last", "--max-drop"},
    "init": {"--path"},
    "install": set(),
    "rules": {"--cache", "--check", "--format", "--json", "--out", "--path"},
    "scan": set(
        """--badge --baseline --cache --diff --fail-on --format --history --json
        --min-score --module --odoo-version --score-delta --write-baseline""".split()
    ),
}

# --- machine-readable output ------------------------------------------------

FROZEN_REPORT_KEYS = {
    "version",
    "schema_version",
    "score_schema_version",
    "project_score",
    "top_findings",
    "modules",
}
FROZEN_MODULE_KEYS = {"score", "fix_priorities", "suppression_stats", "diagnostics"}
FROZEN_SCORE_KEYS = {"overall", "label", "categories", "diagnostics_counted"}
FROZEN_CATEGORY_KEYS = {"category", "score", "finding_count"}
FROZEN_DIAGNOSTIC_KEYS = set(
    """module file_path line column rule category severity tier source confidence
    title message help odoo_version url""".split()
)
FROZEN_TOP_FINDING_KEYS = set(
    """module file_path line rule tier title category severity confidence
    fixable""".split()
)
FROZEN_FIX_PRIORITY_KEYS = set(
    """rank rule file_path line tier title category impact effort roi
    projected_score score_gain fixable""".split()
)
FROZEN_SUPPRESSION_COUNTS = {"surfaced", "inline", "ignore_rule", "severity_off"}
FROZEN_HISTORY_KEYS = set(
    """history_schema_version score_schema_version tool_version timestamp commit
    branch project modules""".split()
)

FROZEN_PLUGIN_API = set(
    """CATEGORIES CONFIDENCES Diagnostic ModuleContext PLUGIN_API_VERSION SEVERITIES
    TIERS node_is_orm read_source receiver_is_orm rule""".split()
)


def _click_command():
    return typer.main.get_command(app)


def _flags(command) -> set[str]:
    return {
        opt
        for param in command.params
        for opt in getattr(param, "opts", [])
        if opt.startswith("-") and opt != "--help"
    }


def _scan_report(addon: str = "bad_addon") -> dict:
    result = runner.invoke(app, ["scan", str(FIXTURES / addon), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


# --- tests ------------------------------------------------------------------


def test_no_promised_rule_id_disappears():
    current = {meta.name for meta, _ in default_registry.get_rules()}
    assert set(FROZEN_RULE_IDS) <= current, sorted(set(FROZEN_RULE_IDS) - current)


@pytest.mark.parametrize("path", sorted(FROZEN_CLI))
def test_cli_commands_and_flags_still_exist(path: str):
    command = _click_command()
    for part in path.split():
        command = command.commands[part]
    missing = FROZEN_CLI[path] - _flags(command)
    assert not missing, f"`odoo-doctor {path}` lost {sorted(missing)}"


@pytest.mark.parametrize(
    "argv, expected",
    [
        (["scan", str(FIXTURES / "sample_addon")], 0),
        (["scan", str(FIXTURES / "bad_addon"), "--fail-on", "error"], 1),
        (["scan", str(FIXTURES / "bad_addon"), "--min-score", "100"], 2),
        (["scan", str(FIXTURES / "bad_addon"), "--min-score", "200"], 3),
    ],
)
def test_exit_codes(argv: list[str], expected: int):
    assert runner.invoke(app, argv).exit_code == expected


def test_json_report_keys_are_stable():
    report = _scan_report()
    assert FROZEN_REPORT_KEYS <= set(report)
    assert report["schema_version"] == "1.0"
    assert {"overall", "label", "module_count"} <= set(report["project_score"])
    assert FROZEN_TOP_FINDING_KEYS <= set(report["top_findings"][0])

    module = next(iter(report["modules"].values()))
    assert FROZEN_MODULE_KEYS <= set(module)
    assert FROZEN_SCORE_KEYS <= set(module["score"])
    assert FROZEN_CATEGORY_KEYS <= set(module["score"]["categories"][0])
    assert FROZEN_DIAGNOSTIC_KEYS <= set(module["diagnostics"][0])
    assert FROZEN_FIX_PRIORITY_KEYS <= set(module["fix_priorities"][0])
    first_rule = next(iter(module["suppression_stats"].values()))
    assert FROZEN_SUPPRESSION_COUNTS <= set(first_rule)


def test_rules_stats_json_keys_are_stable():
    result = runner.invoke(
        app, ["rules", "stats", "--path", str(FIXTURES / "bad_addon"), "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert {"thresholds", "rules"} <= set(data)
    assert {"min_sample", "noisy_ratio"} <= set(data["thresholds"])
    assert set(
        """rule surfaced inline ignore_rule severity_off suppressed total ratio
            noisy suggestion""".split()
    ) <= set(data["rules"][0])


def test_history_record_keys_are_stable(tmp_path: Path):
    history = tmp_path / "h.jsonl"
    result = runner.invoke(
        app,
        ["scan", str(FIXTURES / "bad_addon"), "--json", "--history", str(history)],
    )
    assert result.exit_code == 0, result.output
    record = json.loads(history.read_text().splitlines()[0])
    assert FROZEN_HISTORY_KEYS <= set(record)
    assert record["history_schema_version"] == HISTORY_SCHEMA_VERSION == 1


def test_baseline_file_format_is_stable(tmp_path: Path):
    baseline = tmp_path / "b.json"
    result = runner.invoke(
        app,
        ["scan", str(FIXTURES / "bad_addon"), "--write-baseline", str(baseline)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(baseline.read_text())
    assert data["version"] == 1
    assert isinstance(data["ids"], list) and data["ids"]


def test_sarif_is_2_1_0_with_rule_names_as_rule_ids():
    result = runner.invoke(
        app, ["scan", str(FIXTURES / "bad_addon"), "--format", "sarif"]
    )
    sarif = json.loads(result.stdout)
    assert sarif["version"] == "2.1.0"
    known = {meta.name for meta, _ in default_registry.get_rules()}
    rule_ids = {r["ruleId"] for r in sarif["runs"][0]["results"]}
    assert rule_ids & known  # native findings are reported under their rule name


def test_config_keys_are_still_read(tmp_path: Path):
    (tmp_path / "odoo-doctor.toml").write_text(
        """
[odoo-doctor]
odoo_version = "17.0"
addons_paths = ["a"]
target_modules = ["m"]
odoo_source_path = "/odoo"
min_score = 55
capabilities = ["enterprise"]

[plugins]
enabled = true
allow = ["p"]

[adapters]
ruff = false
pylint_odoo = false
oca = false

[severity]
eval-usage = "warning"

[ignore]
rules = ["orphan-view"]
files = ["**/migrations/**"]
modules = ["legacy"]

[category_weights]
Security = 2.0

[surfaces.ci_failure]
min_confidence = "medium"
categories = ["Security"]
tiers = ["P0"]
"""
    )
    cfg = load_config(tmp_path)
    assert cfg.odoo_version == "17.0"
    assert cfg.addons_paths == ["a"]
    assert cfg.target_modules == ["m"]
    assert cfg.odoo_source_path == "/odoo"
    assert cfg.min_score == 55
    assert cfg.capabilities == ["enterprise"]
    assert cfg.enable_plugins is True and cfg.plugin_allowlist == ["p"]
    assert cfg.adapters["ruff"] is False and cfg.adapters["pylint_odoo"] is False
    assert cfg.severity_overrides == {"eval-usage": "warning"}
    assert cfg.ignore_rules == ["orphan-view"]
    assert cfg.ignore_files == ["**/migrations/**"]
    assert cfg.ignore_modules == ["legacy"]
    assert cfg.category_weights == {"Security": 2.0}
    ci = cfg.surfaces["ci_failure"]
    assert (ci.min_confidence, ci.categories, ci.tiers) == (
        "medium",
        ["Security"],
        ["P0"],
    )


def test_plugin_api_surface_is_stable():
    assert plugin_api.PLUGIN_API_VERSION == 1
    assert FROZEN_PLUGIN_API <= set(plugin_api.__all__)


# --- the document must stay in step with the frozen data ---------------------


@pytest.fixture(scope="module")
def stability_doc() -> str:
    path = ROOT / "docs" / "stability.md"
    assert path.exists(), "docs/stability.md is missing"
    return path.read_text(encoding="utf-8")


def test_doc_names_every_frozen_command(stability_doc: str):
    for path in FROZEN_CLI:
        command = path.split()[0]
        assert (
            f"`{command}`" in stability_doc or f"odoo-doctor {command}" in stability_doc
        )


def test_doc_states_exit_codes_and_policy(stability_doc: str):
    for needle in ("Exit codes", "Deprecated", "plugin_api", "score_schema_version"):
        assert needle in stability_doc, needle
