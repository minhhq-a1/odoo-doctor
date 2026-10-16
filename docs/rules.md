<!-- GENERATED FILE: do not edit by hand. Source: src/odoo_doctor/rules/rule_docs.py. Regenerate with `odoo-doctor rules docs --out docs/rules.md`. -->

# Built-in Rules

Odoo Doctor ships 55 native rules. Each rule has a **tier** (P0 critical, P1 serious, P2 moderate, P3 advisory), a **category** and a **confidence**; only high-confidence findings affect the score.

| Rule | Tier | Category | Severity | Confidence | Fixable |
|------|------|----------|----------|------------|---------|
| [eval-usage](#eval-usage) | P0 | Security | error | high |  |
| [missing-access-csv](#missing-access-csv) | P0 | Security | error | high |  |
| [raw-sql-string-interpolation](#raw-sql-string-interpolation) | P0 | Security | error | high |  |
| [access-write-without-group](#access-write-without-group) | P1 | Security | error | high |  |
| [csrf-disabled-authenticated-route](#csrf-disabled-authenticated-route) | P1 | Security | warning | high |  |
| [dynamic-method-dispatch](#dynamic-method-dispatch) | P1 | Security | error | high |  |
| [missing-multicompany-rule](#missing-multicompany-rule) | P1 | Security | warning | medium |  |
| [public-controller-sudo-risk](#public-controller-sudo-risk) | P1 | Security | error | high |  |
| [record-rule-without-domain](#record-rule-without-domain) | P1 | Security | warning | medium |  |
| [rpc-sudo-without-access-check](#rpc-sudo-without-access-check) | P1 | Security | error | high |  |
| [sudo-without-comment](#sudo-without-comment) | P1 | Security | warning | low |  |
| [tls-verification-disabled](#tls-verification-disabled) | P1 | Security | warning | high |  |
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
| [http-request-without-timeout](#http-request-without-timeout) | P2 | Performance | warning | high |  |
| [unbounded-search](#unbounded-search) | P2 | Performance | warning | high |  |
| [manual-cr-commit](#manual-cr-commit) | P1 | Data Integrity | warning | high |  |
| [missing-ondelete](#missing-ondelete) | P1 | Data Integrity | warning | low |  |
| [data-noupdate-risk](#data-noupdate-risk) | P2 | Data Integrity | warning | high |  |
| [act-window-target-inline](#act-window-target-inline) | P1 | Upgrade Safety | error | high |  |
| [chatter-div-removed](#chatter-div-removed) | P1 | Upgrade Safety | warning | high |  |
| [cron-removed-fields](#cron-removed-fields) | P1 | Upgrade Safety | error | high |  |
| [deprecated-api-usage](#deprecated-api-usage) | P1 | Upgrade Safety | warning | high |  |
| [kanban-legacy-templates](#kanban-legacy-templates) | P1 | Upgrade Safety | error | high |  |
| [removed-core-field-usage](#removed-core-field-usage) | P1 | Upgrade Safety | error | high |  |
| [removed-model-still-referenced](#removed-model-still-referenced) | P1 | Upgrade Safety | error | medium |  |
| [removed-orm-api-usage](#removed-orm-api-usage) | P1 | Upgrade Safety | error | high |  |
| [search-view-group-attributes](#search-view-group-attributes) | P1 | Upgrade Safety | error | high |  |
| [sql-constraints-unsupported](#sql-constraints-unsupported) | P1 | Upgrade Safety | error | high |  |
| [view-attrs-states-removed](#view-attrs-states-removed) | P1 | Upgrade Safety | error | high |  |
| [view-tree-removed](#view-tree-removed) | P1 | Upgrade Safety | error | high |  |
| [deprecated-orm-api-usage](#deprecated-orm-api-usage) | P2 | Upgrade Safety | warning | high |  |
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

**Fix**: Use `ast.literal_eval` for a stored literal (a domain, a list), `odoo.tools.safe_eval.safe_eval` for an expression that needs variables, or refactor to explicit logic.

**Note**: An argument provably built from constants (a literal, or a variable bound only to constants) is not reported; anything else, including a parameter or a string with interpolated values, is. The message shows the evaluated expression. A module that binds the name itself (`from odoo.tools.safe_eval import safe_eval as eval`, an Odoo 8/9 idiom) is calling that function, not the builtin, and is not reported. Odoo 19 community contains one bare `exec` (the `shell` command), so a finding here is almost always genuine.

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

**Detects**: Models defined in the module with no row in `security/ir.model.access.csv` (or no CSV file at all). A model the module only extends (`_inherit`, with or without repeating its `_name`) needs no row of its own here.

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

**Note**: `<anything>._table` is a trusted identifier (set by the model author and validated by the registry), and scripts under `tests/`, `migrations/` and `upgrades/` (Odoo 18+) are skipped. When the dynamic part is not user data (for example a WHERE fragment whose values are bound through parameters), assert it with pylint-odoo's marker `# pylint: disable=sql-injection`, which this rule honours: a trailing comment covers its line, a comment on its own line covers the rest of the enclosing function. `# odoo-doctor: disable=raw-sql-string-interpolation` also works. The rule follows values through local variables, lists (`append`, `extend`, `+=`), `if`/`try`/loop branches and module constants: SQL built only from constants, `int()` casts, `self._table`, `SQL(...)` or `','.join(['%s'] * n)` placeholder lists is not reported, while a fragment that reaches the query through a list or a branch is. Test code (`tests/`), `migrations/` and the install-time hooks `init` / `_auto_init` that take only `self` (where SQL views are created) are skipped: nothing a request controls reaches them.

Bad:

```python
self.env.cr.execute(f"SELECT * FROM res_partner WHERE name = '{name}'")
```

Good:

```python
self.env.cr.execute("SELECT * FROM res_partner WHERE name = %s", (name,))
```

### access-write-without-group

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Rows in `ir.model.access.csv` with an empty `group_id:id` that grant `perm_write`, `perm_unlink` or `perm_create`. Rows for wizards (`TransientModel`) are ignored.

**Why**: A row without a group applies to every user, portal and public users included, so anyone can modify or delete the model's records.

**Fix**: Set `group_id:id` to `base.group_user` or a dedicated group, and keep the group-less row read-only if it must stay.

**Note**: A row that only grants `create` is reported at medium confidence and does not affect the score: public forms create records anonymously on purpose.

Bad:

```csv
access_x,x,model_x,,1,1,1,1
```

Good:

```csv
access_x,x,model_x,base.group_user,1,1,1,1
```

### csrf-disabled-authenticated-route

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Routes declared with `csrf=False` that run as the logged-in user (`auth='user'`, the default), have `type='http'` and accept POST, PUT, PATCH or DELETE (or leave `methods` unset, at medium confidence).

**Why**: A browser sends the session cookie on a cross-site request, so any page the user visits can trigger the route. Odoo only checks the CSRF token on these routes.

**Fix**: Remove `csrf=False` and send the token with the request (`request.csrf_token()`). A trusted third party that calls the route should use `auth='public'` and a verified signature or secret instead of the session.

**Note**: Webhooks (`auth='public'` / `'none'`), JSON routes and GET-only routes are not reported: they carry no session identity of their own, or Odoo never checks the token for them.

Bad:

```python
@http.route('/my/save', type='http', auth='user', methods=['POST'], csrf=False)
```

Good:

```python
@http.route('/my/save', type='http', auth='user', methods=['POST'])
```

### dynamic-method-dispatch

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `getattr(obj, name)(...)` (called directly or through a variable) where `name` is not a constant. A name built on a constant prefix (`'_get_%s' % kind`), looked up in a module-level table, checked in the same function (`in` / `==`, `startswith`) or taken from a logger is ignored.

**Why**: Whoever controls the name can run any method of the object, ORM methods such as `unlink()` or `sudo()` included. Refusing names that start with `_` is not enough.

**Fix**: Map the accepted names to methods in a dict or a set and reject the rest, or build the name on a constant prefix.

**Note**: High confidence when the name comes from the parameters of a public method (reachable by RPC or HTTP). Names read from records or other data, and names in private helpers, are medium and do not affect the score.

Bad:

```python
def download(self, method_print):
    return getattr(self, method_print)()
```

Good:

```python
REPORTS = {'xlsx': '_report_xlsx', 'pdf': '_report_pdf'}

def download(self, kind):
    return getattr(self, REPORTS[kind])()
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

**Note**: A route that also calls an access check (`consteq` on an access token, `_document_check_access`, a signature or `check_access*` call) is reported at medium confidence and does not affect the score; without one it is high. `.sudo(False)` and `env['ir.config_parameter'].sudo().get_param('<constant>')` are not elevations. Public website routes legitimately use `sudo()`: about one in five routes of Odoo 19 community does, so review rather than ban.

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

### rpc-sudo-without-access-check

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Public model methods (no leading underscore) and authenticated routes that call `.sudo()` on records or values chosen by their parameters, with no access check in the method: `check_access*`, `has_access`, a token or group test, a check-style helper, or a `raise` that refuses the caller. Public routes (`auth='public'`) are left to `public-controller-sudo-risk`.

**Why**: A public method is reachable with any record ids and arguments. Elevating with `sudo()` on what the caller picked lets them read or change records their rights and record rules would refuse (an IDOR).

**Fix**: Check the caller's rights on the records before elevating (`record.check_access('read')` / `has_access`), or drop `sudo()` and let the record rules apply; elevate only the narrowest recordset.

**Note**: High confidence only when a parameter reaches a write, unlink or create on the elevated recordset and the method does not scope by the caller (`env.user`, `uid`). Reads, `search` results (already filtered by the caller's rules) and parameters handed to another method (where a check may live) are medium or ignored; medium does not affect the score.

Bad:

```python
def close(self, rid):
    self.env['x.y'].sudo().browse(rid).write({'state': 'closed'})
```

Good:

```python
def close(self, rid):
    rec = self.env['x.y'].browse(rid)
    rec.check_access('write')
    rec.sudo().write({'state': 'closed'})
```

### sudo-without-comment

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: low · **Min Odoo version**: 14.0

**Detects**: `.sudo()` calls with no justifying comment on any line of the statement or directly above it (a compound statement counts only its header line(s)).

**Why**: Every privilege elevation should be reviewable; an undocumented `sudo()` is hard to audit.

**Fix**: Add a short comment explaining why elevated privileges are needed.

**Note**: `.sudo(False)` (drops privileges), test files and migration scripts are skipped. A comment on every `sudo()` is a team convention rather than a defect (Odoo's own addons leave most of theirs uncommented), and addons you only vendor are best left out with `[ignore] modules`. Low confidence: does not affect the score, and `min_confidence = "medium"` on a surface hides it.

Bad:

```python
partner = self.env['res.partner'].sudo().browse(pid)
```

Good:

```python
# sudo: portal users cannot read partners but need the display name
partner = self.env['res.partner'].sudo().browse(pid)
```

### tls-verification-disabled

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Code that turns off TLS verification: `verify=False` on a call, `session.verify = False`, `ctx.check_hostname = False`, `ctx.verify_mode = ssl.CERT_NONE` and `ssl._create_unverified_context()`.

**Why**: Without certificate verification anyone on the network path can pose as the server and read or change the traffic, including credentials and API tokens.

**Fix**: Remove the override. For a private or self-signed certificate, point `verify` at the CA bundle, or install the CA on the host.

**Note**: `verify=False` in a file that imports no network library is reported at medium confidence, because the keyword may belong to an unrelated function. Scripts under `tests/` and `migrations/` are skipped.

Bad:

```python
requests.get(url, verify=False)
```

Good:

```python
requests.get(url, verify='/etc/ssl/certs/company-ca.pem', timeout=10)
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

**Note**: A field the method assigns (`rec.total = ...`) is its result, not an input, so reading it back inside the same method is not reported.

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

**Detects**: `create()` called inside a loop (its iterable and `else` clause excluded; chunked and constant-literal loops are skipped).

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

**Detects**: Field reads on a record built by `browse(<one id>)` on every iteration of a `for` loop or comprehension (the id depends on the loop variable).

**Why**: Odoo prefetches: iterating a recordset and reading `line.product_id.name` costs one query per field for the whole recordset. A singleton browsed per iteration starts with an empty prefetch, so every read hits the database.

**Fix**: Browse all the ids once before the loop and iterate that recordset, or call `with_prefetch(ids)` on the browsed record.

**Note**: Looping over a recordset (`for line in order.line_ids:`) is not reported, and neither are `with_prefetch(...)`, method calls and `id` / `env`. Low confidence: does not affect the score.

Bad:

```python
for pid in partner_ids:
    name = self.env['res.partner'].browse(pid).country_id.name
```

Good:

```python
for partner in self.env['res.partner'].browse(partner_ids):
    name = partner.country_id.name
```

### search-in-loop

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: ORM queries (`search`, `search_count`, `read`) inside `for` or `while` loops. `browse()` is not flagged: it only wraps ids and does not query the database.

**Why**: One query per iteration scales badly with record count.

**Fix**: Move the call out of the loop and batch the results.

**Note**: The performance rules skip files inside an addon's `tests/` directory. Only what runs on every iteration counts: the loop's own iterable (`for rec in self.env[...].search(...)`) and its `else` clause run once. Loops over chunks (`split_every(...)`, `range(a, b, step)`), over a literal tuple/list of constants, and `while` loops paged with `limit=N` (N > 1) are not reported.

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

**Detects**: `write()` called inside a loop (its iterable and `else` clause excluded; chunked and constant-literal loops are skipped).

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

### http-request-without-timeout

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `requests.get/post/put/patch/delete/head/options/request()`, the same calls on a `requests.Session`, and `urllib.request.urlopen()` without a `timeout`.

**Why**: Neither library gives up on its own. One unresponsive server holds an Odoo worker until the server-wide time limit kills it, and with it every request that worker was serving.

**Fix**: Pass an explicit `timeout` in seconds, or a `(connect, read)` pair.

**Note**: A call that passes `**options` is not reported, because `timeout` may be in it. Scripts under `tests/` and `migrations/` are skipped.

Bad:

```python
response = requests.post(url, json=payload)
```

Good:

```python
response = requests.post(url, json=payload, timeout=10)
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

### manual-cr-commit

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: `cr.commit()` on the transaction Odoo opened for the request: `self.env.cr`, `self._cr`, `request.cr`. A commit on another name (`env.cr`, `cr`) is medium confidence and does not affect the score.

**Why**: A commit ends the request's transaction. Work done before it can no longer be rolled back, so a later error leaves the database half updated.

**Fix**: Remove the commit and let Odoo commit when the request succeeds. Run batch work from a cron or a queue job, or in its own cursor (`with self.pool.cursor() as cr:`).

**Note**: Not reported: a cursor or environment the code opened itself (`registry.cursor()`, `self.pool.cursor()`, `api.Environment(...)`), cron methods (a function with `cron` in its name), install hooks (`init`, `_auto_init`, `post_init_hook`...), a commit under an `if` that tests `test_enable` / `testing`, and a line marked `# pylint: disable=invalid-commit`. Scripts under `tests/` and `migrations/` are skipped.

Bad:

```python
def action_import(self):
    for row in rows:
        self.create(row)
        self.env.cr.commit()
```

Good:

```python
def action_import(self):
    self.create(rows)
```

### missing-ondelete

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: low · **Min Odoo version**: 14.0

**Detects**: `Many2one` fields on non-transient, non-abstract models without an explicit `ondelete`.

**Why**: An optional `Many2one` defaults to `set null`: deleting the target silently empties the field, which orphans a line whose parent is deleted. Declaring the policy documents the intent.

**Fix**: Declare `ondelete` explicitly.

**Note**: Required `Many2one` fields are skipped: Odoo already defaults them to `restrict`. So are related or computed fields that are not stored (no `store=True`): they have no foreign-key column. Low confidence: the default is a legitimate choice (about 83% of Odoo 19 community's optional stored `Many2one` fields rely on it), so this is a hint that does not affect the score.

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

### act-window-target-inline

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 19.0

**Detects**: An `ir.actions.act_window` record or Python action dict with `target` set to `inline` (Odoo 19).

**Why**: Odoo 19 removed `inline` from the `target` selection, so the record is rejected on install or update.

**Fix**: Use `current` (the settings actions of Odoo 19 do), or `new` for a dialog.

Bad:

```xml
<field name="target">inline</field>
```

Good:

```xml
<field name="target">current</field>
```

### chatter-div-removed

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 18.0

**Detects**: A `<div class="oe_chatter">` in a view architecture (Odoo 18 and later).

**Why**: The form compiler of Odoo 17 selected `div.oe_chatter`. Odoo 18 and 19 select only the `<chatter/>` tag, so the div is a plain block and the form shows no followers, messages or activities. The view still loads, so nothing fails at install time.

**Fix**: Replace the whole `<div class="oe_chatter">...</div>` block with `<chatter/>`.

**Note**: Checked against the form compilers of Odoo 18.0 and 19.0; no Odoo 18/19 code reads `oe_chatter` any more.

Bad:

```xml
<div class="oe_chatter">
    <field name="message_follower_ids"/>
    <field name="message_ids"/>
</div>
```

Good:

```xml
<chatter/>
```

### cron-removed-fields

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 18.0

**Detects**: `ir.cron` records in data or demo files that set `numbercall` or `doall`, on Odoo 18 and later.

**Why**: `ir.cron` no longer has these fields since Odoo 18. A job that used `numbercall` to run a limited number of times now repeats on every interval.

**Fix**: Remove the fields. If the job must stop after some runs, have its method deactivate the cron.

**Note**: Only `ir.cron` records are checked; the same field names on other models are left alone.

Bad:

```xml
<field name="numbercall">-1</field>
<field name="doall" eval="False"/>
```

Good:

```xml
<!-- nothing: the interval fields are enough -->
```

### deprecated-api-usage

**Tier**: P1 (serious) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Old-API patterns: `from openerp` imports, `_columns`, `osv.osv` and model calls through the pool with `cr, uid`.

**Why**: They belong to Odoo 7-9 and are removed in modern versions.

**Fix**: Migrate to the new API.

**Note**: `self.pool['model']` alone is the registry (a model class, used for `isinstance` checks) and is not reported. Scripts in `migrations/<version>/` for a version before Odoo 10 may import `openerp`: they ran on databases of that era.

Bad:

```python
from openerp import models
class MyModel(osv.osv): ...
self.pool.get('res.partner').search(cr, uid, [])
```

Good:

```python
from odoo import models
class MyModel(models.Model): ...
self.env['res.partner'].search([])
```

### kanban-legacy-templates

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 19.0

**Detects**: The `t-name="kanban-box"` and `t-name="kanban-menu"` templates of a kanban view, and an XPath that targets them (Odoo 19).

**Why**: Odoo 18 renamed them `card` and `menu` and still read the old names with a deprecation note. Odoo 19 reads only the new names: the view fails with "Missing 'card' template", and an XPath on the old name finds no anchor in the core kanban view.

**Fix**: Rename `kanban-box` to `card` and `kanban-menu` to `menu`, port the card markup to the Odoo 18 layout (`main` / `aside` / `footer`) and re-anchor inherited XPaths.

Bad:

```xml
<t t-name="kanban-box">...</t>
```

Good:

```xml
<t t-name="card">...</t>
```

### removed-core-field-usage

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 18.0

**Detects**: Fields that core models no longer have, set by a data record or shown by a view: `groups_id` of `res.users`, `ir.ui.view`, `ir.ui.menu` and the actions (renamed `group_ids`, Odoo 19), `category_id` and `users` of `res.groups`, `mobile` of `res.partner` and `crm.lead`, `deprecated` of `account.account`, `user_id` of `ir.filters` (Odoo 19), and `detailed_type` of the product models (Odoo 18). In Python, the names `groups_id` and `detailed_type` as attribute, dict key, domain term or `selection_add` target.

**Why**: A record that sets a missing field fails to load (`Invalid field ... in ...`), and the module cannot be installed or updated.

**Fix**: Use the replacement named in the finding, for example `group_ids`, `user_ids`, `privilege_id` (with a `res.groups.privilege` record), `phone`, `active`, or `type` plus `is_storable`.

**Note**: The table lists only fields that the ORM source of that release no longer defines. In XML the model comes from the record, so the finding is high confidence. The Python names are unique to the removed fields, so a hit is medium confidence (no score effect); a model the module creates itself (`_name`), `'groups_id' in rec._fields` and `hasattr()` probes are skipped.

Bad:

```xml
<record id="group_x" model="res.groups">
    <field name="name">X</field>
    <field name="users" eval="[(4, ref('base.user_admin'))]"/>
</record>
```

Good:

```xml
<record id="group_x" model="res.groups">
    <field name="name">X</field>
    <field name="user_ids" eval="[(4, ref('base.user_admin'))]"/>
</record>
```

### removed-model-still-referenced

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: medium · **Min Odoo version**: 14.0

**Detects**: `_inherit` of a core model that Odoo removed or renamed at or before the target version (for example `account.invoice`, `stock.production.lot`, `mail.channel`, `ir.property`, `stock.valuation.layer`, `stock.quant.package`) and that the project does not define itself.

**Why**: Models are removed or renamed between versions; inheriting a missing model breaks the registry load.

**Fix**: Port the code to the replacement model named in the finding.

**Note**: Based on a curated list of certain removals: a model that is merely absent from the scanned set is usually an unscanned dependency and is not reported. Medium confidence: does not affect the score.

### removed-orm-api-usage

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 17.0

**Detects**: Overrides and calls of ORM methods the running Odoo version no longer defines: `fields_view_get` and `invalidate_cache` (removed in 17), `name_get` (removed in 18). A call on `self` or `env` is high confidence; a call on an unrelated object is medium and does not affect the score.

**Why**: An override of a removed method is dead code, because nothing calls it any more, and a call raises `AttributeError`.

**Fix**: Use `get_view()` for `fields_view_get`, `invalidate_model()` / `invalidate_recordset()` for `invalidate_cache`, and `_compute_display_name` for `name_get`.

**Note**: Each method is reported only from the Odoo version whose ORM source no longer defines it. `super().name_get()` inside an override is not reported twice.

Bad:

```python
def name_get(self):
    return [(r.id, r.name) for r in self]
```

Good:

```python
@api.depends('name')
def _compute_display_name(self):
    for r in self:
        r.display_name = r.name
```

### search-view-group-attributes

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 19.0

**Detects**: `string` or `expand` on a `<group>` inside a search view (Odoo 19).

**Why**: The Odoo 19 search view schema no longer allows those attributes on `<group>`, so the view is rejected on install or update. In Odoo 18 they are still valid.

**Fix**: Use a bare `<group>` around the "Group By" filters.

**Note**: An inherited view is checked only for a `<group>` that holds `<filter>` children, which only a search view has. `<group string>` in a form view is valid and not reported.

Bad:

```xml
<group expand="0" string="Group By">
    <filter name="by_user" string="User" context="{'group_by': 'user_id'}"/>
</group>
```

Good:

```xml
<group>
    <filter name="by_user" string="User" context="{'group_by': 'user_id'}"/>
</group>
```

### sql-constraints-unsupported

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 19.0

**Detects**: A model class that sets `_sql_constraints` to a non-empty list, on Odoo 19 and later. Plain Python mixins, empty lists and test files are ignored.

**Why**: Odoo 19 no longer reads `_sql_constraints`: it only logs a warning and creates none of the constraints, so a UNIQUE or CHECK the model relied on silently stops being enforced.

**Fix**: Declare each constraint as a class attribute with `models.Constraint`, after checking the database for rows that would violate a UNIQUE one.

**Note**: Gated to Odoo 19 and later (`min_version`). Verified against the Odoo 19 ORM source, which logs that the attribute is no longer supported.

Bad:

```python
_sql_constraints = [('name_uniq', 'unique(name)', 'Name must be unique')]
```

Good:

```python
_name_uniq = models.Constraint('UNIQUE(name)', 'Name must be unique')
```

### view-attrs-states-removed

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 17.0

**Detects**: Elements with `attrs` or `states` (or an `<attribute name="attrs">` xpath edit) in the architecture of an `ir.ui.view` record, on Odoo 17 and later. One finding per view. QWeb templates are not checked.

**Why**: Odoo 17 and later refuse such a view ("Since 17.0, the attrs and states attributes are no longer used"), so the module cannot be installed or updated.

**Fix**: Put the condition in the attribute itself: `invisible`, `readonly` or `required` take a Python expression on the record's fields.

**Note**: `states="draft,sent"` on a button becomes `invisible="state not in ('draft', 'sent')"`.

Bad:

```xml
<field name="note" attrs="{'invisible': [('state', '=', 'draft')]}"/>
```

Good:

```xml
<field name="note" invisible="state == 'draft'"/>
```

### view-tree-removed

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 18.0

**Detects**: The `tree` view type on Odoo 18 and later: a `<tree>` element in a view architecture (also nested in an x2many field), `<field name="type">tree`, a `tree` step in an XPath, `tree` in the `view_mode` of an action or an `ir.actions.act_window.view`, and Python action dicts with `'view_mode': 'tree,form'` or a `(False, 'tree')` pair in `'views'`.

**Why**: Odoo 18 renamed the tree view type to `list` and kept no alias, so the view is rejected on install or update and the action cannot open.

**Fix**: Rename: `<tree>` to `<list>`, `tree,form` to `list,form`, and the XPath step `tree` to `list`.

**Note**: Reported once per view or action record. A Python dict that does not look like an action (no `res_model`, no `type`) is medium confidence. Only files the manifest loads are read, and QWeb templates are skipped.

Bad:

```xml
<record id="view_x_tree" model="ir.ui.view">
    <field name="model">x.model</field>
    <field name="arch" type="xml">
        <tree><field name="name"/></tree>
    </field>
</record>
```

Good:

```xml
<record id="view_x_list" model="ir.ui.view">
    <field name="model">x.model</field>
    <field name="arch" type="xml">
        <list><field name="name"/></list>
    </field>
</record>
```

### deprecated-orm-api-usage

**Tier**: P2 (moderate) · **Severity**: warning · **Confidence**: high · **Min Odoo version**: 18.0

**Detects**: Calls of ORM methods the running Odoo version still defines but deprecates: `read_group`, `toggle_active` and `check_field_access_rights` (Odoo 19), `check_access_rights`, `check_access_rule`, `_filter_access_rules`, `_check_recursion` and `_check_m2m_recursion` (Odoo 18). An override of `read_group` is reported on Odoo 19 as well. A call on `self` or `env` is high confidence; a call on an unrelated object is medium and does not affect the score.

**Why**: A deprecated method keeps working and logs a warning until a later release removes it. On Odoo 19 nothing in core calls `read_group` any more: grouped views use `web_read_group` and `formatted_read_group`, which go through `_read_group`, so an override of `read_group` is not applied to them.

**Fix**: Use `_read_group()` in backend code or `formatted_read_group()` for a formatted result, `check_access()` / `has_access()` for the access checks, `_has_cycle()` (it returns True when there is a cycle) for the recursion checks, and `action_archive()` / `action_unarchive()` for `toggle_active`.

**Note**: Each method is reported only from the Odoo version whose ORM source deprecates it. `self._cr`, `self._uid` and `self._context` are deprecated in Odoo 19 too but are not reported: core still uses them and they would bury every other finding. `super().read_group()` inside an override is not reported twice.

Bad:

```python
groups = self.env['sale.order'].read_group(
    domain, ['amount_total:sum'], ['partner_id'])
```

Good:

```python
groups = self.env['sale.order']._read_group(
    domain, ['partner_id'], ['amount_total:sum'])
```

## Module Hygiene

### manifest-missing-dependency

**Tier**: P1 (serious) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0

**Detects**: Modules required by Python `_inherit` models, XML external ID references (including `eval="ref(...)"`) and inherited views that are not listed in `depends`.

**Why**: The module installs only when another module happens to be installed first.

**Fix**: Add the providing module to `depends`.

**Note**: A module reachable through `depends` transitively counts as available. When part of that chain is a module whose manifest is unknown (set `odoo_source_path` to index core addons), the finding is reported with medium confidence and does not affect the score.

### manifest-data-order-risk

**Tier**: P2 (moderate) · **Severity**: error · **Confidence**: high · **Min Odoo version**: 14.0 · **Fixable**: yes

**Detects**: A security file listed in `data` after a view/action file. It is reported with high confidence only when that security XML creates a group which an earlier file already needs when it loads (a `<menuitem groups=...>`, a `<template groups=...>`, or a `groups_id` / `group_ids` / `groups` field with `ref` or `eval="ref(...)"`).

**Why**: Odoo resolves those references while the earlier file loads and raises if the group does not exist yet, so the module cannot be installed. A group named only in a view arch (`groups=` on a field or button) just logs a warning.

**Fix**: List the security file that creates the group before the first file that uses it.

**Note**: Every other case is advisory (medium confidence, no score impact, not auto-fixed): `ir.model.access.csv` and security files that only update a group which already exists, or that define groups no earlier file needs. Fixable via `odoo-doctor fix` for the high case: the file is moved in front of the first file that needs it, with a local edit of the `data` lines. The fixer declines when the list is not one element per line or when it cannot show the new position keeps what the file depends on loaded before it.

Bad:

```python
'data': [
    'views/menus.xml',      # <menuitem groups="my_mod.group_x"/>
    'security/groups.xml',  # creates group_x
]
```

Good:

```python
'data': [
    'security/groups.xml',
    'views/menus.xml',
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

**Note**: Missing `version` and `data` are `medium` confidence (Odoo defaults both, and Odoo core omits them from many manifests), so they do not lower the score; `name`, `depends` and `license` stay `high`. Fixable via `odoo-doctor fix`, which adds only the absent high-confidence keys with a local edit and leaves everything else byte-identical. `installable` is not required (Odoo defaults it to `True`), and `data` is not required when the manifest declares `assets` or `demo`.

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

**Detects**: Extra primary views that are not their model's default view of that type and that nothing in the module references or inherits.

**Fix**: Reference the view, inherit it, or remove it if unused.

**Note**: Odoo serves a model's primary view of each type (lowest `priority`, then first defined) without any reference, so that one is never flagged; neither are QWeb views or ids mentioned in Python, JS, XML or CSV. Medium confidence: the reference may live in a module that was not scanned. Does not affect the score.

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
