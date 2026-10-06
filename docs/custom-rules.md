# Writing custom rules

> Status: **stable (plugin API v1)** since v0.5.0. Import only from
> `odoo_doctor.plugin_api`; everything else in `odoo_doctor` is internal. Changes
> to that module follow `PLUGIN_API_VERSION`: additions keep the version,
> breaking changes bump it.

## Quick start

```bash
odoo-doctor rules new no-print-statements --out .   # creates odoo-doctor-rules-no-print-statements/
cd odoo-doctor-rules-no-print-statements
pip install -e ".[dev]" && pytest
```

The command writes a ready-to-install pack: `pyproject.toml` with the entry point, a starter
rule in `src/odoo_doctor_rules_<name>/rules.py` (it flags `print()` calls; replace it with
your check), tests in `tests/` that build a small source file and assert the findings, a
README and a `.gitignore`. The name must be kebab-case and must not be an existing rule; the
command refuses to overwrite an existing directory. The generated rule imports only from
`odoo_doctor.plugin_api`. The sections below explain each part.

A custom rule lives in your own Python package and registers itself via an
entry point. Odoo Doctor imports your module at startup, which runs your
`@rule` decorators.

## 1. Write the rule

```python
# my_odoo_rules/no_print.py
import ast
from pathlib import Path

from odoo_doctor.plugin_api import Diagnostic, read_source, rule

ODOO_DOCTOR_PLUGIN_API = 1  # the plugin API version this module targets


@rule(
    name="no-print-statements",
    category="Maintainability",
    tier="P3",
    severity="info",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_no_print(file_path: Path, module_name: str, odoo_version: str):
    source = read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    diags = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            diags.append(
                Diagnostic(
                    module=module_name, file_path=str(file_path),
                    line=node.lineno, column=node.col_offset,
                    rule="no-print-statements", category="Maintainability",
                    severity="info", tier="P3", source="native",
                    confidence="high", title="print() left in code",
                    message="Remove debug print().", help="Use logging.",
                    odoo_version=odoo_version,
                )
            )
    return diags
```

## 2. Register the entry point

In your package's pyproject.toml:

```toml
[project.entry-points."odoo_doctor.rules"]
my_rules = "my_odoo_rules.no_print"
```

Naming convention for shared plugins: publish the package as
`odoo-doctor-rules-<topic>` so it is easy to find on PyPI.

## 3. Enable plugins (opt-in) and run

Plugin loading runs third-party code with your full privileges, so it is OFF by
default. Enable it explicitly in odoo-doctor.toml, optionally restricting which
entry points may load:

```toml
[plugins]
enabled = true
allow = ["my_rules"]   # optional; omit to load every discovered plugin
```

```bash
pip install -e .
odoo-doctor scan .   # your rule runs only because [plugins].enabled = true
```

## Guarantees

- **Opt-in.** Nothing loads unless `[plugins].enabled = true`.
- **Allowlist.** With `[plugins].allow`, entry points not listed are skipped
  (a message names each skipped plugin). `allow = []` loads nothing.
- **Validation at load time.** `category` must be one of `plugin_api.CATEGORIES`,
  `tier` one of `plugin_api.TIERS`, `severity` one of `plugin_api.SEVERITIES`,
  `default_confidence` one of `plugin_api.CONFIDENCES`. Otherwise `@rule` raises
  `ValueError` and the plugin is skipped.
- **No overrides.** A rule name already registered (built-in or another plugin)
  is rejected; a plugin can never replace a built-in rule.
- **Version check.** Declare the plugin API your module was written against with
  `ODOO_DOCTOR_PLUGIN_API = 1` at module level (the module your entry point
  names). It must be an integer equal to `plugin_api.PLUGIN_API_VERSION`;
  anything else (another number, `True`, `"1"`, `1.0`) refuses the plugin with a
  warning that names it. Omitting it still loads the plugin but prints a warning,
  because without it odoo-doctor cannot refuse the plugin when the API changes.
- **Rollback and isolation.** A plugin that raises while loading is skipped with
  a warning and every rule it had already registered is removed. A rule that
  raises while running is reported as a warning and skipped for that module/file;
  it never aborts the scan.
- **Same gates as built-ins.** `min_version` and `requires_capabilities` /
  `excludes_capabilities` are honored, and findings go through the normal
  pipeline (severity overrides, `[ignore]`, inline suppressions, baseline).
  Only `confidence="high"` findings affect scores.

## Rule contract

- Context rules: `needs_context=True`, signature `func(ctx: ModuleContext)`.
- File rules: `needs_context=False`, signature
  `func(file_path: Path, module_name: str, odoo_version: str)`; called once per
  `.py` file of each addon.
- Return (or yield) `Diagnostic` objects.
- Exported helpers: `Diagnostic`, `ModuleContext`, `rule`, `read_source`,
  `receiver_is_orm`, `node_is_orm`, plus the constants `PLUGIN_API_VERSION`,
  `CATEGORIES`, `TIERS`, `SEVERITIES` and `CONFIDENCES`.
- Plugin rules are not part of the built-in rules reference (`docs/rules.md`) and
  their findings carry no docs link unless you set `Diagnostic.url` yourself.

## Versioning policy

`PLUGIN_API_VERSION` is an integer. It stays the same when `plugin_api` gains names;
it is bumped, and the old value refused by the loader, only when a name is removed
or its behavior changes incompatibly. Such a bump follows the deprecation window in
[stability.md](stability.md). The exported names are frozen in
`tests/test_stability_contract.py`, and `tests/rules/test_plugin_api_ga.py` checks
that this page mentions every one of them.

## Security / trust model

> Plugins are **not sandboxed**. Importing a plugin executes its module code.
> Only enable plugins from sources you trust, exactly as you would for any
> installed Python package. `[plugins].enabled` and `[plugins].allow` are the
> only gates.
