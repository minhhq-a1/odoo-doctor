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
        detects="`execute()`, `executemany()` and `copy_expert()` calls on a cursor (`cr`, "
        "`env.cr`, `request.env.cr`, `request.cr`, `registry.cursor()` / `self.pool.cursor()` "
        "and names bound to them), and Odoo 17+ `env.execute_query(...)` on `self.env` / "
        "`env` / `request.env`, that build "
        "the query (SELECT, DML or DDL such as DROP / ALTER / TRUNCATE / WITH) with "
        "f-strings, `%`-formatting, `.format()` or concatenation, also inside `SQL(...)`. "
        "Tuple unpacking and `:=` carry the state.",
        why="Interpolating values into SQL leads to SQL injection.",
        fix="Pass values as query parameters.",
        bad="self.env.cr.execute(f\"SELECT * FROM res_partner WHERE name = '{name}'\")",
        good='self.env.cr.execute("SELECT * FROM res_partner WHERE name = %s", (name,))',
        notes="`<anything>._table` is a trusted identifier (set by the model author and "
        "validated by the registry), and scripts under `tests/`, `migrations/` and "
        "`upgrades/` (Odoo 18+) are skipped. "
        "When the dynamic part is not user data (for example a WHERE "
        "fragment whose values are bound through parameters), assert it with "
        "pylint-odoo's marker `# pylint: disable=sql-injection`, which this rule "
        "honours: a trailing comment covers its line, a comment on its own line "
        "covers the rest of the enclosing function. "
        "`# odoo-doctor: disable=raw-sql-string-interpolation` also works. "
        "The rule follows values through local variables, lists (`append`, "
        "`extend`, `+=`), `if`/`try`/loop branches and module constants: SQL "
        'built only from constants, `int()` casts, `self._table`, `SQL("... %s", x)` '
        "(parameters passed separately) or `','.join(['%s'] * n)` placeholder lists is "
        'not reported, while `SQL(f"...{x}")` (or `+`, `%`, `.format()` building the '
        "SQL string) and a "
        "fragment that reaches the query through a list or a branch is. Test code "
        "(`tests/`), `migrations/` and the install-time hooks `init` / `_auto_init` "
        "that take only `self` (where SQL views are created) are skipped: nothing a "
        "request controls reaches them. Known limits: `SQL` is recognised by its "
        "name, so an import alias (`from odoo.tools import SQL as S`) is not followed, "
        "and a statement that starts with a SQL comment (`-- ...` or `/* ... */`) "
        "defeats the statement-start check of the DDL/`WITH`/`COPY` heuristics. "
        "Also not reported: `%d` / `%i` / `%f` formatting (a non-number raises, so "
        '`"... LIMIT %d" % n` cannot inject), the clauses of an Odoo `Query` '
        "(`query.get_sql()`, `query.select()` / `.subselect()` with constant arguments), "
        "a record's `.id`, `Datetime.now()`-style calls, and a name checked with "
        '`if op not in ("<", "="): return` (or `raise`) before it is used. '
        "Confidence: `high` when the text of the query is built from something a "
        "caller outside the module controls: a parameter (including `**kw` / `post`) of a "
        "public method (RPC reaches those) or of a route, what the request carries "
        "(`request.params`, `request.httprequest`, `request.get_json_data()`, cookies), "
        "a public field of `self` (`self.name`: a wizard's fields are typed in by the user, "
        "also through `self.mapped('name')` and `for rec in self`), and the same values "
        "handed on to a private helper of the same class or a module-level function of the "
        "same file (`self._q(term)`, up to 3 hops), whatever else is interpolated next to "
        "them. Everything else that is dynamic is `medium`: model metadata and ORM-built "
        "fragments (`self._where()`, `self._sequence_field`, `self.env.context`), a "
        "private helper that only literals reach, a module-level function no entry point "
        "calls, and the ORM hooks with a leading underscore that the ORM feeds from RPC "
        "arguments (`_search`, `_read_group`, `_name_search`, `_search_*` field search "
        "methods: an `order`, `groupby` or name typed by a client can reach them; this is a "
        "documented limit, review them). Odoo's own addons write dynamic SQL that way "
        "(Odoo 19: 0 `high`, 9 `medium`). A `medium` finding is listed but does not lower "
        "the score and does not trip the default `--fail-on` policy (P0/P1 high "
        "confidence). Calls on another class's helper, through inheritance or a callback "
        "are not followed.",
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
        fix="Use `ast.literal_eval` for a stored literal (a domain, a list), "
        "`odoo.tools.safe_eval.safe_eval` for an expression that needs variables, "
        "or refactor to explicit logic.",
        bad="result = eval(expression)",
        good="from odoo.tools.safe_eval import safe_eval\n"
        "result = safe_eval(expression, {'uid': self.env.uid})",
        notes="An argument provably built from constants (a literal, or a "
        "variable bound only to constants) is not reported; anything else, "
        "including a parameter or a string with interpolated values, is. The "
        "message shows the evaluated expression. A module that binds the name "
        "itself (`from odoo.tools.safe_eval import safe_eval as eval`, an Odoo 8/9 "
        "idiom) is calling that function, not the builtin, and is not reported. "
        "Odoo 19 community contains one bare `exec` (the `shell` command), so a "
        "finding here is almost always genuine.",
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
        notes="A route that also calls an access check (`consteq` on an access "
        "token, `_document_check_access`, a signature or `check_access*` call) is "
        "reported at medium confidence and does not affect the score; without one "
        "it is high. `.sudo(False)` and `env['ir.config_parameter'].sudo()"
        ".get_param('<constant>')` are not elevations. Public website routes "
        "legitimately use `sudo()`: about one in five routes of Odoo 19 community "
        "does, so review rather than ban. A route that omits `auth` (a bare "
        "`@http.route()` override) keeps the auth of the route it overrides, found "
        "through the classes of the scanned addons; when the parent is not among "
        "them (`WebsiteSale`, `CustomerPortal` of an addon that is not scanned) the "
        "auth is unknown. A `sudo()` in such a route is reported at medium (low after "
        "an access check), whether the inherited auth is public or unknown: Odoo's "
        "own addons override public routes and elevate in them as a convention. "
        "State `auth=` on the route to grade it like any other. Parents are matched by "
        "class NAME, in base order: an unrelated scanned `class Main(http.Controller)` "
        "with `auth='user'` can capture a subclass that imports another addon's "
        "`Main`, and several scanned classes of one name with different autos give "
        "unknown. `[target_modules]` limits discovery, so a parent in a module that "
        "is not a target is not found and the auth is unknown, as is a computed "
        "`auth=CONST`. The grade of an explicit `auth='public'` with `sudo()` (high; "
        "151 hits in Odoo 19 community, mostly conventions) is a pre-existing "
        "choice; the inherited grade is deliberately medium.",
    ),
    "access-write-without-group": RuleDoc(
        detects="Rows in `ir.model.access.csv` with an empty `group_id:id` that grant "
        "`perm_write`, `perm_unlink` or `perm_create`. Rows for wizards "
        "(`TransientModel`) are ignored.",
        why="A row without a group applies to every user, portal and public users "
        "included, so anyone can modify or delete the model's records.",
        fix="Set `group_id:id` to `base.group_user` or a dedicated group, and keep "
        "the group-less row read-only if it must stay.",
        bad="access_x,x,model_x,,1,1,1,1",
        good="access_x,x,model_x,base.group_user,1,1,1,1",
        lang="csv",
        notes="A row that only grants `create` is reported at medium confidence and "
        "does not affect the score: public forms create records anonymously on purpose.",
    ),
    "dynamic-method-dispatch": RuleDoc(
        detects="`getattr(obj, name)(...)` (called directly or through a variable) "
        "where `name` is not a constant. A name built on a constant prefix "
        "(`'_get_%s' % kind`), looked up in a module-level table, checked in the "
        "same function (`in` / `==`, `startswith`), taken from a logger, taken from "
        "a literal tuple or `fn.__name__`, the name of a `__getattr__` hook, or "
        "passed to a helper of the file that refuses ORM methods "
        "(`hasattr(models.BaseModel, name)`) is ignored.",
        why="Whoever controls the name can run any method of the object, ORM methods "
        "such as `unlink()` or `sudo()` included. Refusing names that start with `_` "
        "is not enough.",
        fix="Map the accepted names to methods in a dict or a set and reject the "
        "rest, or build the name on a constant prefix.",
        bad="def download(self, method_print):\n"
        "    return getattr(self, method_print)()",
        good="REPORTS = {'xlsx': '_report_xlsx', 'pdf': '_report_pdf'}\n\n"
        "def download(self, kind):\n"
        "    return getattr(self, REPORTS[kind])()",
        lang="python",
        notes="High confidence when the name comes from the parameters of a public "
        "method (reachable by RPC or HTTP). Names read from records or other data, and "
        "names in private helpers, are medium and do not affect the score.",
    ),
    "rpc-sudo-without-access-check": RuleDoc(
        detects="Public model methods (no leading underscore) and authenticated "
        "routes (of any controller class, whatever its base is called) that call "
        "`.sudo()` on records or values chosen by their parameters, "
        "with no access check in the method: `check_access*`, `has_access`, a token "
        "or group test, a check-style helper, or a `raise` that refuses the caller. "
        "Public routes (`auth='public'`, also inherited from the overridden route) "
        "and routes whose auth cannot be resolved are left to "
        "`public-controller-sudo-risk`. So the rule is silent on a bare override of "
        "a parent route that is not scanned, or with a computed `auth=CONST`: the "
        "tainted-parameter signal is lost there.",
        why="A public method is reachable with any record ids and arguments. Elevating "
        "with `sudo()` on what the caller picked lets them read or change records "
        "their rights and record rules would refuse (an IDOR).",
        fix="Check the caller's rights on the records before elevating "
        "(`record.check_access('read')` / `has_access`), or drop `sudo()` and let the "
        "record rules apply; elevate only the narrowest recordset.",
        bad="def close(self, rid):\n"
        "    self.env['x.y'].sudo().browse(rid).write({'state': 'closed'})",
        good="def close(self, rid):\n"
        "    rec = self.env['x.y'].browse(rid)\n"
        "    rec.check_access('write')\n"
        "    rec.sudo().write({'state': 'closed'})",
        lang="python",
        notes="High confidence only when a parameter reaches a write, unlink or create "
        "on the elevated recordset and the method does not scope by the caller "
        "(`env.user`, `uid`). Reads, `search` results (already filtered by the caller's "
        "rules) and parameters handed to another method (where a check may live) are "
        "medium or ignored; medium does not affect the score.",
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
        "header line(s)). A comment naming sudo within five lines above, or a "
        "function docstring naming it, also counts; so does a `.sudo()` on an "
        "environment that `self = self.sudo()` already elevated.",
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
        detects="The same XML ID declared more than once in a module, where the "
        "later declaration is not just a patch of the record. It is reported with "
        "high confidence when it gives the id another model, and with medium "
        "confidence when it sets a field the earlier declarations already set.",
        why="Odoo loads a repeated id as an update of the same record. Another "
        "model makes the install fail (`found record of different model`). A "
        "field set twice is allowed, the later value wins and the first is dead "
        "code, so it is usually a copy-paste leftover.",
        fix="Rename one of the IDs, or merge the declarations into one.",
        notes="A later declaration that only sets fields the earlier ones did not "
        "set is the normal way to adjust a record (for example "
        '`<record id="menu_x" model="ir.ui.menu">` adding `group_ids`) and is '
        "not reported. A `<menuitem>` counts as setting `name`, `parent_id` and "
        "`active`, and a `<template>` as setting `name`, `key`, `type` and `arch`, "
        "because Odoo always writes them. A tag the rule cannot read the fields of "
        "(for example `<asset>`) keeps the plain duplicate finding at high.",
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
        "this repository) and the field provably does not exist. `_inherit` and "
        "`_inherits` are read as a string, a list or a tuple. A model with a parent "
        "that is not packaged (the mixins of a stub-known module, a model of an "
        "addon that is not scanned) or not written out (`_inherit = MIXINS`) may have "
        "any field, so nothing is reported. Parents added to a model by an extension "
        "in another module (`_inherit = ['x.base', 'mail.thread']`, no `_name`) "
        "count. Fields and methods of an extension that names no model "
        "(`_inherit = MIXINS`, no `_name`) are never reported missing.",
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
        notes="The `super()` call must be for the same method: `super().write(..)` "
        "inside `create` is not the call chain (a `super()` kept in a variable is "
        "trusted). Not reported: a method whose body raises and never returns "
        "(`def copy(self, default=None): raise UserError(...)`) blocks the "
        "operation on purpose. Medium confidence, not high: the method calls its own "
        "name on records of another model that it maps out of `self` "
        "(`self.mapped('tmpl_id').copy(...)`, `self.line_ids.copy(...)`); calling it "
        "on `self`, on `self.sudo()` / `self.with_context(..)` or on an `env` lookup "
        "stays high. Also medium: `create`/`write` on a model with `_auto = False`, "
        "which has no ORM table for `super()` to write into.",
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
        detects="ORM queries (`search`, `search_count`, `read`, `search_read`, "
        "`search_fetch`, `read_group`) inside `for` or `while` loops and "
        "comprehensions. `browse()` is not flagged: it only wraps ids and does "
        "not query the database.",
        why="One query per iteration scales badly with record count.",
        fix="Move the call out of the loop and batch the results.",
        bad="for line in lines:\n"
        "    partner = self.env['res.partner'].search([('id', '=', line.pid)])",
        good="partners = self.env['res.partner'].search([('id', 'in', lines.mapped('pid'))])\n"
        "by_id = {p.id: p for p in partners}",
        notes="The performance rules skip files inside an addon's `tests/` directory. "
        "Only what runs on every iteration counts: the loop's own iterable "
        "(`for rec in self.env[...].search(...)`) and its `else` clause run once. "
        "Loops over chunks (`split_every(...)`, `range(a, b, step)`), over a literal "
        "tuple/list of constants, and `while` loops paged with `limit=N` (N > 1) are "
        "not reported. The receiver must be a recordset: `self`, an `env[...]` "
        "lookup, a loop variable over records and a local assigned from one "
        "(`recs = self.env['x'].search([])`), but not an attribute that `__init__` "
        "or the class body sets to a plain object (`self.client = Client()`). "
        "Confidence is medium for a query that depends on the loop, which is how Odoo's "
        "own addons are written (hundreds of per-record queries in core 19). It is high "
        "only when the loop cannot change the query: a plain statement of a `for` body "
        "(not under `if` / `try` / `match` / `assert`, not past a short circuit "
        "(`and`, `or`, `x if c else y`, `a < b < query`), not in a comprehension, "
        "`while` or nested function, with no `break` / `continue` / `return` / "
        "`yield` in the body), `self` / `env[...]` receiver, `search` / "
        "`search_count` / `read`, with a receiver and arguments that use no loop "
        "variable or name the loops rebind (by assignment, `except ... as`, a `match` "
        "capture, `import ... as`, `def` or `class`). A query that is a plain "
        "statement of an inner `for` is judged against that inner loop; names the "
        "outer loops rebind count too. The body must also change no record: no "
        "attribute or item store (`rec.state = ...`, `rec['a'] += 1`, "
        "`rec.a, b = ...`, `for rec.state in ...`, `del rec.a`) and no call other than "
        "a plain read (`search*`, `read*`, `browse`, `mapped`, `filtered`, `sorted`, "
        "`with_context`, `sudo`, `get`, `append`, `len` ...); any other call, such as "
        "`create` / `write` / `unlink` / `flush*` / `invalidate*` / `message_post` / "
        "`action_*` or a helper of the class, keeps the query medium. Such a query can "
        "be hoisted out of the loop as is. Blind spot: what a helper does is not "
        "followed, which is why a helper call only ever lowers the confidence; calls "
        "are allowed by name only, so a user-defined `get` / `format` that writes, or "
        "a name that aliases one the loop mutates (`d = domain; d.append(..)`), is not "
        "seen.",
    ),
    "create-in-loop": RuleDoc(
        detects="`create()` called inside a loop or comprehension (its iterable and "
        "`else` clause excluded; chunked and constant-literal loops are skipped; "
        "the receiver rules of `search-in-loop` apply).",
        why="Each call triggers its own INSERT and recomputation round trip.",
        fix="Collect the values and call `create()` once with a list.",
        bad="for vals in vals_list:\n    self.env['my.model'].create(vals)",
        good="self.env['my.model'].create(vals_list)",
        notes="Medium confidence, as in Odoo's own addons: high only when the call is "
        "the only statement of a `for` body and its values and context do not use "
        "the loop (`for n in names: self.env['x'].create({'a': 1})`) and call "
        "nothing that may return another value on the next pass: only "
        "`fields.Datetime.now()` / `today()`, builtins such as `len` / `str`, `_()` "
        "and `with_context` / `sudo`; a sequence, `uuid` / `random`, `next()`, a "
        "helper or another ORM call keeps it medium.",
    ),
    "write-in-loop": RuleDoc(
        detects="`write()` called inside a loop or comprehension (its iterable and "
        "`else` clause excluded; chunked and constant-literal loops are skipped; "
        "the receiver rules of `search-in-loop` apply).",
        why="Each call triggers its own UPDATE and recomputation round trip.",
        fix="Write once on the whole recordset when the values are identical.",
        bad="for rec in records:\n    rec.write({'state': 'done'})",
        good="records.write({'state': 'done'})",
        notes="Medium confidence, as in Odoo's own addons: high only when the call is "
        "the only statement of a `for` body and its values and context do not use "
        "the loop (`for rec in recs: rec.write({'state': 'done'})`) and call "
        "nothing that may return another value on the next pass (as for "
        "`create-in-loop`: `fields.Datetime.now()` is fine, `next_by_code()` is "
        "not). The receiver may be the loop variable.",
    ),
    "n-plus-one-read": RuleDoc(
        detects="Field reads on a record built by `browse(<one id>)` on every "
        "iteration of a `for` loop or comprehension (the id depends on the loop "
        "variable).",
        why="Odoo prefetches: iterating a recordset and reading `line.product_id.name` "
        "costs one query per field for the whole recordset. A singleton browsed per "
        "iteration starts with an empty prefetch, so every read hits the database.",
        fix="Browse all the ids once before the loop and iterate that recordset, or "
        "call `with_prefetch(ids)` on the browsed record.",
        bad="for pid in partner_ids:\n"
        "    name = self.env['res.partner'].browse(pid).country_id.name",
        good="for partner in self.env['res.partner'].browse(partner_ids):\n"
        "    name = partner.country_id.name",
        notes="Looping over a recordset (`for line in order.line_ids:`) is not "
        "reported, and neither are `with_prefetch(...)`, method calls and `id` / `env`. "
        "Low confidence: does not affect the score.",
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
        notes="Missing `version` and `data` are `medium` confidence (Odoo "
        "defaults both, and Odoo core omits them from many manifests), so they "
        "do not lower the score; `name`, `depends` and `license` stay `high`. "
        "Fixable via `odoo-doctor fix`, which adds only the absent high-confidence "
        "keys with a local edit and leaves every other line identical (line endings "
        "are normalised to LF by `fix`). "
        "`installable` is not required (Odoo defaults it to `True`), and `data` "
        "is not required when the manifest declares `assets` or `demo`.",
    ),
    "manifest-data-order-risk": RuleDoc(
        detects="A security file listed in `data` after a view/action file. It is "
        "reported with high confidence only when that security XML creates a group "
        "which an earlier file already needs when it loads (a `<menuitem groups=...>`, "
        "a `<template groups=...>`, or a `groups_id` / `group_ids` / `groups` field "
        'with `ref` or `eval="ref(...)"`).',
        why="Odoo resolves those references while the earlier file loads and raises "
        "if the group does not exist yet, so the module cannot be installed. A group "
        "named only in a view arch (`groups=` on a field or button) just logs a "
        "warning.",
        fix="List the security file that creates the group before the first file that "
        "uses it.",
        bad="'data': [\n"
        "    'views/menus.xml',      # <menuitem groups=\"my_mod.group_x\"/>\n"
        "    'security/groups.xml',  # creates group_x\n"
        "]",
        good="'data': [\n    'security/groups.xml',\n    'views/menus.xml',\n]",
        notes="Every other case is advisory (medium confidence, no score impact, not "
        "auto-fixed): `ir.model.access.csv` and security files that only update a group "
        "which already exists, or that define groups no earlier file needs. Fixable via "
        "`odoo-doctor fix` for the high case: the file is moved in front of the first "
        "file that needs it, with a local edit of the `data` lines (line endings are "
        "normalised to LF by `fix`). The fixer declines when the list is not one "
        "element per line or when it cannot show the new position keeps what the "
        "file depends on loaded before it.",
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
        why="An optional `Many2one` defaults to `set null`: deleting the target "
        "silently empties the field, which orphans a line whose parent is deleted. "
        "Declaring the policy documents the intent.",
        fix="Declare `ondelete` explicitly.",
        bad='partner_id = fields.Many2one("res.partner")',
        good='partner_id = fields.Many2one("res.partner", ondelete="restrict")',
        notes="Required `Many2one` fields are skipped: Odoo already defaults "
        "them to `restrict`. So are related or computed fields that are not stored "
        "(no `store=True`): they have no foreign-key column. Low confidence: the "
        "default is a legitimate choice (about 83% of Odoo 19 community's optional "
        "stored `Many2one` fields rely on it), so this is a hint that does not "
        "affect the score.",
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
        "`mail.channel`, `ir.property`, `stock.valuation.layer`, `stock.quant.package`) "
        "and that the project does not define itself.",
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
    "sql-constraints-unsupported": RuleDoc(
        detects="A model class that sets `_sql_constraints` to a non-empty list, on "
        "Odoo 19 and later. Plain Python mixins, empty lists and test files are ignored.",
        why="Odoo 19 no longer reads `_sql_constraints`: it only logs a warning and "
        "creates none of the constraints, so a UNIQUE or CHECK the model relied on "
        "silently stops being enforced.",
        fix="Declare each constraint as a class attribute with `models.Constraint`, "
        "after checking the database for rows that would violate a UNIQUE one.",
        bad="_sql_constraints = [('name_uniq', 'unique(name)', 'Name must be unique')]",
        good="_name_uniq = models.Constraint('UNIQUE(name)', 'Name must be unique')",
        lang="python",
        notes="Gated to Odoo 19 and later (`min_version`). Verified against the Odoo 19 "
        "ORM source, which logs that the attribute is no longer supported.",
    ),
    "removed-orm-api-usage": RuleDoc(
        detects="Overrides and calls of ORM methods the running Odoo version no longer "
        "defines: `fields_view_get` and `invalidate_cache` (removed in 17), `name_get` "
        "(removed in 18). A call on `self` or `env` is high confidence; a call on an "
        "unrelated object is medium and does not affect the score.",
        why="An override of a removed method is dead code, because nothing calls it any "
        "more, and a call raises `AttributeError`.",
        fix="Use `get_view()` for `fields_view_get`, `invalidate_model()` / "
        "`invalidate_recordset()` for `invalidate_cache`, and "
        "`_compute_display_name` for `name_get`.",
        bad="def name_get(self):\n    return [(r.id, r.name) for r in self]",
        good="@api.depends('name')\n"
        "def _compute_display_name(self):\n"
        "    for r in self:\n"
        "        r.display_name = r.name",
        lang="python",
        notes="Each method is reported only from the Odoo version whose ORM source no "
        "longer defines it. `super().name_get()` inside an override is not reported "
        "twice.",
    ),
    "cron-removed-fields": RuleDoc(
        detects="`ir.cron` records in data or demo files that set `numbercall` or "
        "`doall`, on Odoo 18 and later.",
        why="`ir.cron` no longer has these fields since Odoo 18. A job that used "
        "`numbercall` to run a limited number of times now repeats on every interval.",
        fix="Remove the fields. If the job must stop after some runs, have its method "
        "deactivate the cron.",
        bad='<field name="numbercall">-1</field>\n<field name="doall" eval="False"/>',
        good="<!-- nothing: the interval fields are enough -->",
        lang="xml",
        notes="Only `ir.cron` records are checked; the same field names on other "
        "models are left alone.",
    ),
    "view-attrs-states-removed": RuleDoc(
        detects='Elements with `attrs` or `states` (or an `<attribute name="attrs">` '
        "xpath edit) in the architecture of an `ir.ui.view` record, on Odoo 17 and "
        "later. One finding per view. QWeb is not checked: a view of type `qweb`, a "
        "kanban view's `<templates>` block, an element with a `t-*` directive and an "
        "xpath into either. The `<field>` and `<button>` elements of the rest of a "
        "kanban view are.",
        why='Odoo 17 and later refuse such a view ("Since 17.0, the attrs and states '
        'attributes are no longer used"), so the module cannot be installed or updated.',
        fix="Put the condition in the attribute itself: `invisible`, `readonly` or "
        "`required` take a Python expression on the record's fields.",
        bad="<field name=\"note\" attrs=\"{'invisible': [('state', '=', 'draft')]}\"/>",
        good='<field name="note" invisible="state == \'draft\'"/>',
        lang="xml",
        notes='`states="draft,sent"` on a button becomes '
        "`invisible=\"state not in ('draft', 'sent')\"`.",
    ),
    # ---------------------------------------------------- Real-repo backlog (0.9.2)
    "deprecated-orm-api-usage": RuleDoc(
        detects="Calls of ORM methods the running Odoo version still defines but "
        "deprecates: `read_group`, `toggle_active` and `check_field_access_rights` "
        "(Odoo 19), `check_access_rights`, `check_access_rule`, `_filter_access_rules`, "
        "`_check_recursion` and `_check_m2m_recursion` (Odoo 18). An override of "
        "`read_group` is reported on Odoo 19 as well. A call on `self` or `env` is high "
        "confidence; a call on an unrelated object is medium and does not affect the "
        "score.",
        why="A deprecated method keeps working and logs a warning until a later release "
        "removes it. On Odoo 19 nothing in core calls `read_group` any more: grouped "
        "views use `web_read_group` and `formatted_read_group`, which go through "
        "`_read_group`, so an override of `read_group` is not applied to them.",
        fix="Use `_read_group()` in backend code or `formatted_read_group()` for a "
        "formatted result, `check_access()` / `has_access()` for the access checks, "
        "`_has_cycle()` (it returns True when there is a cycle) for the recursion "
        "checks, and `action_archive()` / `action_unarchive()` for `toggle_active`.",
        bad="groups = self.env['sale.order'].read_group(\n"
        "    domain, ['amount_total:sum'], ['partner_id'])",
        good="groups = self.env['sale.order']._read_group(\n"
        "    domain, ['partner_id'], ['amount_total:sum'])",
        notes="Each method is reported only from the Odoo version whose ORM source "
        "deprecates it. `self._cr`, `self._uid` and `self._context` are deprecated in "
        "Odoo 19 too but are not reported: core still uses them and they would bury "
        "every other finding. `super().read_group()` inside an override is not reported "
        "twice.",
    ),
    "tls-verification-disabled": RuleDoc(
        detects="Code that turns off TLS verification: `verify=False` on a call, "
        "`session.verify = False`, `ctx.check_hostname = False`, "
        "`ctx.verify_mode = ssl.CERT_NONE` and `ssl._create_unverified_context()`.",
        why="Without certificate verification anyone on the network path can pose as the "
        "server and read or change the traffic, including credentials and API tokens.",
        fix="Remove the override. For a private or self-signed certificate, point "
        "`verify` at the CA bundle, or install the CA on the host.",
        bad="requests.get(url, verify=False)",
        good="requests.get(url, verify='/etc/ssl/certs/company-ca.pem', timeout=10)",
        notes="`verify=False` in a file that imports no network library is reported at "
        "medium confidence, because the keyword may belong to an unrelated function. "
        "Scripts under `tests/` and `migrations/` are skipped.",
    ),
    "http-request-without-timeout": RuleDoc(
        detects="`requests.get/post/put/patch/delete/head/options/request()`, the same "
        "calls on a `requests.Session`, and `urllib.request.urlopen()` without a "
        "`timeout`.",
        why="Neither library gives up on its own. One unresponsive server holds an Odoo "
        "worker until the server-wide time limit kills it, and with it every request "
        "that worker was serving.",
        fix="Pass an explicit `timeout` in seconds, or a `(connect, read)` pair.",
        bad="response = requests.post(url, json=payload)",
        good="response = requests.post(url, json=payload, timeout=10)",
        notes="A call that passes `**options` is not reported, because `timeout` may be "
        "in it. Scripts under `tests/` and `migrations/` are skipped.",
    ),
    "csrf-disabled-authenticated-route": RuleDoc(
        detects="Routes declared with `csrf=False` that run as the logged-in user "
        "(`auth='user'`, the default), have `type='http'` and accept POST, PUT, PATCH or "
        "DELETE (or leave `methods` unset, at medium confidence).",
        why="A browser sends the session cookie on a cross-site request, so any page the "
        "user visits can trigger the route. Odoo only checks the CSRF token on these "
        "routes.",
        fix="Remove `csrf=False` and send the token with the request "
        "(`request.csrf_token()`). A trusted third party that calls the route should "
        "use `auth='public'` and a verified signature or secret instead of the session.",
        bad="@http.route('/my/save', type='http', auth='user', methods=['POST'], csrf=False)",
        good="@http.route('/my/save', type='http', auth='user', methods=['POST'])",
        notes="Webhooks (`auth='public'` / `'none'`), JSON routes and GET-only routes are "
        "not reported: they carry no session identity of their own, or Odoo never checks "
        "the token for them.",
    ),
    "manual-cr-commit": RuleDoc(
        detects="`cr.commit()` on the transaction Odoo opened for the request: "
        "`self.env.cr`, `self._cr`, `request.cr`. A commit on another name (`env.cr`, "
        "`cr`) is medium confidence and does not affect the score.",
        why="A commit ends the request's transaction. Work done before it can no longer "
        "be rolled back, so a later error leaves the database half updated.",
        fix="Remove the commit and let Odoo commit when the request succeeds. Run batch "
        "work from a cron or a queue job, or in its own cursor "
        "(`with self.pool.cursor() as cr:`).",
        bad="def action_import(self):\n"
        "    for row in rows:\n"
        "        self.create(row)\n"
        "        self.env.cr.commit()",
        good="def action_import(self):\n    self.create(rows)",
        notes="Not reported: a cursor or environment the code opened itself "
        "(`registry.cursor()`, `self.pool.cursor()`, `api.Environment(...)`) in the "
        "function that commits it or an enclosing one (or at module level), not "
        "elsewhere in the file and not under a parameter of the same name, cron "
        "methods (a function with `cron` in its name), install hooks (`init`, "
        "`_auto_init`, `post_init_hook`...), a commit under an `if` that tests "
        "`test_enable` / `testing`, and a line marked "
        "`# pylint: disable=invalid-commit`. Scripts under `tests/` and `migrations/` "
        "are skipped.",
    ),
    # ------------------------------------------ Odoo 18 / 19 migration (0.9.3)
    "view-tree-removed": RuleDoc(
        detects="The `tree` view type on Odoo 18 and later: a `<tree>` element in a view "
        'architecture (also nested in an x2many field), `<field name="type">tree`, a '
        "`tree` step in an XPath, `tree` in the `view_mode` of an action or an "
        "`ir.actions.act_window.view`, and Python action dicts with `'view_mode': "
        "'tree,form'` or a `(False, 'tree')` pair in `'views'`.",
        why="Odoo 18 renamed the tree view type to `list` and kept no alias, so the view "
        "is rejected on install or update and the action cannot open.",
        fix="Rename: `<tree>` to `<list>`, `tree,form` to `list,form`, and the XPath "
        "step `tree` to `list`.",
        bad='<record id="view_x_tree" model="ir.ui.view">\n'
        '    <field name="model">x.model</field>\n'
        '    <field name="arch" type="xml">\n'
        '        <tree><field name="name"/></tree>\n'
        "    </field>\n"
        "</record>",
        good='<record id="view_x_list" model="ir.ui.view">\n'
        '    <field name="model">x.model</field>\n'
        '    <field name="arch" type="xml">\n'
        '        <list><field name="name"/></list>\n'
        "    </field>\n"
        "</record>",
        lang="xml",
        notes="Reported once per view or action record. A Python dict that does not look "
        "like an action (no `res_model`, no `type`) is medium confidence. Only files the "
        "manifest loads are read, and QWeb templates are skipped. "
        "`odoo-doctor fix --upgrade-to 19.0` renames every form of a high-confidence finding.",
    ),
    "removed-core-field-usage": RuleDoc(
        detects="Fields that core models no longer have, set by a data record or shown by "
        "a view: `groups_id` of `res.users`, `ir.ui.view`, `ir.ui.menu` and the actions "
        "(renamed `group_ids`, Odoo 19), `category_id` and `users` of `res.groups`, "
        "`mobile` of `res.partner` and `crm.lead`, `deprecated` of `account.account`, "
        "`user_id` of `ir.filters` (Odoo 19), and `detailed_type` of the product models "
        "(Odoo 18). In Python, the names `groups_id` and `detailed_type` as attribute, "
        "dict key, domain term or `selection_add` target.",
        why="A record that sets a missing field fails to load (`Invalid field ... in "
        "...`), and the module cannot be installed or updated.",
        fix="Use the replacement named in the finding, for example `group_ids`, "
        "`user_ids`, `privilege_id` (with a `res.groups.privilege` record), `phone`, "
        "`active`, or `type` plus `is_storable`.",
        bad='<record id="group_x" model="res.groups">\n'
        '    <field name="name">X</field>\n'
        '    <field name="users" eval="[(4, ref(\'base.user_admin\'))]"/>\n'
        "</record>",
        good='<record id="group_x" model="res.groups">\n'
        '    <field name="name">X</field>\n'
        '    <field name="user_ids" eval="[(4, ref(\'base.user_admin\'))]"/>\n'
        "</record>",
        lang="xml",
        notes="The table lists only fields that the ORM source of that release no longer "
        "defines. In XML the model comes from the record, so the finding is high "
        "confidence. The Python names are unique to the removed fields, so a hit is "
        "medium confidence (no score effect); a model the module creates itself "
        "(`_name`), `'groups_id' in rec._fields` and `hasattr()` probes are skipped. "
        "`fix --upgrade-to` renames only `groups_id` to `group_ids` and `res.groups.users` to "
        "`user_ids` (high confidence); the other entries change meaning and need a person.",
    ),
    "search-view-group-attributes": RuleDoc(
        detects="`string` or `expand` on a `<group>` inside a search view (Odoo 19).",
        why="The Odoo 19 search view schema no longer allows those attributes on "
        "`<group>`, so the view is rejected on install or update. In Odoo 18 they are "
        "still valid.",
        fix='Use a bare `<group>` around the "Group By" filters.',
        bad='<group expand="0" string="Group By">\n'
        '    <filter name="by_user" string="User" context="{\'group_by\': \'user_id\'}"/>\n'
        "</group>",
        good="<group>\n"
        '    <filter name="by_user" string="User" context="{\'group_by\': \'user_id\'}"/>\n'
        "</group>",
        lang="xml",
        notes="An inherited view is checked only for a `<group>` that holds `<filter>` "
        "children, which only a search view has. `<group string>` in a form view is "
        "valid and not reported. `fix --upgrade-to` removes both attributes.",
    ),
    "act-window-target-inline": RuleDoc(
        detects="An `ir.actions.act_window` record or Python action dict with "
        "`target` set to `inline` (Odoo 19).",
        why="Odoo 19 removed `inline` from the `target` selection, so the record is "
        "rejected on install or update.",
        fix="Use `current` (the settings actions of Odoo 19 do), or `new` for a dialog.",
        bad='<field name="target">inline</field>',
        good='<field name="target">current</field>',
        lang="xml",
    ),
    "chatter-div-removed": RuleDoc(
        detects='A `<div class="oe_chatter">` in a view architecture (Odoo 18 and later).',
        why="The form compiler of Odoo 17 selected `div.oe_chatter`. Odoo 18 and 19 "
        "select only the `<chatter/>` tag, so the div is a plain block and the form "
        "shows no followers, messages or activities. The view still loads, so nothing "
        "fails at install time.",
        fix='Replace the whole `<div class="oe_chatter">...</div>` block with '
        "`<chatter/>`.",
        bad='<div class="oe_chatter">\n'
        '    <field name="message_follower_ids"/>\n'
        '    <field name="message_ids"/>\n'
        "</div>",
        good="<chatter/>",
        lang="xml",
        notes="Checked against the form compilers of Odoo 18.0 and 19.0; no Odoo 18/19 "
        "code reads `oe_chatter` any more. A div that only has the class, the standard chatter "
        "fields and a parent that is the view root or an `xpath` is high confidence and "
        "`fix --upgrade-to` replaces it by `<chatter/>`; any other div is medium confidence "
        "and needs a person.",
    ),
    "kanban-legacy-templates": RuleDoc(
        detects='The `t-name="kanban-box"` and `t-name="kanban-menu"` templates of a '
        "kanban view, and an XPath that targets them (Odoo 19).",
        why="Odoo 18 renamed them `card` and `menu` and still read the old names with a "
        "deprecation note. Odoo 19 reads only the new names: the view fails with "
        "\"Missing 'card' template\", and an XPath on the old name finds no anchor in "
        "the core kanban view.",
        fix="Rename `kanban-box` to `card` and `kanban-menu` to `menu`, port the card "
        "markup to the Odoo 18 layout (`main` / `aside` / `footer`) and re-anchor "
        "inherited XPaths.",
        bad='<t t-name="kanban-box">...</t>',
        good='<t t-name="card">...</t>',
        lang="xml",
    ),
}
