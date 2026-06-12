"""Custom-rule plugins are discovered via entry points and imported."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass

from odoo_doctor.rules.plugins import load_rule_plugins


@dataclass
class _FakeEP:
    name: str
    value: str

    def load(self):
        # Simulate importlib EntryPoint.load(): import & return the module.
        return __import__(self.value, fromlist=["*"])


def test_load_rule_plugins_imports_each_entry_point():
    # Create a throwaway module that records that it was imported.
    mod = types.ModuleType("fake_odoo_doctor_plugin")
    mod.LOADED = True
    sys.modules["fake_odoo_doctor_plugin"] = mod

    eps = [_FakeEP(name="fake", value="fake_odoo_doctor_plugin")]
    loaded = load_rule_plugins(entry_points=eps)

    assert "fake" in loaded
    assert sys.modules["fake_odoo_doctor_plugin"].LOADED is True


def test_load_rule_plugins_is_resilient_to_bad_plugin():
    class _Boom:
        name = "boom"

        def load(self):
            raise RuntimeError("broken plugin")

    # A broken plugin must not crash discovery; it is skipped with a warning.
    loaded = load_rule_plugins(entry_points=[_Boom()])
    assert "boom" not in loaded
