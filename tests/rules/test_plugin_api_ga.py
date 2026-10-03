"""Plugin API v1 guarantees: validation, no overrides, rollback, allowlist, versioning."""

from __future__ import annotations

import types

import pytest

from odoo_doctor import plugin_api
from odoo_doctor.core.config import _build_config
from odoo_doctor.rules.plugins import load_rule_plugins
from odoo_doctor.rules.registry import RuleRegistry, rule


def _rule_kwargs(**over):
    base = {
        "name": "p-rule",
        "category": "Maintainability",
        "tier": "P3",
        "severity": "info",
        "default_confidence": "high",
        "needs_context": False,
    }
    base.update(over)
    return base


class _EP:
    def __init__(self, name, loader):
        self.name = name
        self._loader = loader

    def load(self):
        return self._loader()


def test_public_api_surface():
    for name in plugin_api.__all__:
        assert hasattr(plugin_api, name), name
    assert plugin_api.PLUGIN_API_VERSION == 1
    assert plugin_api.TIERS == ("P0", "P1", "P2", "P3")


@pytest.mark.parametrize(
    "bad",
    [
        {"category": "Nonsense"},
        {"tier": "P9"},
        {"severity": "fatal"},
        {"default_confidence": "certain"},
    ],
)
def test_invalid_metadata_is_rejected(bad):
    with pytest.raises(ValueError, match="invalid"):
        rule(**_rule_kwargs(**bad), registry=RuleRegistry())


def test_duplicate_rule_name_is_rejected():
    reg = RuleRegistry()
    rule(**_rule_kwargs(), registry=reg)(lambda f, m, v: [])
    with pytest.raises(ValueError, match="already registered"):
        rule(**_rule_kwargs(), registry=reg)(lambda f, m, v: [])


def test_plugin_cannot_override_builtin_rule():
    import odoo_doctor.cli.app  # noqa: F401  (registers built-ins)
    from odoo_doctor.rules.registry import default_registry

    before = default_registry.get("eval-usage")[1]
    with pytest.raises(ValueError):
        rule(**_rule_kwargs(name="eval-usage", category="Security", tier="P0"))(
            lambda f, m, v: []
        )
    assert default_registry.get("eval-usage")[1] is before


def test_failing_plugin_is_rolled_back_and_others_survive():
    reg = RuleRegistry()

    def bad():
        rule(**_rule_kwargs(name="half-registered"), registry=reg)(lambda f, m, v: [])
        raise RuntimeError("boom after registering")

    def good():
        rule(**_rule_kwargs(name="fine"), registry=reg)(lambda f, m, v: [])
        return types.SimpleNamespace(ODOO_DOCTOR_PLUGIN_API=1)

    loaded = load_rule_plugins(
        entry_points=[_EP("bad", bad), _EP("good", good)], registry=reg
    )
    assert loaded == {"good": True}
    assert "half-registered" not in reg and "fine" in reg


def test_incompatible_api_version_is_refused_and_rolled_back():
    reg = RuleRegistry()

    def future():
        rule(**_rule_kwargs(name="future-rule"), registry=reg)(lambda f, m, v: [])
        return types.SimpleNamespace(ODOO_DOCTOR_PLUGIN_API=2)

    assert load_rule_plugins(entry_points=[_EP("future", future)], registry=reg) == {}
    assert "future-rule" not in reg


def test_plugin_without_declared_version_still_loads():
    reg = RuleRegistry()

    def legacy():
        rule(**_rule_kwargs(name="legacy"), registry=reg)(lambda f, m, v: [])
        return types.SimpleNamespace()

    assert load_rule_plugins(entry_points=[_EP("legacy", legacy)], registry=reg) == {
        "legacy": True
    }


def test_allowlist_restricts_loading(capsys):
    reg = RuleRegistry()
    calls = []

    def make(name):
        def loader():
            calls.append(name)
            return types.SimpleNamespace()

        return _EP(name, loader)

    loaded = load_rule_plugins(
        entry_points=[make("a"), make("b")], allow=["a"], registry=reg
    )
    assert loaded == {"a": True} and calls == ["a"]
    assert "'b'" in capsys.readouterr().err


def test_empty_allowlist_loads_nothing():
    assert load_rule_plugins(entry_points=[_EP("a", lambda: None)], allow=[]) == {}


def test_config_parses_allowlist():
    assert _build_config({}).plugin_allowlist is None
    cfg = _build_config({"plugins": {"enabled": True, "allow": ["x", "y"]}})
    assert cfg.plugin_allowlist == ["x", "y"]
