"""Upgrade readiness report: what a module still needs to run on a newer Odoo.

Pure functions over the scan's findings; no I/O. ``scan --upgrade-report`` calls
:func:`build_upgrade_report` and adds the result to the JSON payload (key
``upgrade_report``) or prints :func:`render_upgrade_report`.

Grouping. The report covers every finding of category "Upgrade Safety" the scan
produced (any confidence), grouped by *kind of change* with the static table
``_GROUPS`` below. A rule not in the table lands in "Other upgrade findings".

Mechanical or needs review. The label comes only from the static tables
``MECHANICAL_RULES`` and ``MECHANICAL_RENAMES``, never from the finding's text, and
only a ``high`` confidence finding can be mechanical: ``fix`` applies only ``high``
findings (``core.fixer.compute_fixes``). A finding is "mechanical" when the change
is a rename that needs no decision. ``fix --upgrade-to`` fixes them
(``rules/upgrade_safety/fixers.py``); the report itself fixes nothing.

Readiness score (``readiness_schema_version`` 1), per module::

    points    = sum(TIER_IMPACT[tier]) over its high-confidence Upgrade Safety findings
    readiness = round(100 * 100 / (100 + points), 1)

100 when there are none; it falls as points grow but never reaches 0, so a module
with 5 findings and one with 500 still differ. Only ``high`` findings count
(``medium`` and ``low`` appear in the group counts but not in the score), and
mechanical findings count like the others: they are still work to do. The project
score is the mean of the module scores (100 for an empty scan). Changing the
formula bumps ``READINESS_SCHEMA_VERSION``.

Effort of a group is the sum of ``EFFORT_BY_RULE`` (1-3, default 2) over its findings.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from odoo_doctor.core.diagnostics import TIER_IMPACT, Diagnostic
from odoo_doctor.core.roi import DEFAULT_EFFORT, EFFORT_BY_RULE
from odoo_doctor.core.text import safe_text

READINESS_SCHEMA_VERSION = 1
CATEGORY = "Upgrade Safety"
OTHER_GROUP = "Other upgrade findings"
# First Odoo major with a migration rule (the rules are gated on 18.0 and 19.0).
FIRST_MIGRATION_MAJOR = 18

# Change group -> its rules, in report order.
_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("View type tree renamed to list", ("view-tree-removed",)),
    ("Chatter div replaced by <chatter/>", ("chatter-div-removed",)),
    ("Kanban legacy templates", ("kanban-legacy-templates",)),
    ("Search view group attributes", ("search-view-group-attributes",)),
    ("View attrs and states removed", ("view-attrs-states-removed",)),
    ("Action target inline removed", ("act-window-target-inline",)),
    ("Removed core fields", ("removed-core-field-usage",)),
    (
        "Removed models and ORM APIs",
        ("removed-model-still-referenced", "removed-orm-api-usage"),
    ),
    ("Deprecated APIs", ("deprecated-api-usage", "deprecated-orm-api-usage")),
    ("Cron removed fields", ("cron-removed-fields",)),
    ("SQL constraints ignored", ("sql-constraints-unsupported",)),
)
RULE_GROUPS: dict[str, str] = {r: g for g, rules in _GROUPS for r in rules}

# Rules whose high-confidence findings are all labelled mechanical: each has a migration
# fixer that repairs every form its rule reports at high confidence (a rule demotes to
# medium the forms the fixer would not repair, e.g. a chatter div with custom content).
MECHANICAL_RULES = frozenset(
    {"view-tree-removed", "chatter-div-removed", "search-view-group-attributes"}
)
# removed-core-field-usage entries that are pure renames: (model, old field) -> new field.
# The rest of that rule's table (category_id, deprecated, mobile, ir.filters.user_id,
# detailed_type) changes meaning or type and stays "needs review". The migration fixer
# (rules/upgrade_safety/fixers.py) renames exactly these, so the label and the fix agree.
MECHANICAL_RENAMES: dict[tuple[str, str], str] = {
    (model, "groups_id"): "group_ids"
    for model in (
        "res.users",
        "ir.ui.view",
        "ir.ui.menu",
        "ir.actions.act_window",
        "ir.actions.server",
        "ir.actions.report",
    )
} | {("res.groups", "users"): "user_ids"}

# Parses the title built in rules/upgrade_safety/removed_core_field_usage.py (emit()):
# the upgrade report depends on its wording; change both together.
_FIELD_TITLE = re.compile(r"^'(\w+)' no longer exists on (\S+) \(Odoo \d+\)$")


def has_migration_rules(version: str) -> bool:
    head = version.split(".", 1)[0]
    return head.isdigit() and int(head) >= FIRST_MIGRATION_MAJOR


def parse_field_title(title: str) -> tuple[str, str] | None:
    """``(model, field)`` from the title of a removed-core-field-usage finding."""
    m = _FIELD_TITLE.match(title)
    return (m.group(2), m.group(1)) if m else None


def is_mechanical(d: Diagnostic) -> bool:
    """Does ``fix --upgrade-to`` fix this finding? (high confidence and in the static tables)"""
    if d.confidence != "high":
        return False
    if d.rule in MECHANICAL_RULES:
        return True
    if d.rule == "removed-core-field-usage":
        return parse_field_title(d.title) in MECHANICAL_RENAMES
    return False


def readiness_score(diagnostics: Iterable[Diagnostic]) -> float:
    points = sum(
        TIER_IMPACT.get(d.tier, 0)
        for d in diagnostics
        if d.category == CATEGORY and d.confidence == "high"
    )
    return round(100 * 100 / (100 + points), 1)


def _summarize(diags: list[Diagnostic]) -> dict:
    mechanical = sum(is_mechanical(d) for d in diags)
    return {
        "findings": len(diags),
        "files": len({d.file_path for d in diags}),
        "effort": sum(EFFORT_BY_RULE.get(d.rule, DEFAULT_EFFORT) for d in diags),
        "mechanical": mechanical,
        "needs_review": len(diags) - mechanical,
    }


def _module_entry(diags: list[Diagnostic]) -> dict:
    by_group: dict[str, list[Diagnostic]] = {}
    for d in diags:
        by_group.setdefault(RULE_GROUPS.get(d.rule, OTHER_GROUP), []).append(d)
    order = [g for g, _ in _GROUPS] + [OTHER_GROUP]
    return {
        "score": readiness_score(diags),
        "groups": [
            {
                "group": g,
                "rules": sorted({d.rule for d in by_group[g]}),
                **_summarize(by_group[g]),
            }
            for g in order
            if g in by_group
        ],
        "totals": _summarize(diags),
    }


def build_upgrade_report(
    diagnostics: Iterable[Diagnostic], modules: Iterable[str], target_version: str
) -> dict:
    """The ``upgrade_report`` payload; every module of the scan gets an entry."""
    by_module: dict[str, list[Diagnostic]] = {m: [] for m in modules}
    for d in diagnostics:
        if d.category == CATEGORY:
            by_module.setdefault(d.module, []).append(d)
    entries = {m: _module_entry(ds) for m, ds in by_module.items()}
    all_diags = [d for ds in by_module.values() for d in ds]
    scores = [e["score"] for e in entries.values()]
    return {
        "readiness_schema_version": READINESS_SCHEMA_VERSION,
        "target_version": target_version,
        "modules": entries,
        "totals": {
            "modules": len(entries),
            "score": round(sum(scores) / len(scores), 1) if scores else 100.0,
            "files": len({(d.module, d.file_path) for d in all_diags}),
            **{k: v for k, v in _summarize(all_diags).items() if k != "files"},
        },
    }


def _split(t: dict) -> str:
    return f"{t['mechanical']} mechanical (`fix --upgrade-to`) / {t['needs_review']} need review"


def render_upgrade_report(report: dict) -> str:
    """Plain-text report for the terminal (no colour, safe to pipe)."""
    lines = [f"Upgrade readiness report (target Odoo {report['target_version']})"]
    for name, mod in report["modules"].items():
        lines.append(f"\n{safe_text(name)}  readiness {mod['score']:.1f}/100")
        if not mod["groups"]:
            lines.append("  no Upgrade Safety findings")
        for g in mod["groups"]:
            lines.append(
                f"  {g['group']}: {g['findings']} finding(s) in {g['files']} file(s), "
                f"effort {g['effort']}; {_split(g)}"
            )
    t = report["totals"]
    lines.append(
        f"\nProject: {t['modules']} module(s), mean readiness {t['score']:.1f}/100, "
        f"{t['findings']} finding(s) in {t['files']} file(s), effort {t['effort']}; {_split(t)}"
    )
    return "\n".join(lines)
