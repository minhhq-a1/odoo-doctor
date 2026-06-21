# Repository Guidelines

## Project Overview

**Odoo Doctor** is a unified static analysis and health-scoring tool for custom Odoo addons. It detects security vulnerabilities, broken views, duplicate XML IDs, missing dependencies, and performance issues across 15 native rules, integrated with external linters (Ruff, Pylint-Odoo) to produce a single 0–100 health score per addon.

---

## Project Structure

```
odoo-doctor/
├── src/odoo_doctor/          # Main source code
│   ├── core/                 # Pipeline orchestration (7-stage), config, scoring
│   ├── rules/                # Rule implementations (P0–P3 tiers)
│   ├── parsers/              # Python AST, XML record, manifest, CSV parsing
│   ├── graph/                # Symbol resolution engine
│   ├── discovery/            # Addon discovery & Odoo version detection
│   ├── adapters/             # External linter integration (Ruff, Pylint-Odoo)
│   ├── reporters/            # Output formatting (GitHub, JSON, SARIF, plain text)
│   ├── cli/                  # CLI entry point (Typer)
│   └── skills/               # Agent-friendly SKILL.md documentation
├── tests/                    # 320+ test cases (~46 test files)
├── docs/                     # Rule documentation
├── pyproject.toml            # Build & dependency config
├── CLAUDE.md                 # Detailed developer guide
└── odoo-doctor.toml          # User config (generated via `odoo-doctor init`)
```

---

## Development Commands

### Setup & Installation
```bash
pip install -e ".[dev]"        # Install in editable mode with dev dependencies
```

### Testing
```bash
pytest                         # Run all tests (~320+ cases)
pytest tests/test_file.py      # Run a specific test file
pytest -xvs                    # Stop on first failure, verbose, no capture
pytest --cov=odoo_doctor       # Coverage report
```

### Code Quality
```bash
ruff check src tests           # Lint
ruff format src tests          # Auto-format
ruff format --check src tests  # Check without applying
```

### CLI Testing
```bash
odoo-doctor scan .             # Scan current directory
odoo-doctor scan . --json      # JSON output
odoo-doctor scan . --min-score 80  # Fail if score < 80
odoo-doctor scan . --diff HEAD --fail-on error  # Changed files only
odoo-doctor rules explain rule-name  # Explain a rule
```

---

## Coding Style & Naming Conventions

- **Python**: Python 3.10–3.13, enforced by Ruff in CI. All files must pass `ruff format` and `ruff check`.
- **Indentation**: 4 spaces (standard Python).
- **Line Length**: 88 characters (Ruff default).
- **Imports**: Organized by stdlib, third-party, local (enforced by Ruff).
- **Naming**: Snake_case for functions/variables, PascalCase for classes. Rule classes inherit from `Rule` base class.
- **Comments**: Minimal and necessary only; prefer self-documenting code.

---

## Testing Guidelines

- **Framework**: pytest (8.0+). Test files in `tests/` with naming pattern `test_*.py`.
- **Coverage**: Aim for high coverage; run `pytest --cov=odoo_doctor` locally before submitting PRs.
- **Test Organization**: Each rule has a corresponding `test_rule_name.py` exercising positive/negative cases.
- **Fixtures**: Use temporary addon directories with manifests and Python/XML stubs. Main test input is `ModuleContext` object.
- **Assertions**: Verify diagnostics are emitted (or not), check confidence/tier, validate message text.

### Run a Single Test
```bash
pytest tests/test_my_rule.py -xvs
```

---

## Adding a New Rule

1. Create `src/odoo_doctor/rules/my_rule.py`:
   ```python
   from odoo_doctor.rules.base import Rule
   from odoo_doctor.core.diagnostics import Diagnostic

   class MyRule(Rule):
       """Brief description."""
       tier = "P1"
       category = "Correctness"
       
       def check(self, addon_context):
           for issue in addon_context.my_method():
               yield Diagnostic(
                   rule=self.name,
                   file=issue.path,
                   line=issue.line,
                   confidence="high",
                   message="..."
               )
   ```

2. Create tests in `tests/test_my_rule.py`.
3. Rule auto-registers via `registry.py` — no manual registration needed.

---

## Commit & Pull Request Guidelines

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):
```
<type>(<scope>): <subject>

<body>
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`  
**Scope**: Optional, e.g., `(rules)`, `(parser)`, `(cli)`  
**Subject**: Lowercase, imperative, no period. ~50 characters.

**Examples**:
```
feat(rules): add raw-sql-string-interpolation rule
fix(parser): handle inherited views correctly
docs(readme): update quick start section
chore(release): bump version to 0.3.1
```

### Pull Requests

1. **Branch**: Use descriptive branch names, e.g., `feat/add-raw-sql-rule`, `fix/parser-inheritance`.
2. **Description**: Include what changed and why. Reference linked issues.
3. **Testing**: Ensure all tests pass locally (`pytest --cov=odoo_doctor`).
4. **Code Quality**: Run `ruff format` and `ruff check` before pushing.
5. **CI/CD**: GitHub Actions runs tests, linting, and coverage checks automatically.

### Cut a New Release

1. Bump the version string in `pyproject.toml`, `src/odoo_doctor/reporters/json_report.py`, `README.md`, `CLAUDE.md`, and `AGENTS.md`.
2. Update the `CHANGELOG.md` with release notes.
3. Commit and merge to `main`.
4. Create and push a new Git tag (e.g., `git tag v0.4.0 && git push origin v0.4.0`).
5. Create a GitHub Release. The `.github/workflows/publish.yml` action will automatically build and publish the wheel to PyPI via Trusted Publishing.

---

## Data Flow & Architecture

The tool follows a **7-stage diagnostic pipeline** (all stages are pure functions):
1. **Normalize**: Load `odoo-doctor.toml` → Config
2. **Discover**: Find addons via `__manifest__.py`
3. **Parse**: Extract Python AST, XML records, CSV, manifests
4. **Index**: Build symbol resolution graph
5. **Analyze**: Run enabled rules → raw diagnostics
6. **Filter**: Apply suppressions, confidence thresholds, path ignores
7. **Score**: Deduct by tier, blend per-category scores → 0–100 overall

**Key Design**: Rules emit `Diagnostic` objects with confidence levels (HIGH/MEDIUM/LOW). Only HIGH confidence findings count toward scoring to minimize false positives.

---

## Inline Suppression

Disable a rule for a specific line:

```python
x = self.env.cr.execute(f"SELECT ...")  # odoo-doctor: disable=raw-sql-string-interpolation
```

```xml
<record id="my_record" model="ir.ui.view">  <!-- odoo-doctor: disable=duplicate-xml-id -->
```

---

## Important Files & Locations

| File/Path | Purpose |
|-----------|---------|
| `src/odoo_doctor/core/pipeline.py` | Main 7-stage pipeline |
| `src/odoo_doctor/rules/` | Rule implementations |
| `src/odoo_doctor/core/config.py` | Config loading & validation |
| `src/odoo_doctor/graph/resolver.py` | Symbol resolution engine |
| `src/odoo_doctor/cli/app.py` | CLI entry point |
| `tests/` | Test suite |
| `CLAUDE.md` | Detailed development guide |

---

## Quick Reference

- **Python Version**: 3.10–3.13
- **Build System**: Hatchling
- **Key Dependencies**: typer, rich, lxml, tomli
- **Exit Codes**: 0 (clean), 1 (findings triggered), 2 (score below threshold), 3 (invalid args/git error)
- **CI/CD**: GitHub Actions on push/PR — runs tests, linting, coverage
- **pre-commit Hook**: Runs `odoo-doctor scan --diff HEAD --fail-on error` on Python/XML files

See `CLAUDE.md` for advanced topics (stubs generation, adapter development, symbol resolution internals).
