import yaml
from pathlib import Path


def test_action_yaml_is_valid():
    action_file = Path("action.yml")
    assert action_file.exists()

    with open(action_file) as f:
        data = yaml.safe_load(f)

    assert data["runs"]["using"] == "composite"


def test_action_declares_expected_inputs():
    with open("action.yml") as f:
        data = yaml.safe_load(f)

    inputs = data.get("inputs", {})
    expected = {
        "odoo-version",
        "fail-on",
        "advisory",
        "diff-base",
        "pr-comment",
        "min-score",
        "paths",
    }
    assert expected.issubset(inputs.keys())


def test_action_invokes_scan_with_format_github():
    with open("action.yml") as f:
        data = yaml.safe_load(f)

    steps = data["runs"]["steps"]
    run_step = next(step for step in steps if step.get("name") == "Run odoo-doctor")
    script = run_step["run"]

    assert "odoo-doctor scan" in script
    assert "--format github" in script
