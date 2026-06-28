# Built-in Rules

Each rule has:
- **tier**: P0 (critical) → P1 (serious) → P2 (moderate) → P3 (advisory)
- **category**: one of Security, Correctness, Performance, Module Hygiene, Maintainability, Uncategorized

## Security Rules

### raw-sql-string-interpolation [P0]

**Detects**: `cr.execute()` calls using f-strings or `%`-formatting.

**Why**: String interpolation in SQL leads to SQL injection vulnerabilities.

**Fix**: Use parameterized queries:
```python
# Bad
self.env.cr.execute(f"SELECT * FROM {table}")

# Good
self.env.cr.execute("SELECT * FROM %s", (table,))
```

---

### missing-access-csv [P0]

**Detects**: Models defined without any record in `ir.model.access.csv`.

**Fix**: Create `security/ir.model.access.csv` and add ACL rows.

---

## Correctness Rules

### unknown-model-in-access-csv [P1]

**Detects**: Access rules in the CSV that reference models that don't exist.

**Fix**: Correct the model name to match the `_name` attribute.

---

### duplicate-xml-id [P1]

**Detects**: The same XML ID appearing multiple times in the same module.

**Fix**: Remove or rename the duplicate.

---

### view-field-not-in-model [P1]

**Detects**: Views that reference fields not found on the model.

**Note**: Only fires when confidence is HIGH — i.e., the model is known (in stubs or in the repo) and the field provably doesn't exist.

---

### button-method-not-found [P1]

**Detects**: Buttons with `type="object"` calling a method that doesn't exist on the model.

---

### missing-xml-ref [P1]

**Detects**: `ref="..."` attributes referencing XML IDs that can't be resolved.

---

## Module Hygiene Rules

### manifest-missing-required-fields [P2]

**Detects**: `__manifest__.py` missing one of: `name`, `version`, `depends`, `data`, `installable`, `license`.

**Fixable**: Yes, supports auto-fix via `odoo-doctor fix`.

---

### manifest-missing-dependency [P1]

**Detects**: Dependencies required by Python `_inherit` models, XML external ID references (including `eval="ref(...)"`), and inherited XML views, when the providing module is not listed in `depends`.

---

---

## Performance Rules

### search-in-loop [P1]

**Detects**: ORM calls (`search`, `browse`, `read`, `write`, `create`) inside `for` or `while` loops.

**Fix**: Move the ORM call outside the loop and batch results.

---

### unbounded-search [P2]

**Detects**: `search()` or `read()` calls without a limit on result count.

**Why**: Unbounded searches can load thousands of records into memory, causing performance issues.

**Fix**: Add a `limit` parameter:
```python
# Bad
records = self.env['res.partner'].search([('country_id', '=', country_id)])

# Good
records = self.env['res.partner'].search([('country_id', '=', country_id)], limit=100)
```

---

## Security Rules (Additional)

### public-controller-sudo-risk [P1]

**Detects**: `@route()` methods with `auth='public'` or `auth='none'` that call `sudo()` or access sensitive data.

**Why**: Public endpoints that bypass permission checks expose authentication/authorization vulnerabilities.

**Fix**: Use appropriate authentication level:
```python
# Bad
@route('/api/data', auth='public')
def get_data(self):
    return self.env['private.model'].sudo().search([])

# Good
@route('/api/data', auth='user')  # Require login
def get_data(self):
    return self.env['public.model'].search([])
```

---

## Correctness Rules (Additional)

### override-missing-super [P1]

**Detects**: Methods that override inherited ORM methods (like `create()`, `write()`, `unlink()`) without calling `super()`.

**Why**: Skipping `super()` breaks the method chain and bypasses parent logic, validation, and hooks.

**Fix**: Call parent implementation:
```python
# Bad
def create(self, vals):
    # Custom logic but no super!
    return self.env['res.partner'].create(vals)

# Good
def create(self, vals):
    result = super().create(vals)
    # Custom logic after parent
    return result
```

---

### compute-missing-depends [P2]

**Detects**: `@computed_field` or `@depends()` decorators missing required field dependencies.

**Why**: Missing dependencies can cause stale computed values and lead to data inconsistencies.

**Fix**: List all fields the computation depends on:
```python
# Bad
@computed_field
def total_amount(self):
    return self.quantity * self.unit_price

# Good
@computed_field
@depends('quantity', 'unit_price')
def total_amount(self):
    return self.quantity * self.unit_price
```

---

## Module Hygiene Rules (Additional)

### manifest-data-order-risk [P2]

**Detects**: Data files in `__manifest__.py` that may load in an unsafe order (e.g., XML before dependencies, records before security rules).

**Fixable**: Yes, supports auto-fix via `odoo-doctor fix`.

**Why**: Loading files in the wrong order can cause foreign key violations, missing references, or security rule conflicts.

**Fix**: Order data files by dependency:
```python
# Bad
'data': [
    'data/custom_records.xml',  # Depends on views
    'views/my_views.xml',       # Loaded after records
    'security/ir.model.access.csv',
]

# Good
'data': [
    'security/ir.model.access.csv',  # Security first
    'views/my_views.xml',            # Views before records
    'data/custom_records.xml',       # Records after dependencies
]
```

---

## Data Integrity Rules

### missing-ondelete [P1]

**Detects**: Many2one fields on non-transient, non-abstract models that lack an explicit `ondelete` keyword argument.

**Why**: The default `ondelete='set null'` may not be appropriate for all relations. Explicitly declaring the ondelete policy documents the intended behavior and prevents data integrity issues when referenced records are deleted.

**Fix**: Add an explicit ondelete policy:
```python
# Bad
partner_id = fields.Many2one("res.partner")

# Good
partner_id = fields.Many2one("res.partner", ondelete="restrict")
```

---

### data-noupdate-risk [P2]

**Detects**: Records of critical models (`ir.rule`, `ir.config_parameter`, `ir.cron`) in XML data files that are not wrapped in `noupdate="1"`.

**Why**: Records without `noupdate="1"` are overwritten on every module update, discarding any user modifications. This is particularly dangerous for security rules, configuration parameters, and scheduled actions.

**Fix**: Wrap critical records in a `<data noupdate="1">` block:
```xml
<!-- Bad -->
<odoo>
    <record id="my_rule" model="ir.rule">
        <field name="name">My Rule</field>
    </record>
</odoo>

<!-- Good -->
<odoo>
    <data noupdate="1">
        <record id="my_rule" model="ir.rule">
            <field name="name">My Rule</field>
        </record>
    </data>
</odoo>
```

---

## Upgrade Safety Rules

### deprecated-api-usage [P1]

**Detects**: Use of deprecated Odoo APIs: `from openerp` imports, `_columns` dict, `osv.osv` inheritance, and `.pool` access pattern.

**Min version**: 14.0

**Why**: These patterns belong to the old API (Odoo 7.0–9.0) and are removed or unsupported in modern Odoo versions.

**Fix**: Migrate to the new API:
```python
# Bad
from openerp import models
_columns = {'name': fields.char('Name')}
class MyModel(osv.osv): ...
self.pool.get('res.partner')

# Good
from odoo import models, fields
name = fields.Char(string="Name")
class MyModel(models.Model): ...
self.env['res.partner']
```

---

### removed-model-still-referenced [P1]

**Detects**: Models in `_inherit` declarations that cannot be resolved in the project or Odoo stubs.

**Min version**: 14.0

**Confidence**: Medium (won't affect scoring)

**Why**: Models may be removed or renamed between Odoo versions. Inheriting a non-existent model causes import errors at runtime.

**Fix**: Verify the model exists in your target Odoo version and update the `_inherit` declaration accordingly.

---

## Frontend Rules

### asset-bundle-missing [P2]

**Detects**: Asset files listed in `__manifest__.py` `assets` dict that don't exist on disk.

**Min version**: 15.0

**Why**: Missing asset files cause JavaScript/CSS loading errors at runtime, breaking the Odoo web client UI.

**Fix**: Create the missing file or remove the reference from the manifest:
```python
# Manifest declares:
'assets': {
    'web.assets_backend': [
        'my_module/static/src/js/missing_script.js',  # File doesn't exist!
    ],
}

# Fix: create the file at static/src/js/missing_script.js
# or remove the entry from the assets dict
```

---

## Summary of All Rules

| Rule | Tier | Category | Fixable |
|------|------|----------|---------|
| raw-sql-string-interpolation | P0 | Security | |
| missing-access-csv | P0 | Security | |
| eval-usage | P0 | Security | |
| public-controller-sudo-risk | P1 | Security | |
| sudo-without-comment | P1 | Security | |
| unknown-model-in-access-csv | P1 | Correctness | |
| duplicate-xml-id | P1 | Correctness | |
| view-field-not-in-model | P1 | Correctness | |
| button-method-not-found | P1 | Correctness | |
| missing-xml-ref | P1 | Correctness | |
| override-missing-super | P1 | Correctness | |
| manifest-missing-dependency | P1 | Module Hygiene | |
| search-in-loop | P1 | Performance | |
| create-in-loop | P1 | Performance | |
| write-in-loop | P1 | Performance | |
| n-plus-one-read | P1 | Performance | |
| unbounded-search | P2 | Performance | |
| compute-missing-depends | P2 | Correctness | |
| orphan-view | P2 | Maintainability | |
| record-rule-without-domain | P1 | Security | |
| field-no-string-on-required | P2 | Maintainability | |
| missing-translation | P2 | Maintainability | |
| missing-ondelete | P1 | Data Integrity | |
| data-noupdate-risk | P2 | Data Integrity | |
| deprecated-api-usage | P1 | Upgrade Safety | |
| removed-model-still-referenced | P1 | Upgrade Safety | |
| manifest-missing-required-fields | P2 | Module Hygiene | Yes |
| manifest-data-order-risk | P2 | Module Hygiene | Yes |
| asset-bundle-missing | P2 | Frontend | |

## New Rules

### orphan-view [P2]
**Detects**: Unreferenced views.
**Fix**: Reference or delete them.

### record-rule-without-domain [P1]
**Detects**: ir.rule without a domain_force.
**Fix**: Add a valid domain_force.

### field-no-string-on-required [P2]
**Detects**: required=True fields without string label.
**Fix**: Add string="...".

### missing-translation [P2]
**Detects**: UserError/ValidationError strings not wrapped in _().
**Fix**: Wrap with _("...").

### create-in-loop / write-in-loop [P1]
**Detects**: create/write called inside loops.
**Fix**: Batch records and call create/write once.

### n-plus-one-read [P1]
**Detects**: Chained attribute access inside loops.
**Fix**: Prefetch before looping.

### eval-usage [P0]
**Detects**: Use of built-in eval/exec.
**Fix**: Use safe_eval or explicit logic.

### sudo-without-comment [P1]
**Detects**: .sudo() without comment.
**Fix**: Add a comment explaining why sudo is needed.
