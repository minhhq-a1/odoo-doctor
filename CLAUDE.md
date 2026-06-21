# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Odoo Doctor** is a unified static analysis and health-scoring tool for custom Odoo addons. It detects security vulnerabilities, broken views, duplicate XML IDs, missing dependencies, performance issues, and integrates with external linters (Ruff, Pylint-Odoo) to produce a single 0–100 health score per addon.

Key features:
- 15 native static analysis rules across 5 categories (Security, Correctness, Performance, Module Hygiene, Maintainability)
- Confidence-aware scoring (only HIGH confidence findings count toward scores)
- Per-category scoring blended into an overall score: `0.4 × min(categories) + 0.6 × avg(categories)`
- Config-driven rule filtering via `odoo-doctor.toml`
- External adapter support (Ruff, Pylint-Odoo, custom)
- GitHub Actions integration, pre-commit support, AI agent-friendly JSON output

## Development Commands

### Setup & Installation
```bash
pip install -e ".[dev]"        # Install in editable mode with dev dependencies
pip install ruff               # Code formatter/linter (required for CI)
```

### Testing
```bash
pytest                         # Run all tests (~46 test files, 320+ cases)
pytest tests/test_file.py      # Run a specific test file
pytest tests/test_file.py::TestClass::test_method  # Run a specific test
pytest --cov=odoo_doctor      # Coverage report
pytest -xvs                    # Stop on first failure, verbose, no capture
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest  # CI-mode (disables pytest plugins)
```

### Code Quality
```bash
ruff check src tests           # Lint (format violations, imports, etc.)
ruff format src tests          # Auto-format code
ruff format --check src tests  # Check formatting without applying
```

### CLI Testing
```bash
odoo-doctor scan .             # Scan current directory
odoo-doctor scan . --json      # JSON output for integration
odoo-doctor scan . --min-score 80  # Fail if score < 80
odoo-doctor scan . --diff HEAD --fail-on error  # Scan only changed files
odoo-doctor rules explain rule-name  # Explain a specific rule
odoo-doctor init               # Generate odoo-doctor.toml
```

## Architecture

The tool follows a **7-stage diagnostic pipeline** that transforms addon code into scored findings. Each stage is a pure function (no side effects) defined in `core/pipeline.py`. Stages flow: Normalize → Discover → Parse → Index → Analyze → Filter → Score.

### Core Components

**`core/` — Pipeline & Scoring**
- `pipeline.py`: The seven-stage pipeline orchestrating the entire analysis flow. Stages include version detection, addon discovery, file parsing, source indexing, rule execution, filtering, and scoring.
- `config.py`: Config loader (`odoo-doctor.toml`) with defaults, validation, and capability derivation.
- `scoring.py`: Confidence/tier-based deduction scoring and per-category blending.
- `diagnostics.py`: `Diagnostic` dataclass (finding metadata: rule, file, line, confidence, tier, message).
- `surfaces.py`: Output formatting — GitHub Actions annotations, PR comments, CLI tables.

**`rules/` — Rule Engine**
- `registry.py`: Rule metadata registration, rule loading by tier/category/confidence.
- `base.py`: Abstract `Rule` base class with common patterns (dependency tracking, symbol resolution).
- Individual rule files: Each rule inherits from `Rule`, implements `check()` method (receives parsed addon context, yields diagnostics).

**`parsers/` — Code Parsing**
- `python_models.py`: AST-based Python parser — extracts `_name`, `_inherit`, methods, ORM calls, SQL patterns, field definitions, decorators.
- `xml_records.py`: XML record parser — extracts model names, field names, button methods, XML IDs, refs, eval expressions.
- `manifest.py`: Manifest (`__manifest__.py`) parser — extracts metadata, dependencies, data files.
- `security_csv.py`: CSV parser for `ir.model.access.csv` — model ACLs.

**`graph/` — Symbol Resolution**
- `resolver.py`: Symbol resolution engine — tracks which module/model/field/XML ID exists, where it's defined, what it inherits from.
- `module_context.py`: Per-addon context object gathering all parsed data (manifest, Python files, XML records, CSV rows, inherited views).
- `source_index.py`: Optional indexing of Odoo source code via `odoo_source_path` — enables cross-repo model/XML ID lookups without importing Odoo.

**`discovery/` — Addon Discovery**
- `addons.py`: Scans filesystem for addon folders (by `__manifest__.py` presence).
- `odoo_version.py`: Detects Odoo version from manifest, requirements, or config.

**`adapters/` — External Tool Integration**
- `ruff_adapter.py`, `pylint_odoo_adapter.py`: Plug-in architecture for external linters — each yields Diagnostic objects formatted consistently.

**`reporters/` — Output Formatting**
- Output drivers for GitHub Actions, JSON, SARIF, plain text.

**`cli/app.py`** — CLI entry point using Typer, handles `scan`, `init`, `rules explain`, `install` commands.

### Data Flow Example

```
odoo-doctor scan .
  1. [Normalize] Load odoo-doctor.toml → Config + Capabilities
  2. [Discover] Find addons via __manifest__.py
  3. [Parse] Extract Python AST, XML records, CSV, manifests
  4. [Index] Build symbol resolution graph (what exists, where)
  5. [Analyze] Run enabled rules against addon context → raw diagnostics
  6. [Filter] Apply suppressions, min confidence, path ignores
  7. [Score] Deduct points by tier, blend per-category scores → final 0-100
  → Output (GitHub/JSON/table)
```

### Key Design Patterns

1. **Pure Pipeline**: Each stage is testable in isolation without mocking external state.
2. **Confidence-Aware**: Rules emit HIGH/MEDIUM/LOW confidence findings; only HIGH counts toward scoring to avoid false positives.
3. **Capability Gates**: Rules can require certain Odoo versions or addon capabilities (`enterprise`, `owl`, `odoo:17`, etc.) — disabled at runtime if not met.
4. **Adapter Pattern**: External linters (Ruff, Pylint-Odoo) plug in as subclasses that emit Diagnostic objects with consistent metadata.
5. **Suppression**: Inline `odoo-doctor: disable=rule-name` comments in Python/XML bypass specific findings per line.

## Testing Patterns

- Test files are in `tests/` with names matching `test_*.py`.
- Each rule has a corresponding `test_rule_name.py` that exercises positive/negative cases.
- Fixtures use temporary addon directories with manifests and Python/XML stubs.
- The `ModuleContext` object is the main test input — assembled from parsed files, then rules are run against it.
- Common assertions: check that specific diagnostics are (or aren't) emitted, verify confidence/tier, validate message text.

## Configuration

Create `odoo-doctor.toml` at repo root (or run `odoo-doctor init`):

```toml
[odoo-doctor]
odoo_version = "17.0"              # or "auto" to detect
addons_paths = ["."]               # where to scan for addons
odoo_source_path = "/path/to/odoo" # optional, enables cross-repo lookups
capabilities = ["enterprise", "owl"]

[adapters]
ruff = true                        # enable Ruff integration
pylint_odoo = false

[severity]
"search-in-loop" = "warning"       # override rule severity

[ignore]
rules = []                         # disable specific rules
files = ["**/migrations/**"]        # ignore paths
modules = []                       # ignore addons by name

[category_weights]
Security = 1.5                     # weight category differently (default 1.0)

[surfaces.pr_comment]
min_confidence = "all"
categories = []
```

## Common Tasks

### Add a New Rule

1. Create `src/odoo_doctor/rules/my_rule.py` implementing `Rule` base class:
   ```python
   from odoo_doctor.rules.base import Rule
   from odoo_doctor.core.diagnostics import Diagnostic

   class MyRule(Rule):
       """Brief description."""
       
       tier = "P1"
       category = "Correctness"
       
       def check(self, addon_context):
           # addon_context: ModuleContext with parsed files
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
3. Rule auto-registers via `registry.py` (no manual registration needed).

### Cut a New Release

1. Bump the version string in `pyproject.toml`, `src/odoo_doctor/reporters/json_report.py`, `README.md`, `CLAUDE.md`, and `AGENTS.md`.
2. Update the `CHANGELOG.md` with release notes.
3. Commit and merge to `main`.
4. Create and push a new Git tag (e.g., `git tag v0.4.0 && git push origin v0.4.0`).
5. Create a GitHub Release. The `.github/workflows/publish.yml` action will automatically build and publish the wheel to PyPI via Trusted Publishing.

### Run a Single Test

```bash
pytest tests/test_rule_name.py -xvs
```

### Debug a Rule

Add `print()` statements or use a debugger:
```bash
python -m pdb -m pytest tests/test_rule.py::TestRule::test_case
```

### Generate Stubs for a New Odoo Version

```bash
# From source checkout
python -m odoo_doctor.graph.stubs.build_stubs source \
  --odoo-path /path/to/odoo \
  --version 18.0

# From live instance
python -m odoo_doctor.graph.stubs.build_stubs rpc \
  --rpc-url http://localhost:8069 \
  --rpc-db mydb \
  --rpc-password admin \
  --version 18.0
```
Generated JSON lands in `src/odoo_doctor/graph/stubs/data/<version>.json`.

## CI/CD Integration

- **GitHub Actions**: Use `.github/workflows/odoo-doctor.example.yml` or the published action `minhhq-a1/odoo-doctor@v0.3.1`.
- **pre-commit**: Hook defined in `.pre-commit-hooks.yaml` runs `odoo-doctor scan --diff HEAD --fail-on error` on Python/XML files.
- **Exit Codes**: `0` = clean, `1` = findings at severity threshold, `2` = score below min, `3` = invalid args/git failure.

## Important Files & Locations

| File/Path | Purpose |
|-----------|---------|
| `src/odoo_doctor/core/pipeline.py` | Main 7-stage pipeline orchestration |
| `src/odoo_doctor/rules/` | Rule implementations |
| `src/odoo_doctor/core/config.py` | Config loading & validation |
| `src/odoo_doctor/graph/resolver.py` | Symbol resolution engine |
| `src/odoo_doctor/cli/app.py` | CLI entry point |
| `tests/` | Test suite (~320+ test cases) |
| `odoo-doctor.toml` | User configuration (created via `odoo-doctor init`) |
| `docs/rules.md` | Rule documentation |

## Development Notes

- **Python Version**: Supports 3.10–3.13 (see `pyproject.toml`).
- **Dependencies**: Minimal — `typer`, `rich`, `lxml`, `tomli` (for Python < 3.11).
- **Build System**: Hatchling. Stub JSON data files are included in wheels via `hatch.build`.
- **Code Style**: Ruff enforced in CI — all files must pass `ruff format` and `ruff check`.
- **Pre-commit**: Hook runs `odoo-doctor scan --diff HEAD --fail-on error` to catch issues early.
