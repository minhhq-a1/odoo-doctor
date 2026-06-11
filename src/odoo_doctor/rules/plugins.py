# src/odoo_doctor/rules/plugins.py
"""Discover and load third-party rule plugins via entry points.

SKELETON (v0.3.0): plugins register rules by exposing an entry point in the
group 'odoo_doctor.rules' whose value is an importable module. Importing the
module triggers its @rule decorators, registering rules in the default
registry — identical to how built-in rules are wired in cli/app.py.

NOT YET STABLE: the rule-function contract, capability gating for third-party
rules, and error isolation guarantees are provisional and may change in v0.4.0.
"""

from __future__ import annotations

import sys
from importlib.metadata import entry_points
from typing import Iterable

ENTRY_POINT_GROUP = "odoo_doctor.rules"


def _discover() -> Iterable:
    try:
        eps = entry_points()
    except Exception:  # pragma: no cover - defensive
        return []
    # Python 3.10+ : entry_points() returns a SelectableGroups/EntryPoints.
    try:
        return list(eps.select(group=ENTRY_POINT_GROUP))
    except AttributeError:  # pragma: no cover - very old API
        return list(eps.get(ENTRY_POINT_GROUP, []))


def load_rule_plugins(entry_points=None) -> dict[str, bool]:
    """Import every discovered plugin module. Returns {name: ok}.

    A failing plugin is logged to stderr and skipped, never raised, so one bad
    plugin cannot break a scan.
    """
    eps = list(entry_points if entry_points is not None else _discover())
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
        try:
            ep.load()
            loaded[name] = True
        except Exception as exc:  # noqa: BLE001 - isolation is the point
            print(
                f"[WARN] failed to load rule plugin '{name}': {exc}",
                file=sys.stderr,
            )
    return loaded
