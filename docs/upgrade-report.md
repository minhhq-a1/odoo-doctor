# Upgrade readiness report

`scan --upgrade-report` answers one question: how far is this module from running on the
Odoo version you are moving to (for example 19.0)? It takes the **Upgrade Safety** findings
of the scan, groups them by kind of change, says how much of each group is a mechanical
rename and how much needs a human, and gives every module a readiness score from 0 to 100.

It is a static estimate. It reports nothing that no rule covers (see [Limits](#limits)), and
it changes no file.

## Run it

```bash
odoo-doctor scan . --odoo-version 19.0 --upgrade-report          # terminal
odoo-doctor scan . --odoo-version 19.0 --upgrade-report --json   # data for CI and agents
```

`--odoo-version` is the **target**. With `--upgrade-report --odoo-version X` every module is
evaluated as targeting X, whatever version its manifest declares. Without `--odoo-version`
the rules are gated on each module's own manifest version, so a module that declares `17.0.x`
shows an empty report; odoo-doctor then prints one warning on stderr naming up to three such
modules and asking for `--odoo-version 19.0`: the report is empty because no target was given,
not because the code is ready. `--odoo-version 19.0` alone keeps its old meaning (a normal scan as 19.0); the report
is only added by the flag. SARIF, GitHub annotations and HTML ignore the flag (a note on
stderr). Exit codes and every other output are unchanged.

Terminal output (trimmed to one module; scan of the Odoo 17.0 `hr_holidays` addon as 19.0):

```text
Upgrade readiness report (target Odoo 19.0)

hr_holidays  readiness 14.7/100
  View type tree renamed to list: 30 finding(s) in 10 file(s), effort 30; 30 mechanical (`fix --upgrade-to`) / 0 need review
  Chatter div replaced by <chatter/>: 3 finding(s) in 2 file(s), effort 3; 3 mechanical (`fix --upgrade-to`) / 0 need review
  Kanban legacy templates: 4 finding(s) in 4 file(s), effort 12; 0 mechanical (`fix --upgrade-to`) / 4 need review
  Search view group attributes: 4 finding(s) in 4 file(s), effort 4; 4 mechanical (`fix --upgrade-to`) / 0 need review
  Removed core fields: 10 finding(s) in 6 file(s), effort 20; 4 mechanical (`fix --upgrade-to`) / 6 need review
  Deprecated APIs: 12 finding(s) in 2 file(s), effort 12; 0 mechanical (`fix --upgrade-to`) / 12 need review
  Cron removed fields: 2 finding(s) in 1 file(s), effort 2; 0 mechanical (`fix --upgrade-to`) / 2 need review
  SQL constraints ignored: 5 finding(s) in 5 file(s), effort 10; 0 mechanical (`fix --upgrade-to`) / 5 need review
```

Read a line as: *kind of change: how many findings in how many files, estimated effort;
how many are mechanical renames and how many need review.* The readiness score of the
module comes first; the project line at the end has the totals and the mean score.

## JSON

`--json` adds one top-level key, `upgrade_report`, only when the flag is on. Nothing else in
the JSON changes and `score_schema_version` stays as it is.

```json
{
  "upgrade_report": {
    "readiness_schema_version": 1,
    "target_version": "19.0",
    "modules": {
      "hr_holidays": {
        "score": 14.7,
        "groups": [
          {"group": "View type tree renamed to list", "rules": ["view-tree-removed"],
           "findings": 30, "files": 10, "effort": 30, "mechanical": 30, "needs_review": 0}
        ],
        "totals": {"findings": 70, "files": 21, "effort": 93, "mechanical": 41, "needs_review": 29}
      }
    },
    "totals": {"modules": 1, "score": 14.7, "files": 21, "findings": 70,
               "effort": 93, "mechanical": 41, "needs_review": 29}
  }
}
```

Every module of the scan has an entry (score 100.0 and empty `groups` when it has no
findings). `totals.findings` equals the number of Upgrade Safety findings of the same scan.
The `readiness_schema_version` is bumped when the formula below changes. The key is part of
the [stability contract](stability.md).

## Readiness formula

Per module, using the same tier weights as the health score (`P0=25`, `P1=10`, `P2=4`,
`P3=1`):

```text
points    = sum of the tier weight of each high-confidence Upgrade Safety finding
readiness = round(100 * 100 / (100 + points), 1)
```

A module with no such finding scores 100. The score falls as points grow but never reaches
0, so a module with 5 findings and one with 500 still rank differently (a linear
`100 - points` would be 0 after ten P1 findings, and large addons have hundreds).

Worked example: a module with 3 `P1` findings (30 points) and 1 `P2` finding (4 points), all
`high`, plus 5 `medium` findings. The `medium` ones do not count: `points = 34` and
`readiness = 100 * 100 / 134 = 74.6`.

Notes:

- Only `high` findings count. `medium` and `low` are shown in the group counts but not
  scored, the same rule the health score uses.
- Mechanical findings count like the others: they are still work to do.
- The project score is the mean of the module scores.

## Mechanical or needs review

Each finding is labelled from a **static table** in `core/upgrade.py` (`MECHANICAL_RULES`,
`MECHANICAL_FIELDS`); the label is never guessed from the finding's text or from the code
around it. "Mechanical" means a rename that needs no decision.

- Rule level: `view-tree-removed` (`<tree>` to `<list>`, `view_mode`, `(False, 'tree')`
  pairs), `chatter-div-removed` and `search-view-group-attributes`.
- Entry level, for `removed-core-field-usage`: only the pure renames `groups_id` to
  `group_ids` (on `res.users`, `ir.ui.view`, `ir.ui.menu`, `ir.actions.act_window`,
  `ir.actions.server`, `ir.actions.report`) and `res.groups.users` to `user_ids`. The other
  entries (`category_id`, `deprecated`, `mobile`, `ir.filters.user_id`, `detailed_type`)
  change meaning or type and stay "needs review".
- Everything else (kanban templates, `attrs`/`states`, action `target`, removed models and
  ORM APIs, deprecated APIs, cron fields, `_sql_constraints`) needs review, and so does any
  rule not in the table, including plugin rules.

**Only `high` findings can be mechanical.** A `medium` finding is a guess about what the code
refers to: `groups_id` found in Python could belong to any model, and a `view_mode` in a
Python dict that does not look like an action may be unrelated data. The future `fix` command
applies only `high` findings (see [stability.md](stability.md) and `core/fixer.py`), so a
`medium` finding is never promised as mechanical.

**Mechanical means `fix --upgrade-to` fixes it.** Every `high` finding of a mechanical rule is repaired by
the migration fixer in every form the rule reports it at `high`: `view-tree-removed` covers `<tree>` elements
(also nested), XPath steps named `tree`, `<field name="type">tree</field>`, x2many `mode="tree"`, `tree_view_ref` in a view `context`, `view_mode` in XML (text and
`eval=`) and in Python action dicts, and `(id, 'tree')` pairs. A form the fixer could not repair safely is
reported at `medium` instead: `chatter-div-removed` is `high` only for a div that has just the class
`oe_chatter`, holds only the standard chatter fields with no attribute but `name` (or nothing) and sits under the root of the view or in an
`xpath` body; any other div needs a person. The coverage is checked by a test: after the fix the report shows no
mechanical finding left.

## Fixing the mechanical part

```bash
odoo-doctor fix . --upgrade-to 19.0 --fix-dry-run   # the diff, nothing written
odoo-doctor fix . --upgrade-to 19.0 --fix           # apply, then print what is left
```

`--upgrade-to` is the target; it replaces `--odoo-version` (passing both exits 3), must be 18.0 or later, and
evaluates every module as that version. Without it no migration fixer runs, even when a manifest or the config
already says 19.0, because fixing `<tree>` to `<list>` stops the module from running on 17. The fixes edit the
text of the record that has the finding and nothing else (line endings, BOM, comments and indentation stay); a
result that no longer parses is dropped and listed as not fixed. A finding silenced by `odoo-doctor: disable` or
`[ignore]` is not fixed. `version` and `depends` in the manifest are never touched; the command reminds you when
a manifest still names an older Odoo. After `--fix` the report of what is left (the "need review" part) is
printed, from a second scan.

## Effort

The effort of a group is the sum over its findings of `EFFORT_BY_RULE` (1 to 3, default 2), the same table that orders *Fix first*. It is a relative
number for comparing groups and modules, not hours.

## How to use it

1. Run the report with the target version and read the module with the lowest readiness.
2. Start with groups that are all mechanical: they are many findings for little thinking.
3. Plan the "needs review" groups by effort; they hold the real design decisions.
4. Re-run after each step: the totals and scores move, and `--json` lets CI track them.

## Limits

- Static analysis only. Nothing is imported or executed, so runtime behaviour changes, data
  migrations and third-party modules are invisible.
- The report covers only the Upgrade Safety rules odoo-doctor has (13 today). A change no
  rule knows is not counted: a score of 100 means "no known problem", not "will run on 19".
- The explicit target overrides the manifest version only in report mode. A plain
  `scan --odoo-version 19.0` still gates each module on its manifest version, so a `17.0.x`
  module has no migration findings there; use `--upgrade-report` for that question.
- Rules are version-gated (see [support.md](support.md)); the report is only meaningful for a
  target of 18.0 or later.
- A scan restricted with `--module` does not see the other modules, so cross-module
  findings can differ from a full scan (for instance `removed-model-still-referenced` on a
  model another module of the tree still defines).
- The score is a ranking aid, not a measure of hours.

## Rule, change group and migration topic

The last column names the Odoo change the rule is about. It comes from the rule's own
documentation and code, checked against the Odoo sources where they state it. It is a topic
name, not a link: look the topic up in the release and upgrade notes of the Odoo version
named in the third column.

| Rule | Change group | Mechanical | Odoo migration topic |
| --- | --- | --- | --- |
| `view-tree-removed` | View type tree renamed to list | yes (`high`) | Odoo 18: the `tree` view type and view mode were renamed `list` |
| `chatter-div-removed` | Chatter div replaced by `<chatter/>` | yes (`high`) | Odoo 18: form chatter is the `<chatter/>` tag, `div.oe_chatter` is no longer compiled |
| `kanban-legacy-templates` | Kanban legacy templates | no | Odoo 19: kanban templates `kanban-box` and `kanban-menu` are now `card` and `menu` (18 still read the old names) |
| `search-view-group-attributes` | Search view group attributes | yes (`high`) | Odoo 19: the search view schema no longer accepts `string` and `expand` on `<group>` |
| `view-attrs-states-removed` | View attrs and states removed | no | Odoo 17: the `attrs` and `states` view attributes are no longer used (the 19.0 source raises "Since 17.0, the attrs and states attributes are no longer used") |
| `act-window-target-inline` | Action target inline removed | no | Odoo 19: `inline` removed from the `target` selection of window actions |
| `removed-core-field-usage` | Removed core fields | per entry: `groups_id` and `res.groups.users` yes (`high`); `category_id`, `deprecated`, `mobile`, `ir.filters.user_id`, `detailed_type` no | Odoo 18: `product` `detailed_type` merged into `type` plus `is_storable`; Odoo 19: `groups_id` is `group_ids`, `res.groups.users` is `user_ids`, group category moved to a privilege record, `mobile` merged into `phone`, `account.account.deprecated` is `active`, `ir.filters.user_id` is `user_ids` |
| `removed-model-still-referenced` | Removed models and ORM APIs | no | Core models removed or renamed per release: `ir.property` (18), `stock.valuation.layer`, `stock.quant.package`, `hr.employee.base`, `res.partner.title` (19), plus older ones (`account.invoice`, `mail.channel`, ...) |
| `removed-orm-api-usage` | Removed models and ORM APIs | no | ORM methods removed: `fields_view_get` and `invalidate_cache` (17), `name_get` (18) |
| `deprecated-orm-api-usage` | Deprecated APIs | no | ORM methods deprecated: `check_access_rights` / `check_access_rule` / `_check_recursion` (18), `read_group` / `toggle_active` (19), see the `@api.deprecated` messages in the ORM source |
| `deprecated-api-usage` | Deprecated APIs | no | Pre-Odoo 10 API (`openerp` namespace, `_columns`, `osv.osv`, `.pool`) |
| `cron-removed-fields` | Cron removed fields | no | Odoo 18: `numbercall` and `doall` removed from `ir.cron` |
| `sql-constraints-unsupported` | SQL constraints ignored | no | Odoo 19: `_sql_constraints` is no longer read (it only logs a warning); constraints are declared as `models.Constraint` attributes |

Per-rule details, confidence and examples: [rules.md](rules.md).
