# src/odoo_doctor/rules/rule_docs.py
"""Human-facing documentation for every native rule.

Single source of truth: ``odoo-doctor rules explain``, the generated
``docs/rules.md`` page, SARIF ``helpUri`` and the ``Diagnostic.url`` deep link
are all rendered from this catalog plus the structured ``RuleMeta``. Never edit
``docs/rules.md`` by hand; run ``odoo-doctor rules docs --out docs/rules.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Anchors on the generated page are the bare rule name, so a deep link is stable
# and independent of tier/category changes.
DOCS_BASE_URL = "https://github.com/minhhq-a1/odoo-doctor/blob/main/docs/rules.md"


@dataclass(frozen=True)
class RuleDoc:
    detects: str
    why: str = ""
    fix: str = ""
    bad: str = ""
    good: str = ""
    lang: str = "python"
    notes: str = ""


def rule_doc_url(rule_name: str) -> str | None:
    """Deep link to the documentation of a native rule, or None if unknown."""
    if rule_name not in RULE_DOCS:
        return None
    return f"{DOCS_BASE_URL}#{rule_name}"


RULE_DOCS: dict[str, RuleDoc] = {
    # ------------------------------------------------------------- Security
    "raw-sql-string-interpolation": RuleDoc(
        detects="`cr.execute()` calls that build the query with f-strings, "
        "`%`-formatting, `.format()` or concatenation.",
        why="Interpolating values into SQL leads to SQL injection.",
        fix="Pass values as query parameters.",
        bad="self.env.cr.execute(f\"SELECT * FROM res_partner WHERE name = '{name}'\")",
        good='self.env.cr.execute("SELECT * FROM res_partner WHERE name = %s", (name,))',
        notes="When the dynamic part is not user data (for example a WHERE "
        "fragment whose values are bound through parameters), assert it with "
        "pylint-odoo's marker `# pylint: disable=sql-injection`, which this rule "
        "honours: a trailing comment covers its line, a comment on its own line "
        "covers the rest of the enclosing function. "
        "`# odoo-doctor: disable=raw-sql-string-interpolation` also works. "
        "The rule follows values through local variables, lists (`append`, "
        "`extend`, `+=`), `if`/`try`/loop branches and module constants: SQL "
        "built only from constants, `int()` casts, `self._table`, `SQL(...)` or "
        "`','.join(['%s'] * n)` placeholder lists is not reported, while a "
        "fragment that reaches the query through a list or a branch is. Test code "
        "(`tests/`), `migrations/` and the install-time hooks `init` / `_auto_init` "
        "that take only `self` (where SQL views are created) are skipped: nothing a "
        "request controls reaches them.",
    ),
    "missing-access-csv": RuleDoc(
        detects="Models defined in the module with no row in "
        "`security/ir.model.access.csv` (or no CSV file at all). A model the module "
        "only extends (`_inherit`, with or without repeating its `_name`) needs no "
        "row of its own here.",
        why="A model without access rules is unreachable for non-admin users "
        "and is flagged by Odoo at load time.",
        fix="Create `security/ir.model.access.csv` and add an ACL row per model.",
        bad="# security/ir.model.access.csv is missing a row for my.model",
        good="id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,"
        "perm_unlink\n"
        "access_my_model_user,my.model user,model_my_model,base.group_user,1,1,1,0",
        lang="csv",
    ),
    "eval-usage": RuleDoc(
        detects="Calls to the builtins `eval()` / `exec()` on non-literal input.",
        why="Evaluating dynamic strings allows arbitrary code execution.",
        fix="Use `odoo.tools.safe_eval` for domains/expressions, or refactor to "
        "explicit logic.",
        bad="result = eval(expression)",
        good="from odoo.tools.safe_eval import safe_eval\n"
        "result = safe_eval(expression, {'uid': self.env.uid})",
        notes="An argument provably built from constants (a literal, or a "
        "variable bound only to constants) is not reported; anything else, "
        "including a parameter or a string with interpolated values, is.",
    ),
    "public-controller-sudo-risk": RuleDoc(
        detects="`@http.route` handlers with `auth='public'` or `auth='none'` "
        "that call `.sudo()`.",
        why="Public routes combined with `sudo()` bypass access rights and can "
        "lead to privilege escalation or data leaks.",
        fix="Require authentication, or restrict what the sudo call can reach "
        "and validate the input.",
        bad="@http.route('/api/data', auth='public')\n"
        "def get_data(self):\n"
        "    return request.env['private.model'].sudo().search([])",
        good="@http.route('/api/data', auth='user')\n"
        "def get_data(self):\n"
        "    return request.env['private.model'].search([])",
    ),
    "unsafe-template-render": RuleDoc(
        detects="QWeb `t-raw` output, which renders a value without HTML-escaping. "
        'The safe `t-raw="0"` idiom (the body passed to a `t-call`) is ignored.',
        why="Unescaped output of user-controlled data is a stored or reflected "
        "XSS risk in reports, emails and website pages.",
        fix="Use `t-esc` (or `t-out` on Odoo 17+) so the value is escaped, or only "
        "render raw markup when the value is a trusted `Markup` object.",
        bad='<div t-raw="doc.user_comment"/>',
        good='<div t-esc="doc.user_comment"/>',
        lang="xml",
        notes="Medium confidence: the value may already be sanitized, so it does "
        "not count toward the score by default.",
    ),
    "sudo-without-comment": RuleDoc(
        detects="`.sudo()` calls with no justifying comment on any line of the "
        "statement or directly above it (a compound statement counts only its "
        "header line(s)).",
        why="Every privilege elevation should be reviewable; an undocumented "
        "`sudo()` is hard to audit.",
        fix="Add a short comment explaining why elevated privileges are needed.",
        bad="partner = self.env['res.partner'].sudo().browse(pid)",
        good="# sudo: portal users cannot read partners but need the display name\n"
        "partner = self.env['res.partner'].sudo().browse(pid)",
        notes="`.sudo(False)` (drops privileges), test files and migration scripts "
        "are skipped. A comment on every `sudo()` is a team convention rather than a "
        "defect (Odoo's own addons leave most of theirs uncommented), and addons you "
        "only vendor are best left out with `[ignore] modules`. Low confidence: does "
        'not affect the score, and `min_confidence = "medium"` on a surface hides it.',
    ),
    "record-rule-without-domain": RuleDoc(
        detects="`ir.rule` records without a restricting `domain_force`.",
        why="A rule with an empty domain either grants or denies everything and "
        "rarely expresses the intended restriction.",
        fix="Add a `domain_force` that limits the records the rule applies to.",
        bad='<record id="my_rule" model="ir.rule">\n'
        '    <field name="model_id" ref="model_my_model"/>\n'
        "</record>",
        good='<record id="my_rule" model="ir.rule">\n'
        '    <field name="model_id" ref="model_my_model"/>\n'
        "    <field name=\"domain_force\">[('user_id', '=', user.id)]</field>\n"
        "</record>",
        lang="xml",
        notes="Medium confidence: does not affect the score.",
    ),
    # ---------------------------------------------------------- Correctness
    "unknown-model-in-access-csv": RuleDoc(
        detects="Rows in `ir.model.access.csv` whose model does not exist.",
        why="The CSV load fails (or silently grants nothing) when the model "
        "cannot be resolved.",
        fix="Correct the `model_id:id` to match the model's `_name`.",
        bad="access_x,x,model_my_modle,base.group_user,1,0,0,0",
        good="access_x,x,model_my_model,base.group_user,1,0,0,0",
        lang="csv",
    ),
    "duplicate-xml-id": RuleDoc(
        detects="The same XML ID declared more than once in a module.",
        why="The later record silently overwrites the earlier one.",
        fix="Remove or rename the duplicate.",
    ),
    "missing-xml-ref": RuleDoc(
        detects='`ref="..."`, `eval="ref(...)"` and `inherit_id` references '
        "that cannot be resolved.",
        why="Unresolved references abort the module install/update.",
        fix="Verify the referenced XML ID exists and that the providing module "
        "is listed in `depends`.",
    ),
    "view-field-not-in-model": RuleDoc(
        detects="Views that reference fields not found on the model.",
        why="Odoo rejects the view at load time.",
        fix="Add the field to the model or remove it from the view.",
        notes="Fires with high confidence only when the model is known (stubs or "
        "this repository) and the field provably does not exist.",
    ),
    "button-method-not-found": RuleDoc(
        detects='Buttons with `type="object"` calling a method that does not '
        "exist on the model.",
        why="Clicking the button raises an error at runtime.",
        fix="Add the method to the model or fix the button's `name`.",
    ),
    "override-missing-super": RuleDoc(
        detects="Overrides of ORM methods (`create`, `write`, `unlink`, ...) "
        "that never call `super()`.",
        why="Skipping `super()` breaks the method chain and bypasses parent "
        "logic, validation and hooks.",
        fix="Call and return the parent implementation.",
        bad="def create(self, vals):\n    return self.env['res.partner'].create(vals)",
        good="def create(self, vals):\n"
        "    record = super().create(vals)\n"
        "    return record",
    ),
    "compute-missing-depends": RuleDoc(
        detects="Compute methods that read fields not declared in `@api.depends`.",
        why="Missing dependencies leave computed values stale.",
        fix="List every field the computation reads.",
        bad="@api.depends('quantity')\n"
        "def _compute_total(self):\n"
        "    for rec in self:\n"
        "        rec.total = rec.quantity * rec.unit_price",
        good="@api.depends('quantity', 'unit_price')\n"
        "def _compute_total(self):\n"
        "    for rec in self:\n"
        "        rec.total = rec.quantity * rec.unit_price",
        notes="A field the method assigns (`rec.total = ...`) is its result, not an "
        "input, so reading it back inside the same method is not reported.",
    ),
    # ---------------------------------------------------------- Performance
    "search-in-loop": RuleDoc(
        detects="ORM queries (`search`, `search_count`, `read`) inside `for` or "
        "`while` loops. `browse()` is not flagged: it only wraps ids and does "
        "not query the database.",
        why="One query per iteration scales badly with record count.",
        fix="Move the call out of the loop and batch the results.",
        bad="for line in lines:\n"
        "    partner = self.env['res.partner'].search([('id', '=', line.pid)])",
        good="partners = self.env['res.partner'].search([('id', 'in', lines.mapped('pid'))])\n"
        "by_id = {p.id: p for p in partners}",
        notes="The performance rules skip files inside an addon's `tests/` directory.",
    ),
    "create-in-loop": RuleDoc(
        detects="`create()` called inside a loop.",
        why="Each call triggers its own INSERT and recomputation round trip.",
        fix="Collect the values and call `create()` once with a list.",
        bad="for vals in vals_list:\n    self.env['my.model'].create(vals)",
        good="self.env['my.model'].create(vals_list)",
    ),
    "write-in-loop": RuleDoc(
        detects="`write()` called inside a loop.",
        why="Each call triggers its own UPDATE and recomputation round trip.",
        fix="Write once on the whole recordset when the values are identical.",
        bad="for rec in records:\n    rec.write({'state': 'done'})",
        good="records.write({'state': 'done'})",
    ),
    "n-plus-one-read": RuleDoc(
        detects="Chained relational attribute access (`rec.partner_id.name`) on "
        "the loop variable inside a loop.",
        why="Can trigger one query per record when the prefetch cache is cold.",
        fix="Prefetch related records before looping, or read the needed fields "
        "in one batch.",
        notes="Low confidence: does not affect the score.",
    ),
    "unbounded-search": RuleDoc(
        detects="`search()` / `read()` calls with no `limit` in risky contexts.",
        why="Unbounded searches can load a whole table into memory.",
        fix="Add a `limit` or restrict the domain.",
        bad="records = self.env['res.partner'].search([('country_id', '=', cid)])",
        good="records = self.env['res.partner'].search(\n"
        "    [('country_id', '=', cid)], limit=100\n)",
    ),
    "expensive-nonstored-compute": RuleDoc(
        detects="Computed fields that are not stored (`store=True` missing) "
        "whose compute method runs `search`, `search_count`, `search_read` or "
        "`read_group` on an ORM object.",
        why="A non-stored field is recomputed on every read, including list "
        "views, exports and `search_read`, so each display pays for the query.",
        fix="Store the field with a complete `@api.depends`, or move the "
        "aggregate into a stored field or a `read_group` at the call site.",
        bad="total_orders = fields.Integer(compute='_compute_total_orders')\n\n"
        "def _compute_total_orders(self):\n"
        "    for rec in self:\n"
        "        rec.total_orders = self.env['sale.order'].search_count(\n"
        "            [('partner_id', '=', rec.id)]\n"
        "        )",
        good="total_orders = fields.Integer(\n"
        "    compute='_compute_total_orders', store=True\n)\n\n"
        "@api.depends('order_ids')\n"
        "def _compute_total_orders(self):\n"
        "    for rec in self:\n"
        "        rec.total_orders = len(rec.order_ids)",
        notes="Medium confidence: does not affect the score. Complements "
        "`search-in-loop`, which flags the query-per-record pattern itself.",
    ),
    # ----------------------------------------------------------- Module Hygiene
    "manifest-missing-required-fields": RuleDoc(
        detects="`__manifest__.py` missing one of `name`, `version`, `depends`, "
        "`data`, `license`.",
        fix="Add the missing key. Run `odoo-doctor fix` to apply it automatically.",
        notes="Fixable via `odoo-doctor fix`. `installable` is not required "
        "(Odoo defaults it to `True`), and `data` is not required when the "
        "manifest declares `assets` or `demo`.",
    ),
    "manifest-data-order-risk": RuleDoc(
        detects="`data` files in the manifest listed in an unsafe load order "
        "(for example a security file after views/actions).",
        why="Wrong order causes missing references or access rights at load time.",
        fix="Order data files by dependency: security first, then views, then data.",
        bad="'data': [\n"
        "    'views/my_views.xml',\n"
        "    'security/ir.model.access.csv',\n"
        "]",
        good="'data': [\n"
        "    'security/ir.model.access.csv',\n"
        "    'views/my_views.xml',\n"
        "]",
        notes="Fixable via `odoo-doctor fix`.",
    ),
    "manifest-missing-dependency": RuleDoc(
        detects="Modules required by Python `_inherit` models, XML external ID "
        'references (including `eval="ref(...)"`) and inherited views that are '
        "not listed in `depends`.",
        why="The module installs only when another module happens to be "
        "installed first.",
        fix="Add the providing module to `depends`.",
        notes="A module reachable through `depends` transitively counts as "
        "available. When part of that chain is a module whose manifest is "
        "unknown (set `odoo_source_path` to index core addons), the finding is "
        "reported with medium confidence and does not affect the score.",
    ),
    # ------------------------------------------------------- Maintainability
    "orphan-view": RuleDoc(
        detects="Extra primary views that are not their model's default view of that "
        "type and that nothing in the module references or inherits.",
        fix="Reference the view, inherit it, or remove it if unused.",
        notes="Odoo serves a model's primary view of each type (lowest `priority`, "
        "then first defined) without any reference, so that one is never flagged; "
        "neither are QWeb views or ids mentioned in Python, JS, XML or CSV. Medium "
        "confidence: the reference may live in a module that was not scanned. Does "
        "not affect the score.",
    ),
    "field-no-string-on-required": RuleDoc(
        detects="`required=True` fields without an explicit `string`.",
        why="Auto-generated labels produce unclear validation errors and are "
        "hard to translate.",
        fix='Add `string="..."`.',
        bad="name = fields.Char(required=True)",
        good='name = fields.Char(string="Name", required=True)',
        notes="Medium confidence: does not affect the score.",
    ),
    "missing-translation": RuleDoc(
        detects="`UserError` / `ValidationError` messages not wrapped in `_()`.",
        why="Untranslated messages stay in English for every user.",
        fix='Wrap the message with `_("...")`.',
        bad='raise UserError("Amount must be positive")',
        good='raise UserError(_("Amount must be positive"))',
        notes="Medium confidence: does not affect the score.",
    ),
    # --------------------------------------------------------- Data Integrity
    "missing-ondelete": RuleDoc(
        detects="`Many2one` fields on non-transient, non-abstract models "
        "without an explicit `ondelete`.",
        why="The implicit `set null` policy is rarely a conscious choice; "
        "declaring it documents the intended behavior.",
        fix="Declare `ondelete` explicitly.",
        bad='partner_id = fields.Many2one("res.partner")',
        good='partner_id = fields.Many2one("res.partner", ondelete="restrict")',
        notes="Required `Many2one` fields are skipped: Odoo already defaults "
        "them to `restrict`. So are related or computed fields that are not stored "
        "(no `store=True`): they have no foreign-key column.",
    ),
    "data-noupdate-risk": RuleDoc(
        detects="Records of critical models (`ir.rule`, `ir.config_parameter`, "
        '`ir.cron`) in XML data files outside `noupdate="1"`.',
        why="Records without `noupdate` are overwritten on every module update, "
        "discarding user changes.",
        fix='Wrap the records in `<data noupdate="1">`.',
        bad='<record id="my_rule" model="ir.rule">...</record>',
        good='<data noupdate="1">\n'
        '    <record id="my_rule" model="ir.rule">...</record>\n'
        "</data>",
        lang="xml",
        notes="`ir.rule` records are reported with medium confidence (not "
        "scored): Odoo core wraps them in `noupdate` while many addons keep "
        "them updatable so rule fixes ship with the module. "
        "`ir.config_parameter` and `ir.cron` stay high confidence.",
    ),
    # --------------------------------------------------------- Upgrade Safety
    "deprecated-api-usage": RuleDoc(
        detects="Old-API patterns: `from openerp` imports, `_columns`, "
        "`osv.osv` and model calls through the pool with `cr, uid`.",
        why="They belong to Odoo 7-9 and are removed in modern versions.",
        fix="Migrate to the new API.",
        bad="from openerp import models\n"
        "class MyModel(osv.osv): ...\n"
        "self.pool.get('res.partner').search(cr, uid, [])",
        good="from odoo import models\n"
        "class MyModel(models.Model): ...\n"
        "self.env['res.partner'].search([])",
        notes="`self.pool['model']` alone is the registry (a model class, used for "
        "`isinstance` checks) and is not reported. Scripts in `migrations/<version>/` "
        "for a version before Odoo 10 may import `openerp`: they ran on databases of "
        "that era.",
    ),
    "removed-model-still-referenced": RuleDoc(
        detects="`_inherit` of a core model that Odoo removed or renamed at or before "
        "the target version (for example `account.invoice`, `stock.production.lot`, "
        "`mail.channel`) and that the project does not define itself.",
        why="Models are removed or renamed between versions; inheriting a "
        "missing model breaks the registry load.",
        fix="Port the code to the replacement model named in the finding.",
        notes="Based on a curated list of certain removals: a model that is merely "
        "absent from the scanned set is usually an unscanned dependency and is not "
        "reported. Medium confidence: does not affect the score.",
    ),
    # --------------------------------------------------------------- Frontend
    "asset-bundle-missing": RuleDoc(
        detects="Files listed in the manifest `assets` dict that do not exist on disk.",
        why="Missing assets cause JavaScript/CSS loading errors in the web client.",
        fix="Create the file or remove the manifest entry.",
        bad="'assets': {\n"
        "    'web.assets_backend': ['my_module/static/src/js/missing.js'],\n"
        "}",
        good="# create static/src/js/missing.js, or drop the entry above",
    ),
    # -------------------------------------------- Multi-company / multi-currency
    "monetary-missing-currency-field": RuleDoc(
        detects="`fields.Monetary` fields whose currency field (`currency_id`, "
        "or the one named by `currency_field=`) provably does not exist on the "
        "model, including its `_inherit`/`_inherits` ancestors and extensions in "
        "other scanned modules.",
        why="A Monetary field needs a currency to be stored, rounded and "
        "displayed; without it Odoo raises at runtime or shows no currency.",
        fix="Add the currency field, or point `currency_field=` at an existing "
        "Many2one to `res.currency`.",
        bad='amount = fields.Monetary(string="Amount")',
        good='currency_id = fields.Many2one("res.currency")\n'
        'amount = fields.Monetary(string="Amount")',
        notes="Only reported when absence is provable; models that extend an "
        "upstream model you do not define here are skipped.",
    ),
    "missing-multicompany-rule": RuleDoc(
        detects="Models defined in the module with a `company_id` Many2one to "
        "`res.company` that no `ir.rule` in the scanned modules protects.",
        why="Without a company record rule, users of one company can read and "
        "edit another company's records in a multi-company database.",
        fix="Add an `ir.rule` restricting records to `company_ids`.",
        bad='company_id = fields.Many2one("res.company", required=True)\n'
        '# ... and no <record model="ir.rule"> for this model',
        good='<record id="my_model_comp_rule" model="ir.rule">\n'
        '    <field name="name">My model multi-company</field>\n'
        '    <field name="model_id" ref="model_my_model"/>\n'
        "    <field name=\"domain_force\">[('company_id', 'in', company_ids)]"
        "</field>\n"
        "</record>",
        lang="xml",
        notes="Medium confidence (does not affect the score): the rule may live "
        "in an addon that was not scanned. Transient and abstract models are "
        "skipped.",
    ),
    "hardcoded-company-or-currency": RuleDoc(
        detects="`env.ref('base.main_company')` and `env.ref('base.USD')`-style "
        "references to a specific currency in business code.",
        why="In a multi-company or multi-currency database these pick the wrong "
        "record.",
        fix="Use `self.env.company`, `self.env.company.currency_id`, or the "
        "document's own `company_id` / `currency_id`.",
        bad='company = self.env.ref("base.main_company")',
        good="company = self.env.company",
        notes="Medium confidence (does not affect the score). Install hooks "
        "(`*_hook` functions, `hooks.py`), `migrations/` and `tests/` are skipped.",
    ),
    # ------------------------------------------------------------ Supply chain
    "manifest-license-incompatible": RuleDoc(
        detects="An addon whose manifest `license` conflicts with the license of a "
        "scanned dependency: GPL-2 (version 2 only) combined with a GPL-3 family "
        "license in either direction (high confidence), or a proprietary module "
        "(OPL-1, OEEL-1) depending on GPL/AGPL code (medium confidence).",
        why="The combination cannot be distributed under both licenses.",
        fix="Relicense one module or drop the dependency; check with the licensing owner.",
        notes="Only dependencies whose manifest was scanned are compared.",
    ),
    "missing-external-dependency": RuleDoc(
        detects="Third-party Python packages imported by the addon but not listed "
        "in `external_dependencies['python']` (of the addon or of a module it "
        "depends on).",
        why="Installing without the package fails at import time instead of with "
        "a clear dependency error.",
        fix='Add `"external_dependencies": {"python": ["pkg"]}` to the manifest, or '
        "guard an optional import with `try/except ImportError`.",
        notes="Skipped: stdlib, packages Odoo itself installs, guarded and "
        "`TYPE_CHECKING` imports, `tests/` and `migrations/`. Medium confidence "
        "when the dependency chain includes a module whose manifest was not scanned.",
    ),
    "vendored-python-code": RuleDoc(
        detects="Third-party Python code copied into an addon: `vendor/`, `lib/` "
        "and similar directories containing `.py` files, `*.dist-info` / "
        "`*.egg-info`, or a well-known package (for example `six/`) at the top level.",
        why="Copied code misses security fixes and can clash with the installed version.",
        fix="Declare the package in `external_dependencies['python']` instead.",
        notes="Medium confidence (does not affect the score). JavaScript libraries "
        "under `static/` are normal in Odoo and are not reported.",
    ),
}
