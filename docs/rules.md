<!-- GENERATED FILE: do not edit by hand. Source: src/odoo_doctor/rules/rule_docs.py. Regenerate with `odoo-doctor rules docs --out docs/rules.md`. -->

# Built-in Rules

Odoo Doctor ships 37 native rules. Each rule has a **tier** (P0 critical, P1 serious, P2 moderate, P3 advisory), a **category** and a **confidence**; only high-confidence findings affect the score.

| Rule | Tier | Category | Severity | Confidence | Fixable |
|------|------|----------|----------|------------|---------|
| [eval-usage](#eval-usage) | P0 | Security | error | high |  |
| [missing-access-csv](#missing-access-csv) | P0 | Security | error | high |  |
| [raw-sql-string-interpolation](#raw-sql-string-interpolation) | P0 | Security | error | high |  |
| [missing-multicompany-rule](#missing-multicompany-rule) | P1 | Security | warning | medium |  |
| [public-controller-sudo-risk](#public-controller-sudo-risk) | P1 | Security | error | high |  |
| [record-rule-without-domain](#record-rule-without-domain) | P1 | Security | warning | medium |  |
| [sudo-without-comment](#sudo-without-comment) | P1 | Security | warning | medium |  |
| [unsafe-template-render](#unsafe-template-render) | P1 | Security | warning | medium |  |
| [button-method-not-found](#button-method-not-found) | P1 | Correctness | error | high |  |
| [duplicate-xml-id](#duplicate-xml-id) | P1 | Correctness | error | high |  |
| [missing-xml-ref](#missing-xml-ref) | P1 | Correctness | error | high |  |
| [monetary-missing-currency-field](#monetary-missing-currency-field) | P1 | Correctness | error | high |  |
| [override-missing-super](#override-missing-super) | P1 | Correctness | error | high |  |
| [unknown-model-in-access-csv](#unknown-model-in-access-csv) | P1 | Correctness | error | high |  |
| [view-field-not-in-model](#view-field-not-in-model) | P1 | Correctness | error | high |  |
| [compute-missing-depends](#compute-missing-depends) | P2 | Correctness | warning | high |  |
| [hardcoded-company-or-currency](#hardcoded-company-or-currency) | P2 | Correctness | warning | medium |  |
| [create-in-loop](#create-in-loop) | P1 | Performance | error | high |  |
| [n-plus-one-read](#n-plus-one-read) | P1 | Performance | warning | low |  |
| [search-in-loop](#search-in-loop) | P1 | Performance | error | high |  |
| [write-in-loop](#write-in-loop) | P1 | Performance | error | high |  |
| [expensive-nonstored-compute](#expensive-nonstored-compute) | P2 | Performance | warning | medium |  |
| [unbounded-search](#unbounded-search) | P2 | Performance | warning | high |  |
| [missing-ondelete](#missing-ondelete) | P1 | Data Integrity | warning | high |  |
| [data-noupdate-risk](#data-noupdate-risk) | P2 | Data Integrity | warning | high |  |
| [deprecated-api-usage](#deprecated-api-usage) | P1 | Upgrade Safety | warning | high |  |
| [removed-model-still-referenced](#removed-model-still-referenced) | P1 | Upgrade Safety | error | medium |  |
| [manifest-missing-dependency](#manifest-missing-dependency) | P1 | Module Hygiene | error | high |  |
| [manifest-data-order-risk](#manifest-data-order-risk) | P2 | Module Hygiene | error | high | Yes |
| [manifest-license-incompatible](#manifest-license-incompatible) | P2 | Module Hygiene | warning | high |  |
| [manifest-missing-required-fields](#manifest-missing-required-fields) | P2 | Module Hygiene | warning | high | Yes |
| [missing-external-dependency](#missing-external-dependency) | P2 | Module Hygiene | warning | high |  |
| [field-no-string-on-required](#field-no-string-on-required) | P2 | Maintainability | info | medium |  |
| [missing-translation](#missing-translation) | P2 | Maintainability | info | medium |  |
| [orphan-view](#orphan-view) | P2 | Maintainability | warning | medium |  |
| [vendored-python-code](#vendored-python-code) | P3 | Maintainability | info | medium |  |
| [asset-bundle-missing](#asset-bundle-missing) | P2 | Frontend | error | high |  |

## Security

### eval-usage

**Tier**: P0 (critical) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Calls to the builtins `eval()` / `exec()` on non-literal input.

**Why**: Evaluating dynamic strings allows arbitrary code execution.

**Fix**: Use `odoo.tools.safe_eval` for domains/expressions, or refactor to explicit logic.

**Note**: An argument provably built from constants (a literal, or a variable bound only to constants) is not reported; anything else, including a parameter or a string with interpolated values, is.

Bad:

```python
result = eval(expression)
```

Good:

```python
from odoo.tools.safe_eval import safe_eval
result = safe_eval(expression, {'uid': self.env.uid})
```

### missing-access-csv

**Tier**: P0 (critical) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Models defined in the module with no row in `security/ir.model.access.csv` (or no CSV file at all).

**Why**: A model without access rules is unreachable for non-admin users and is flagged by Odoo at load time.

**Fix**: Create `security/ir.model.access.csv` and add an ACL row per model.

Bad:

```csv
# security/ir.model.access.csv is missing a row for my.model
```

Good:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_my_model_user,my.model user,model_my_model,base.group_user,1,1,1,0
```

### raw-sql-string-interpolation

**Tier**: P0 (critical) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `cr.execute()` calls that build the query with f-strings, `%`-formatting, `.format()` or concatenation.

**Why**: Interpolating values into SQL leads to SQL injection.

**Fix**: Pass values as query parameters.

**Note**: When the dynamic part is not user data (for example a WHERE fragment whose values are bound through parameters), assert it with pylint-odoo's marker `# pylint: disable=sql-injection`, which this rule honours: a trailing comment covers its line, a comment on its own line covers the rest of the enclosing function. `# odoo-doctor: disable=raw-sql-string-interpolation` also works. The rule follows values through local variables, lists (`append`, `extend`, `+=`), `if`/`try`/loop branches and module constants: SQL built only from constants, `int()` casts, `self._table`, `SQL(...)` or `','.join(['%s'] * n)` placeholder lists is not reported, while a fragment that reaches the query through a list or a branch is.

Bad:

```python
self.env.cr.execute(f"SELECT * FROM res_partner WHERE name = '{name}'")
```

Good:

```python
self.env.cr.execute("SELECT * FROM res_partner WHERE name = %s", (name,))
```

### missing-multicompany-rule

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: Models defined in the module with a `company_id` Many2one to `res.company` that no `ir.rule` in the scanned modules protects.

**Why**: Without a company record rule, users of one company can read and edit another company's records in a multi-company database.

**Fix**: Add an `ir.rule` restricting records to `company_ids`.

**Note**: Medium confidence (does not affect the score): the rule may live in an addon that was not scanned. Transient and abstract models are skipped.

Bad:

```xml
company_id = fields.Many2one("res.company", required=True)
# ... and no <record model="ir.rule"> for this model
```

Good:

```xml
<record id="my_model_comp_rule" model="ir.rule">
    <field name="name">My model multi-company</field>
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">[('company_id', 'in', company_ids)]</field>
</record>
```

### public-controller-sudo-risk

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `@http.route` handlers with `auth='public'` or `auth='none'` that call `.sudo()`.

**Why**: Public routes combined with `sudo()` bypass access rights and can lead to privilege escalation or data leaks.

**Fix**: Require authentication, or restrict what the sudo call can reach and validate the input.

Bad:

```python
@http.route('/api/data', auth='public')
def get_data(self):
    return request.env['private.model'].sudo().search([])
```

Good:

```python
@http.route('/api/data', auth='user')
def get_data(self):
    return request.env['private.model'].search([])
```

### record-rule-without-domain

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: `ir.rule` records without a restricting `domain_force`.

**Why**: A rule with an empty domain either grants or denies everything and rarely expresses the intended restriction.

**Fix**: Add a `domain_force` that limits the records the rule applies to.

**Note**: Medium confidence: does not affect the score.

Bad:

```xml
<record id="my_rule" model="ir.rule">
    <field name="model_id" ref="model_my_model"/>
</record>
```

Good:

```xml
<record id="my_rule" model="ir.rule">
    <field name="model_id" ref="model_my_model"/>
    <field name="domain_force">[('user_id', '=', user.id)]</field>
</record>
```

### sudo-without-comment

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: `.sudo()` calls with no justifying comment on the same line or directly above.

**Why**: Every privilege elevation should be reviewable; an undocumented `sudo()` is hard to audit.

**Fix**: Add a short comment explaining why elevated privileges are needed.

**Note**: Medium confidence: does not affect the score.

Bad:

```python
partner = self.env['res.partner'].sudo().browse(pid)
```

Good:

```python
# sudo: portal users cannot read partners but need the display name
partner = self.env['res.partner'].sudo().browse(pid)
```

### unsafe-template-render

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: QWeb `t-raw` output, which renders a value without HTML-escaping. The safe `t-raw="0"` idiom (the body passed to a `t-call`) is ignored.

**Why**: Unescaped output of user-controlled data is a stored or reflected XSS risk in reports, emails and website pages.

**Fix**: Use `t-esc` (or `t-out` on Odoo 17+) so the value is escaped, or only render raw markup when the value is a trusted `Markup` object.

**Note**: Medium confidence: the value may already be sanitized, so it does not count toward the score by default.

Bad:

```xml
<div t-raw="doc.user_comment"/>
```

Good:

```xml
<div t-esc="doc.user_comment"/>
```

## Correctness

### button-method-not-found

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Buttons with `type="object"` calling a method that does not exist on the model.

**Why**: Clicking the button raises an error at runtime.

**Fix**: Add the method to the model or fix the button's `name`.

### duplicate-xml-id

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: The same XML ID declared more than once in a module.

**Why**: The later record silently overwrites the earlier one.

**Fix**: Remove or rename the duplicate.

### missing-xml-ref

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `ref="..."`, `eval="ref(...)"` and `inherit_id` references that cannot be resolved.

**Why**: Unresolved references abort the module install/update.

**Fix**: Verify the referenced XML ID exists and that the providing module is listed in `depends`.

### monetary-missing-currency-field

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `fields.Monetary` fields whose currency field (`currency_id`, or the one named by `currency_field=`) provably does not exist on the model, including its `_inherit`/`_inherits` ancestors and extensions in other scanned modules.

**Why**: A Monetary field needs a currency to be stored, rounded and displayed; without it Odoo raises at runtime or shows no currency.

**Fix**: Add the currency field, or point `currency_field=` at an existing Many2one to `res.currency`.

**Note**: Only reported when absence is provable; models that extend an upstream model you do not define here are skipped.

Bad:

```python
amount = fields.Monetary(string="Amount")
```

Good:

```python
currency_id = fields.Many2one("res.currency")
amount = fields.Monetary(string="Amount")
```

### override-missing-super

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Overrides of ORM methods (`create`, `write`, `unlink`, ...) that never call `super()`.

**Why**: Skipping `super()` breaks the method chain and bypasses parent logic, validation and hooks.

**Fix**: Call and return the parent implementation.

Bad:

```python
def create(self, vals):
    return self.env['res.partner'].create(vals)
```

Good:

```python
def create(self, vals):
    record = super().create(vals)
    return record
```

### unknown-model-in-access-csv

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Rows in `ir.model.access.csv` whose model does not exist.

**Why**: The CSV load fails (or silently grants nothing) when the model cannot be resolved.

**Fix**: Correct the `model_id:id` to match the model's `_name`.

Bad:

```csv
access_x,x,model_my_modle,base.group_user,1,0,0,0
```

Good:

```csv
access_x,x,model_my_model,base.group_user,1,0,0,0
```

### view-field-not-in-model

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Views that reference fields not found on the model.

**Why**: Odoo rejects the view at load time.

**Fix**: Add the field to the model or remove it from the view.

**Note**: Fires with high confidence only when the model is known (stubs or this repository) and the field provably does not exist.

### compute-missing-depends

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Compute methods that read fields not declared in `@api.depends`.

**Why**: Missing dependencies leave computed values stale.

**Fix**: List every field the computation reads.

Bad:

```python
@api.depends('quantity')
def _compute_total(self):
    for rec in self:
        rec.total = rec.quantity * rec.unit_price
```

Good:

```python
@api.depends('quantity', 'unit_price')
def _compute_total(self):
    for rec in self:
        rec.total = rec.quantity * rec.unit_price
```

### hardcoded-company-or-currency

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: `env.ref('base.main_company')` and `env.ref('base.USD')`-style references to a specific currency in business code.

**Why**: In a multi-company or multi-currency database these pick the wrong record.

**Fix**: Use `self.env.company`, `self.env.company.currency_id`, or the document's own `company_id` / `currency_id`.

**Note**: Medium confidence (does not affect the score). Install hooks (`*_hook` functions, `hooks.py`), `migrations/` and `tests/` are skipped.

Bad:

```python
company = self.env.ref("base.main_company")
```

Good:

```python
company = self.env.company
```

## Performance

### create-in-loop

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `create()` called inside a loop.

**Why**: Each call triggers its own INSERT and recomputation round trip.

**Fix**: Collect the values and call `create()` once with a list.

Bad:

```python
for vals in vals_list:
    self.env['my.model'].create(vals)
```

Good:

```python
self.env['my.model'].create(vals_list)
```

### n-plus-one-read

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: low · **Min Odoo version**: 14.0

**Detects**: Chained relational attribute access (`rec.partner_id.name`) on the loop variable inside a loop.

**Why**: Can trigger one query per record when the prefetch cache is cold.

**Fix**: Prefetch related records before looping, or read the needed fields in one batch.

**Note**: Low confidence: does not affect the score.

### search-in-loop

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: ORM queries (`search`, `search_count`, `read`) inside `for` or `while` loops. `browse()` is not flagged: it only wraps ids and does not query the database.

**Why**: One query per iteration scales badly with record count.

**Fix**: Move the call out of the loop and batch the results.

**Note**: The performance rules skip files inside an addon's `tests/` directory.

Bad:

```python
for line in lines:
    partner = self.env['res.partner'].search([('id', '=', line.pid)])
```

Good:

```python
partners = self.env['res.partner'].search([('id', 'in', lines.mapped('pid'))])
by_id = {p.id: p for p in partners}
```

### write-in-loop

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `write()` called inside a loop.

**Why**: Each call triggers its own UPDATE and recomputation round trip.

**Fix**: Write once on the whole recordset when the values are identical.

Bad:

```python
for rec in records:
    rec.write({'state': 'done'})
```

Good:

```python
records.write({'state': 'done'})
```

### expensive-nonstored-compute

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: Computed fields that are not stored (`store=True` missing) whose compute method runs `search`, `search_count`, `search_read` or `read_group` on an ORM object.

**Why**: A non-stored field is recomputed on every read, including list views, exports and `search_read`, so each display pays for the query.

**Fix**: Store the field with a complete `@api.depends`, or move the aggregate into a stored field or a `read_group` at the call site.

**Note**: Medium confidence: does not affect the score. Complements `search-in-loop`, which flags the query-per-record pattern itself.

Bad:

```python
total_orders = fields.Integer(compute='_compute_total_orders')

def _compute_total_orders(self):
    for rec in self:
        rec.total_orders = self.env['sale.order'].search_count(
            [('partner_id', '=', rec.id)]
        )
```

Good:

```python
total_orders = fields.Integer(
    compute='_compute_total_orders', store=True
)

@api.depends('order_ids')
def _compute_total_orders(self):
    for rec in self:
        rec.total_orders = len(rec.order_ids)
```

### unbounded-search

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `search()` / `read()` calls with no `limit` in risky contexts.

**Why**: Unbounded searches can load a whole table into memory.

**Fix**: Add a `limit` or restrict the domain.

Bad:

```python
records = self.env['res.partner'].search([('country_id', '=', cid)])
```

Good:

```python
records = self.env['res.partner'].search(
    [('country_id', '=', cid)], limit=100
)
```

## Data Integrity

### missing-ondelete

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `Many2one` fields on non-transient, non-abstract models without an explicit `ondelete`.

**Why**: The implicit `set null` policy is rarely a conscious choice; declaring it documents the intended behavior.

**Fix**: Declare `ondelete` explicitly.

**Note**: Required `Many2one` fields are skipped: Odoo already defaults them to `restrict`.

Bad:

```python
partner_id = fields.Many2one("res.partner")
```

Good:

```python
partner_id = fields.Many2one("res.partner", ondelete="restrict")
```

### data-noupdate-risk

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Records of critical models (`ir.rule`, `ir.config_parameter`, `ir.cron`) in XML data files outside `noupdate="1"`.

**Why**: Records without `noupdate` are overwritten on every module update, discarding user changes.

**Fix**: Wrap the records in `<data noupdate="1">`.

**Note**: `ir.rule` records are reported with medium confidence (not scored): Odoo core wraps them in `noupdate` while many addons keep them updatable so rule fixes ship with the module. `ir.config_parameter` and `ir.cron` stay high confidence.

Bad:

```xml
<record id="my_rule" model="ir.rule">...</record>
```

Good:

```xml
<data noupdate="1">
    <record id="my_rule" model="ir.rule">...</record>
</data>
```

## Upgrade Safety

### deprecated-api-usage

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Old-API patterns: `from openerp` imports, `_columns`, `osv.osv` and `self.pool`.

**Why**: They belong to Odoo 7-9 and are removed in modern versions.

**Fix**: Migrate to the new API.

Bad:

```python
from openerp import models
class MyModel(osv.osv): ...
self.pool.get('res.partner')
```

Good:

```python
from odoo import models
class MyModel(models.Model): ...
self.env['res.partner']
```

### removed-model-still-referenced

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: `_inherit` targets that cannot be resolved in the project or the Odoo stubs for the target version.

**Why**: Models are removed or renamed between versions; inheriting a missing model breaks the import.

**Fix**: Verify the model exists in the target version and update `_inherit`.

**Note**: Medium confidence: does not affect the score.

## Module Hygiene

### manifest-missing-dependency

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Modules required by Python `_inherit` models, XML external ID references (including `eval="ref(...)"`) and inherited views that are not listed in `depends`.

**Why**: The module installs only when another module happens to be installed first.

**Fix**: Add the providing module to `depends`.

**Note**: A module reachable through `depends` transitively counts as available. When part of that chain is a module whose manifest is unknown (set `odoo_source_path` to index core addons), the finding is reported with medium confidence and does not affect the score.

### manifest-data-order-risk

**Tier**: P2 (moderate) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0 · **Fixable**: yes

**Detects**: `data` files in the manifest listed in an unsafe load order (for example a security file after views/actions).

**Why**: Wrong order causes missing references or access rights at load time.

**Fix**: Order data files by dependency: security first, then views, then data.

**Note**: Fixable via `odoo-doctor fix`.

Bad:

```python
'data': [
    'views/my_views.xml',
    'security/ir.model.access.csv',
]
```

Good:

```python
'data': [
    'security/ir.model.access.csv',
    'views/my_views.xml',
]
```

### manifest-license-incompatible

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: An addon whose manifest `license` conflicts with the license of a scanned dependency: GPL-2 (version 2 only) combined with a GPL-3 family license in either direction (high confidence), or a proprietary module (OPL-1, OEEL-1) depending on GPL/AGPL code (medium confidence).

**Why**: The combination cannot be distributed under both licenses.

**Fix**: Relicense one module or drop the dependency; check with the licensing owner.

**Note**: Only dependencies whose manifest was scanned are compared.

### manifest-missing-required-fields

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0 · **Fixable**: yes

**Detects**: `__manifest__.py` missing one of `name`, `version`, `depends`, `data`, `license`.

**Fix**: Add the missing key. Run `odoo-doctor fix` to apply it automatically.

**Note**: Fixable via `odoo-doctor fix`. `installable` is not required (Odoo defaults it to `True`), and `data` is not required when the manifest declares `assets` or `demo`.

### missing-external-dependency

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Third-party Python packages imported by the addon but not listed in `external_dependencies['python']` (of the addon or of a module it depends on).

**Why**: Installing without the package fails at import time instead of with a clear dependency error.

**Fix**: Add `"external_dependencies": {"python": ["pkg"]}` to the manifest, or guard an optional import with `try/except ImportError`.

**Note**: Skipped: stdlib, packages Odoo itself installs, guarded and `TYPE_CHECKING` imports, `tests/` and `migrations/`. Medium confidence when the dependency chain includes a module whose manifest was not scanned.

## Maintainability

### field-no-string-on-required

**Tier**: P2 (moderate) · **Severity**: info · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: `required=True` fields without an explicit `string`.

**Why**: Auto-generated labels produce unclear validation errors and are hard to translate.

**Fix**: Add `string="..."`.

**Note**: Medium confidence: does not affect the score.

Bad:

```python
name = fields.Char(required=True)
```

Good:

```python
name = fields.Char(string="Name", required=True)
```

### missing-translation

**Tier**: P2 (moderate) · **Severity**: info · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: `UserError` / `ValidationError` messages not wrapped in `_()`.

**Why**: Untranslated messages stay in English for every user.

**Fix**: Wrap the message with `_("...")`.

**Note**: Medium confidence: does not affect the score.

Bad:

```python
raise UserError("Amount must be positive")
```

Good:

```python
raise UserError(_("Amount must be positive"))
```

### orphan-view

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: Views that no action, menu or inheriting view references.

**Fix**: Reference the view, inherit it, or remove it if unused.

**Note**: Medium confidence: the reference may live in a module that was not scanned. Does not affect the score.

### vendored-python-code

**Tier**: P3 (advisory) · **Severity**: info · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: Third-party Python code copied into an addon: `vendor/`, `lib/` and similar directories containing `.py` files, `*.dist-info` / `*.egg-info`, or a well-known package (for example `six/`) at the top level.

**Why**: Copied code misses security fixes and can clash with the installed version.

**Fix**: Declare the package in `external_dependencies['python']` instead.

**Note**: Medium confidence (does not affect the score). JavaScript libraries under `static/` are normal in Odoo and are not reported.

## Frontend

### asset-bundle-missing

**Tier**: P2 (moderate) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 15.0

**Detects**: Files listed in the manifest `assets` dict that do not exist on disk.

**Why**: Missing assets cause JavaScript/CSS loading errors in the web client.

**Fix**: Create the file or remove the manifest entry.

Bad:

```python
'assets': {
    'web.assets_backend': ['my_module/static/src/js/missing.js'],
}
```

Good:

```python
# create static/src/js/missing.js, or drop the entry above
```
