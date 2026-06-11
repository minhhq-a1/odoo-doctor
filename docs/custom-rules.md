# Writing custom rules (experimental)

> Status: **skeleton** in v0.3.0. The contract below is provisional and may
> change in v0.4.0.

A custom rule lives in your own Python package and registers itself via an
entry point. Odoo Doctor imports your module at startup, which runs your
`@rule` decorators.

## 1. Write the rule

```python
# my_odoo_rules/no_print.py
import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.source import read_source
from odoo_doctor.rules.registry import rule


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

## 3. Enable plugins (opt-in) and run

Plugin loading runs third-party code with your full privileges, so it is OFF by
default. Enable it explicitly in odoo-doctor.toml:

```toml
[plugins]
enabled = true
```

```bash
pip install -e .
odoo-doctor scan .   # your rule runs only because [plugins].enabled = true
```

## Security / trust model

> Plugins are **not sandboxed** in v0.3.0. Importing a plugin executes its
> module code. Only enable plugins from sources you trust, exactly as you would
> for any installed Python package. A future release (v0.4.0) may add an
> allowlist; until then `[plugins].enabled` is the only gate.

## Rule contract

- Context rules: `needs_context=True`, signature `func(ctx: ModuleContext)`.
- File rules: `needs_context=False`, signature
  `func(file_path: Path, module_name: str, odoo_version: str)`.
- Return a `list[Diagnostic]`. Only `confidence="high"` findings affect scores.
- `category` must be one of the values in `core/diagnostics.py:CATEGORIES`.
