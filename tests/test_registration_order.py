"""Rules register in import order, and that order is user-visible: it is the order of
`odoo-doctor rules list` and of findings at the same location. A formatter that sorts
the side-effect imports (isort did, once) would silently reorder both."""

from __future__ import annotations

import json
import subprocess
import sys

from tests.test_stability_contract import FROZEN_RULE_IDS


def test_rules_register_in_their_documented_order():
    # A fresh interpreter: inside pytest other test modules import rule modules first.
    code = (
        "import json, odoo_doctor.cli.app;"
        "from odoo_doctor.rules.registry import default_registry;"
        "print(json.dumps([m.name for m, _ in default_registry.get_rules()]))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    registered = json.loads(out)
    assert registered[: len(FROZEN_RULE_IDS)] == FROZEN_RULE_IDS, (
        "rule registration order changed; new rules must be imported after the existing "
        "ones in cli/app.py, and the isort-protected blocks must stay unsorted"
    )
