# src/odoo_doctor/rules/plugins.py
"""Discover and load third-party rule plugins via entry points (GA, API v1).

A plugin exposes an entry point in the group 'odoo_doctor.rules' whose value is
an importable module. Importing the module triggers its @rule decorators,
registering rules in the default registry, exactly like built-in rules.

Guarantees (see docs/custom-rules.md):
- opt-in: nothing loads unless ``[plugins].enabled = true``;
- optional allowlist: ``[plugins].allow = ["name", ...]`` restricts which entry
  points load;
- isolation: a plugin that fails to import, declares an incompatible
  ``ODOO_DOCTOR_PLUGIN_API``, or registers an invalid/duplicate rule is skipped
  with a warning and every rule it had registered is rolled back;
- built-in rules can never be overridden (duplicate names are rejected);
- a rule that raises while running is isolated per rule/file by the scanner.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from importlib.metadata import entry_points

from odoo_doctor.plugin_api import PLUGIN_API_VERSION
from odoo_doctor.rules.registry import RuleRegistry, default_registry

ENTRY_POINT_GROUP = "odoo_doctor.rules"
PLUGIN_API_ATTR = "ODOO_DOCTOR_PLUGIN_API"


def _discover() -> Iterable:
    try:
        eps = entry_points()
    except Exception:  # noqa: BLE001  # pragma: no cover - defensive
        return []
    # Python 3.10+ : entry_points() returns a SelectableGroups/EntryPoints.
    try:
        return list(eps.select(group=ENTRY_POINT_GROUP))
    except AttributeError:  # pragma: no cover - very old API
        return list(eps.get(ENTRY_POINT_GROUP, []))


def _rule_names(registry: RuleRegistry) -> set[str]:
    return {meta.name for meta, _ in registry.get_rules()}


def load_rule_plugins(
    entry_points=None,
    allow: Iterable[str] | None = None,
    registry: RuleRegistry | None = None,
) -> dict[str, bool]:
    """Import every permitted plugin module. Returns {name: ok}.

    ``allow`` (None = no restriction) limits loading to the named entry points;
    skipped names are not reported as loaded. A failing plugin is logged to
    stderr, rolled back and skipped, never raised, so one bad plugin cannot
    break a scan.
    """
    target = registry if registry is not None else default_registry
    eps = list(entry_points if entry_points is not None else _discover())
    if allow is not None:
        allowed = set(allow)
        for ep in eps:
            if getattr(ep, "name", "<unknown>") not in allowed:
                print(
                    f"[odoo-doctor] Skipping rule plugin "
                    f"'{getattr(ep, 'name', '<unknown>')}': not in [plugins].allow.",
                    file=sys.stderr,
                )
        eps = [ep for ep in eps if getattr(ep, "name", "<unknown>") in allowed]

    loaded: dict[str, bool] = {}
    if eps:
        print(
            "[odoo-doctor] Loading third-party rule plugins (you enabled "
            "[plugins].enabled). Plugins run with full process privileges; only "
            "enable plugins you trust.",
            file=sys.stderr,
        )
    for ep in eps:
        name = getattr(ep, "name", "<unknown>")
        before = _rule_names(target)
        try:
            module = ep.load()
            declared = getattr(module, PLUGIN_API_ATTR, None)
            if declared is not None and declared != PLUGIN_API_VERSION:
                raise RuntimeError(
                    f"requires plugin API {declared}, this odoo-doctor provides "
                    f"{PLUGIN_API_VERSION}"
                )
            loaded[name] = True
        except Exception as exc:  # noqa: BLE001 - isolation is the point
            for added in _rule_names(target) - before:
                target.unregister(added)
            print(
                f"[WARN] failed to load rule plugin '{name}': {exc}",
                file=sys.stderr,
            )
    return loaded
