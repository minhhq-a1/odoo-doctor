# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Odoo Doctor** is a unified static analysis and health-scoring tool for custom Odoo addons. It detects security vulnerabilities, broken views, duplicate XML IDs, missing dependencies, performance issues, and integrates with external linters (Ruff, Pylint-Odoo) to produce a single 0–100 health score per addon.

Key features:
- 29 native static analysis rules across 8 categories (Security, Correctness, Performance, Module Hygiene, Maintainability, Data Integrity, Upgrade Safety, Frontend)
- Confidence-aware scoring (only HIGH confidence findings count toward scores)
- Per-category scoring blended into an overall score: `0.4 × min(categories) + 0.6 × avg(categories)`
- Config-driven rule filtering via `odoo-doctor.toml`
- External adapter support (Ruff, Pylint-Odoo, custom)
- Plugin system for third-party rules
- Auto-fix support via `odoo-doctor fix`
- Baseline mode for suppressing pre-existing findings
- Incremental scan caching for unchanged modules
- GitHub Actions integration, pre-commit support, AI agent-friendly JSON output

## Development Commands

### Setup & Installation
```bash
pip install -e ".[dev]"        # Install in editable mode with dev dependencies
pip install ruff               # Code formatter/linter (required for CI)
```

### Testing
```bash
pytest                         # Run all tests (~72 test files, 414 cases)
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
odoo-doctor scan . --cache     # Use cached results for unchanged modules
odoo-doctor scan . --baseline .odoo-doctor-baseline.json  # Suppress known findings
odoo-doctor scan . --write-baseline baseline.json  # Save findings as baseline
odoo-doctor fix .              # Apply deterministic fixes
odoo-doctor fix . --fix-dry-run  # Preview fixes as unified diff
odoo-doctor rules list         # List all rules
odoo-doctor rules explain rule-name  # Explain a specific rule
odoo-doctor init               # Generate odoo-doctor.toml
odoo-doctor install            # Install agent skills
```

## Architecture

The tool uses a **two-phase architecture**: a **scanner** (`core/scanner.py`) handles discovery, parsing, indexing, and rule execution; a **pipeline** (`core/pipeline.py`) handles post-processing via 7 pure transformation stages.

### Core Components

**`core/` — Pipeline, Scanning & Scoring**
- `scanner.py`: Scan orchestration — builds the project graph, runs native rules (context-based and file-based), runs external adapters, collects suppressions, then invokes the pipeline. Entry point: `collect_scores()`.
- `pipeline.py`: Seven-stage post-processing pipeline (pure transformations). Stages: Normalize → Deduplicate → Severity Overrides → Ignore Filters → Inline Suppressions → Version/Capability Gates → Score Eligibility.
- `config.py`: Config loader (`odoo-doctor.toml`) with defaults, validation, capability derivation, and hierarchical config merging (child overrides parent).
- `scoring.py`: Confidence/tier-based deduction scoring and per-category blending. Score labels: Excellent (≥90), Good (≥75), Needs work (≥50), Critical (<50).
- `diagnostics.py`: `Diagnostic` frozen dataclass (14 fields: module, file_path, line, column, rule, category, severity, tier, source, confidence, title, message, help, odoo_version, url). Defines `CATEGORIES` list and `TIER_IMPACT` map (P0=25, P1=10, P2=4, P3=1).
- `fixer.py`: Fixer registry and driver for `odoo-doctor fix`. Fixers are `(diagnostic, file_text) -> new_text | None` callables. Must be deterministic and idempotent.
- `baseline.py`: Baseline mode — stores finding identities (rule + module + path + line snippet) as JSON, suppresses pre-existing findings on subsequent scans.
- `cache.py`: Project-level incremental scan cache. All-or-nothing invalidation keyed by a fingerprint of all scanned files, config, version, ruleset, and tool version.
- `surfaces.py`: Output formatting configuration for GitHub Actions annotations and PR comments.
- `source.py`: Source code reading and encoding handling.

**`rules/` — Rule Engine (29 rules)**

Rules are organized into category subdirectories:
- `registry.py`: `@rule()` decorator and `RuleRegistry` class. Rules auto-register on import.
- `suppression.py`: Inline suppression scanner for Python and XML (`odoo-doctor: disable=rule-name`).
- `plugins.py`: Third-party plugin discovery via `entry_points`.
- `_ast_helpers.py`: Shared AST utilities for rule implementations.
- `security/` (7 rules): `eval_usage`, `missing_access_csv`, `raw_sql_interpolation`, `public_controller_sudo`, `record_rule_without_domain`, `sudo_without_comment`, `unknown_model_in_access_csv`
- `correctness/` (4 rules): `compute_missing_depends`, `field_no_string_on_required`, `missing_translation`, `override_missing_super`
- `performance/` (5 rules): `create_write_in_loop` (registers both `create-in-loop` and `write-in-loop`), `n_plus_one_read`, `search_in_loop`, `unbounded_search`
- `xml/` (5 rules): `button_method_not_found`, `duplicate_xml_id`, `missing_xml_ref`, `orphan_view`, `view_field_not_in_model`
- `manifest/` (3 rules + fixers): `data_order_risk`, `missing_dependency`, `missing_required_fields`, plus `fixers.py` for auto-fix support
- `data_integrity/` (2 rules): `missing_ondelete`, `data_noupdate_risk`
- `upgrade_safety/` (2 rules): `deprecated_api_usage`, `removed_model_still_referenced`
- `frontend/` (1 rule): `asset_bundle_missing`

**`parsers/` — Code Parsing**
- `python_models.py`: AST-based Python parser — extracts `_name`, `_inherit`, methods, ORM calls, SQL patterns, field definitions, decorators.
- `xml_records.py`: XML record parser — extracts model names, field names, button methods, XML IDs, refs, eval expressions.
- `manifest.py`: Manifest (`__manifest__.py`) parser — extracts metadata, dependencies, data files.
- `security_csv.py`: CSV parser for `ir.model.access.csv` — model ACLs.

**`graph/` — Symbol Resolution**
- `resolver.py`: Symbol resolution engine — tracks which module/model/field/XML ID exists, where it's defined, what it inherits from.
- `module_context.py`: Per-addon context object gathering all parsed data (manifest, Python files, XML records, CSV rows, inherited views). `build_project_graph()` is the entry point.
- `source_index.py`: Optional indexing of Odoo source code via `odoo_source_path` — enables cross-repo model/XML ID lookups without importing Odoo.
- `stubs/`: Packaged model/field/XML ID stubs for Odoo versions.
  - `loader.py`: Loads stub JSON by version (tries exact match, then major version).
  - `build_stubs.py`: Generates stubs from source checkout or live RPC instance.
  - `data/`: Pre-built stubs for versions 17.0, 18.0, 19.0.

**`discovery/` — Addon Discovery**
- `addons.py`: Scans filesystem for addon folders (by `__manifest__.py` presence).
- `odoo_version.py`: Detects Odoo version from manifest, requirements, config, or file heuristics.

**`adapters/` — External Tool Integration**
- `base.py`: Abstract base adapter class.
- `ruff/adapter.py`: Ruff linter integration — converts Ruff findings to Diagnostic objects.
- `pylint_odoo/adapter.py`: Pylint-Odoo integration — converts Pylint-Odoo findings to Diagnostic objects.

**`reporters/` — Output Formatting**
- `terminal.py`: Rich-formatted terminal table output.
- `json_report.py`: JSON output with findings, scores, and tool version.
- `github_annotations.py`: GitHub Actions check annotations format.
- `sarif.py`: SARIF (Static Analysis Results Interchange Format) output.
- `pr_comment.py`: GitHub PR comment formatting.

**`cli/app.py`** — CLI entry point using Typer. Commands: `scan`, `fix`, `rules` (subcommands: `list`, `explain`), `init`, `install`.

**`skills/`** — Agent-friendly SKILL.md documentation for AI coding assistants.
- `odoo-doctor/SKILL.md`: Scan & fix skill.
- `odoo-doctor-explain/SKILL.md`: Explain & configure skill.

### Data Flow

```
odoo-doctor scan .
  ── Scanner Phase (scanner.py) ──
  1. Load odoo-doctor.toml → Config + Capabilities
  2. Discover addons via __manifest__.py
  3. Build project graph (parse Python AST, XML, CSV, manifests)
  4. Run native rules (context-based, then file-based) → raw diagnostics
  5. Run external adapters (Ruff, Pylint-Odoo) → additional diagnostics
  6. Collect inline suppression comments

  ── Pipeline Phase (pipeline.py) ──
  7. [Normalize] Normalize file paths to POSIX
  8. [Deduplicate] Group by (module, file, line, category, rule), keep best
  9. [Severity Overrides] Apply config-driven severity changes
  10. [Ignore Filters] Remove by rule name, file glob, module name
  11. [Inline Suppressions] Remove suppressed findings
  12. [Version/Capability Gates] Filter by Odoo version and capabilities
  13. [Score Eligibility] Mark HIGH-confidence findings as scoring-eligible

  ── Scoring Phase (scoring.py) ──
  14. Deduct points by tier per category, blend into overall 0–100 score
  → Output (terminal/JSON/GitHub/SARIF)
```

### Key Design Patterns

1. **Scanner + Pipeline Separation**: Scanner handles I/O and rule execution; pipeline is pure transformations testable in isolation.
2. **Confidence-Aware**: Rules emit HIGH/MEDIUM/LOW confidence findings; only HIGH counts toward scoring to avoid false positives.
3. **Capability Gates**: Rules can require certain Odoo versions or addon capabilities (`enterprise`, `owl`, `odoo:17`, etc.) — disabled at runtime if not met.
4. **Adapter Pattern**: External linters (Ruff, Pylint-Odoo) plug in as subclasses of the base adapter, yielding Diagnostic objects with consistent metadata.
5. **Suppression**: Inline `odoo-doctor: disable=rule-name` comments in Python/XML bypass specific findings per line. Line 0 is a sentinel for file-wide suppression.
6. **Fixer Pattern**: Rules can be marked `fixable=True`; corresponding fixers registered in `FixerRegistry` are `(diagnostic, text) -> new_text | None` — deterministic and idempotent.
7. **Baseline Mode**: First run saves finding identities as JSON; subsequent runs suppress matching findings, reporting only new issues.
8. **Incremental Cache**: All-or-nothing cache keyed by a fingerprint of every input — any change invalidates the whole cache for correctness.

## Testing Patterns

- Test files are in `tests/` organized into subdirectories mirroring `src/`: `tests/rules/`, `tests/core/`, `tests/parsers/`, `tests/cli/`, `tests/graph/`, `tests/discovery/`, `tests/adapters/`, `tests/reporters/`, `tests/integration/`.
- 69 test files with 384 test methods.
- Each rule has a corresponding test file exercising positive/negative cases.
- Fixtures use temporary addon directories with manifests and Python/XML stubs.
- The `ModuleContext` object is the main test input — assembled from parsed files, then rules are run against it.
- Common assertions: check that specific diagnostics are (or aren't) emitted, verify confidence/tier, validate message text.
- Integration tests in `tests/integration/` cover end-to-end scanning and crash safety.

## Configuration

Create `odoo-doctor.toml` at repo root (or run `odoo-doctor init`):

```toml
[odoo-doctor]
odoo_version = "17.0"              # or "auto" to detect
addons_paths = ["."]               # where to scan for addons
odoo_source_path = "/path/to/odoo" # optional, enables cross-repo lookups
capabilities = ["enterprise", "owl"]
enable_plugins = false             # enable third-party rule plugins

[adapters]
ruff = true                        # enable Ruff integration
pylint_odoo = false

[severity]
"search-in-loop" = "warning"       # override rule severity ("off" to disable)

[ignore]
rules = []                         # disable specific rules
files = ["**/migrations/**"]        # ignore paths (glob patterns)
modules = []                       # ignore addons by name

[category_weights]
Security = 1.5                     # weight category differently (default 1.0)

[surfaces.pr_comment]
min_confidence = "all"
categories = []
```

Config files are searched upward from the scan directory (max 20 levels), with child configs merged over parent configs.

## Common Tasks

### Add a New Rule

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
       needs_context=True,          # True: func(ctx) | False: func(file, module, version)
       min_version=None,            # e.g. "14.0" to gate by version
       fixable=False,               # True if a fixer exists
   )
   def check_my_rule(ctx):
       # ctx: ModuleContext with parsed files
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
Generated JSON lands in `src/odoo_doctor/graph/stubs/data/<version>.json`. Pre-built stubs exist for 17.0, 18.0, and 19.0.

## CI/CD Integration

- **GitHub Actions CI**: `.github/workflows/ci.yml` — runs on push/PR to `main`. Matrix: Python 3.10, 3.11, 3.12. Steps: install deps, pytest, ruff check, ruff format check.
- **PyPI Publishing**: `.github/workflows/publish.yml` — triggers on GitHub Release. Uses Trusted Publishing (OIDC) to publish wheel to PyPI.
- **GitHub Action**: `action.yml` at repo root — published as `minhhq-a1/odoo-doctor@v0.3.0`. Inputs: `odoo-version`, `fail-on`, `min-score`, `paths`, `diff-base`, `advisory`, `pr-comment`.
- **Example workflow**: `.github/workflows/odoo-doctor.example.yml` demonstrates usage of the published action.
- **pre-commit**: Hook defined in `.pre-commit-hooks.yaml` runs `odoo-doctor scan --diff HEAD --fail-on error` on Python/XML files.
- **Exit Codes**: `0` = clean, `1` = findings at severity threshold, `2` = score below min, `3` = invalid args/git failure.

## Important Files & Locations

| File/Path | Purpose |
|-----------|---------|
| `src/odoo_doctor/core/scanner.py` | Scan orchestration (discovery → rules → pipeline) |
| `src/odoo_doctor/core/pipeline.py` | 7-stage post-processing pipeline |
| `src/odoo_doctor/core/scoring.py` | Score computation and category blending |
| `src/odoo_doctor/core/config.py` | Config loading & validation |
| `src/odoo_doctor/core/diagnostics.py` | Diagnostic dataclass, categories, tier impacts |
| `src/odoo_doctor/core/fixer.py` | Fixer registry for `odoo-doctor fix` |
| `src/odoo_doctor/core/baseline.py` | Baseline mode finding identity & suppression |
| `src/odoo_doctor/core/cache.py` | Incremental scan cache |
| `src/odoo_doctor/rules/` | Rule implementations (29 rules in 8 category dirs) |
| `src/odoo_doctor/rules/registry.py` | `@rule()` decorator and `RuleRegistry` |
| `src/odoo_doctor/graph/resolver.py` | Symbol resolution engine |
| `src/odoo_doctor/graph/module_context.py` | Per-addon context + `build_project_graph()` |
| `src/odoo_doctor/cli/app.py` | CLI entry point (scan, fix, rules, init, install) |
| `tests/` | Test suite (69 files, 384 test cases) |
| `action.yml` | GitHub Actions marketplace action definition |
| `odoo-doctor.toml` | User configuration (created via `odoo-doctor init`) |
| `docs/rules.md` | Rule documentation |
| `docs/custom-rules.md` | Custom rule / plugin documentation |
| `docs/stubs.md` | Stub generation documentation |

## Development Notes

- **Python Version**: Supports 3.10–3.13 (see `pyproject.toml`). CI tests 3.10–3.12.
- **Dependencies**: Minimal — `typer>=0.12`, `rich>=13.0`, `lxml>=5.0`, `tomli>=2.0` (Python < 3.11 only).
- **Dev Dependencies**: `pytest>=8.0`, `pytest-cov>=5.0`, `pyyaml>=6.0`.
- **Build System**: Hatchling. Stub JSON data files are included in wheels via `hatch.build`.
- **Code Style**: Ruff enforced in CI — all files must pass `ruff format` and `ruff check`.
- **Pre-commit**: Hook runs `odoo-doctor scan --diff HEAD --fail-on error` to catch issues early.
- **Version**: Current version is `0.4.0`. Appears in `pyproject.toml` and `reporters/json_report.py`.
