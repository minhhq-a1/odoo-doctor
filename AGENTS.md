# Repository Guidelines

## Project Overview

**Odoo Doctor** is a unified static analysis and health-scoring tool for custom Odoo addons. It detects security vulnerabilities, broken views, duplicate XML IDs, missing dependencies, and performance issues across 29 native rules, integrated with external linters (Ruff, Pylint-Odoo) to produce a single 0–100 health score per addon.

---

## Project Structure

```
odoo-doctor/
├── src/odoo_doctor/          # Main source code
│   ├── core/                 # Scanner, pipeline (7-stage), config, scoring, fixer, baseline, cache
│   ├── rules/                # Rule implementations (P0–P3 tiers, organized by category)
│   │   ├── security/         # 7 rules (eval, SQL injection, sudo, access control)
│   │   ├── correctness/      # 4 rules (missing depends, super, translations)
│   │   ├── performance/      # 5 rules (loops, N+1, unbounded search)
│   │   ├── xml/              # 5 rules (broken refs, duplicate IDs, orphan views)
│   │   ├── manifest/         # 3 rules + fixers (dependencies, data order, required fields)
│   │   ├── data_integrity/  # 2 rules (missing ondelete, noupdate risk)
│   │   ├── upgrade_safety/  # 2 rules (deprecated API, removed model reference)
│   │   └── frontend/        # 1 rule (asset bundle missing)
│   ├── parsers/              # Python AST, XML record, manifest, CSV parsing
│   ├── graph/                # Symbol resolution engine + version stubs (17.0, 18.0, 19.0)
│   ├── discovery/            # Addon discovery & Odoo version detection
│   ├── adapters/             # External linter integration (Ruff, Pylint-Odoo)
│   ├── reporters/            # Output formatting (terminal, JSON, GitHub, SARIF, PR comment)
│   ├── cli/                  # CLI entry point (Typer)
│   └── skills/               # Agent-friendly SKILL.md documentation
├── tests/                    # 414 test cases (~72 test files)
├── docs/                     # Rule, custom-rules, and stubs documentation
├── pyproject.toml            # Build & dependency config
├── action.yml                # GitHub Actions marketplace action
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
pytest                         # Run all tests (~384 cases)
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
odoo-doctor scan . --cache     # Incremental cached scan
odoo-doctor fix .              # Apply deterministic fixes
odoo-doctor fix . --fix-dry-run  # Preview fixes as unified diff
odoo-doctor rules list         # List all rules
odoo-doctor rules explain rule-name  # Explain a rule
```

---

## Coding Style & Naming Conventions

- **Python**: Python 3.10–3.13, enforced by Ruff in CI. All files must pass `ruff format` and `ruff check`.
- **Indentation**: 4 spaces (standard Python).
- **Line Length**: 88 characters (Ruff default).
- **Imports**: Organized by stdlib, third-party, local (enforced by Ruff).
- **Naming**: Snake_case for functions/variables, PascalCase for classes. Rule functions use the `@rule()` decorator.
- **Comments**: Minimal and necessary only; prefer self-documenting code.

---

## Testing Guidelines

- **Framework**: pytest (8.0+). Test files in `tests/` with naming pattern `test_*.py`.
- **Coverage**: Aim for high coverage; run `pytest --cov=odoo_doctor` locally before submitting PRs.
- **Test Organization**: Tests mirror source structure (`tests/rules/`, `tests/core/`, `tests/parsers/`, `tests/cli/`, `tests/graph/`, `tests/discovery/`, `tests/adapters/`, `tests/reporters/`, `tests/integration/`).
- **Fixtures**: Use temporary addon directories with manifests and Python/XML stubs. Main test input is `ModuleContext` object.
- **Assertions**: Verify diagnostics are emitted (or not), check confidence/tier, validate message text.

### Run a Single Test
```bash
pytest tests/test_my_rule.py -xvs
```

---

## Adding a New Rule

1. Create `src/odoo_doctor/rules/<category>/my_rule.py`:
   ```python
   from odoo_doctor.rules.registry import rule
   from odoo_doctor.core.diagnostics import Diagnostic

   @rule(
       name="my-rule-name",
       category="Correctness",
       tier="P1",
       severity="error",
       default_confidence="high",
       needs_context=True,
   )
   def check_my_rule(ctx):
       for issue in ctx.some_method():
           yield Diagnostic(
               module=ctx.name,
               file_path=str(issue.path),
               line=issue.line,
               column=0,
               rule="my-rule-name",
               category="Correctness",
               severity="error",
               tier="P1",
               source="native",
               confidence="high",
               title="Short title",
               message="Detailed explanation",
               help="How to fix it",
               odoo_version=ctx.odoo_version,
           )
   ```

2. Create tests in `tests/rules/test_my_rule.py`.
3. Rule auto-registers via the `@rule()` decorator — no manual registration needed.

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
chore(release): bump version to 0.3.0
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

The tool uses a **two-phase architecture**:

**Scanner Phase** (`core/scanner.py`):
1. Load `odoo-doctor.toml` → Config
2. Discover addons via `__manifest__.py`
3. Build project graph (parse Python AST, XML, CSV, manifests)
4. Run native rules (context-based + file-based) → raw diagnostics
5. Run external adapters (Ruff, Pylint-Odoo) → additional diagnostics
6. Collect inline suppression comments

**Pipeline Phase** (`core/pipeline.py` — 7 pure transformation stages):
1. **Normalize**: Normalize file paths to POSIX format
2. **Deduplicate**: Group by (module, file, line, category, rule), keep highest confidence
3. **Severity Overrides**: Apply config-driven severity changes (`"off"` removes)
4. **Ignore Filters**: Remove by rule name, file glob, module name
5. **Inline Suppressions**: Remove findings suppressed by inline comments
6. **Version/Capability Gates**: Filter by Odoo version and required/excluded capabilities
7. **Score Eligibility**: Mark HIGH-confidence findings as scoring-eligible

**Key Design**: Rules emit `Diagnostic` objects with confidence levels (HIGH/MEDIUM/LOW). Only HIGH confidence findings count toward scoring to minimize false positives. Tier impacts: P0=25, P1=10, P2=4, P3=1 point deductions.

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
| `src/odoo_doctor/core/scanner.py` | Scan orchestration (discovery → rules → pipeline) |
| `src/odoo_doctor/core/pipeline.py` | 7-stage post-processing pipeline |
| `src/odoo_doctor/core/config.py` | Config loading & validation |
| `src/odoo_doctor/core/diagnostics.py` | Diagnostic dataclass, categories, tier impacts |
| `src/odoo_doctor/rules/` | Rule implementations (24 rules in 5 category dirs) |
| `src/odoo_doctor/graph/resolver.py` | Symbol resolution engine |
| `src/odoo_doctor/cli/app.py` | CLI entry point |
| `tests/` | Test suite (69 files, 384 cases) |
| `CLAUDE.md` | Detailed development guide |

---

## Quick Reference

- **Python Version**: 3.10–3.13
- **Build System**: Hatchling
- **Key Dependencies**: typer, rich, lxml, tomli
- **Exit Codes**: 0 (clean), 1 (findings triggered), 2 (score below threshold), 3 (invalid args/git error)
- **CI/CD**: GitHub Actions on push/PR — runs tests (Python 3.10–3.12), linting, formatting
- **pre-commit Hook**: Runs `odoo-doctor scan --diff HEAD --fail-on error` on Python/XML files

See `CLAUDE.md` for advanced topics (stubs generation, adapter development, fixer implementation, baseline mode, caching).
