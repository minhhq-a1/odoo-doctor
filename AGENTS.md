# Repository Guidelines

## Project Overview

**Odoo Doctor** is a unified static analysis and health-scoring tool for custom Odoo addons. It detects security vulnerabilities, broken views, duplicate XML IDs, missing dependencies, and performance issues across 57 native rules, integrated with external linters (Ruff, Pylint-Odoo) to produce a single 0–100 health score per addon.

---

## Project Structure

```
odoo-doctor/
├── src/odoo_doctor/          # Main source code
│   ├── core/                 # Scanner, pipeline (7-stage), config, scoring, fixer, baseline, cache, history, fix ROI, surfaces
│   ├── rules/                # Rule implementations (P0–P3 tiers, organized by category)
│   │   ├── security/         # 14 rules (eval, SQL injection, sudo, access control, multi-company rules, CSRF, TLS)
│   │   ├── correctness/      # 6 rules (missing depends, super, translations, monetary currency, hardcoded company/currency)
│   │   ├── performance/      # 7 rules (loops, N+1, unbounded search, non-stored computes, HTTP timeouts)
│   │   ├── xml/              # 5 rules (broken refs, duplicate IDs, orphan views)
│   │   ├── manifest/         # 6 rules + fixers (dependencies, data order, required fields, license, external dependencies, vendored code)
│   │   ├── data_integrity/  # 3 rules (missing ondelete, noupdate risk, manual commit)
│   │   ├── upgrade_safety/  # 13 rules (deprecated API, deprecated/removed ORM API, removed model/field, sql-constraints, cron fields, view attrs/states/tree/search-group/kanban/chatter, act-window target)
│   │   └── frontend/        # 1 rule (asset bundle missing)
│   ├── parsers/              # Python AST, XML record, manifest, CSV parsing
│   ├── graph/                # Symbol resolution engine, version stubs and the packaged core index (17.0, 18.0, 19.0)
│   ├── discovery/            # Addon discovery & Odoo version detection
│   ├── adapters/             # External linter integration (Ruff, Pylint-Odoo)
│   ├── reporters/            # Output formatting (terminal, JSON, GitHub, SARIF, PR comment, badge, HTML report)
│   ├── cli/                  # CLI entry point (Typer)
│   ├── lsp/                  # Language server (experimental, optional `lsp` extra)
│   ├── plugin_api.py         # The only stable import surface for third-party rules
│   └── skills/               # Agent-friendly SKILL.md documentation
├── editors/vscode/          # VS Code extension (TypeScript)
├── ci-templates/             # GitLab CI and Bitbucket Pipelines templates
├── tests/                    # pytest suite; `tests/corpus/` is the golden corpus of sample addons
├── docs/                     # Rules (generated), stability contract, support policy, custom rules, stubs, LSP, HTML report, score history, performance
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
pytest                         # Run all tests
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
odoo-doctor fix . --upgrade-to 19.0 --fix-dry-run  # Preview migration fixers (opt-in, >= 18.0)
odoo-doctor rules list         # List all rules
odoo-doctor rules explain rule-name  # Explain a rule
odoo-doctor rules disable rule-name   # Disable a rule in odoo-doctor.toml
odoo-doctor rules docs --out docs/rules.md  # Regenerate rules docs (never hand-edit)
odoo-doctor rules stats [--path DIR] [--json]   # Which rules users suppress most
odoo-doctor rules new <rule-name> [--out DIR]   # Scaffold a third-party rule pack
odoo-doctor lsp                # Language server on stdio (needs the lsp extra)
odoo-doctor scan . --odoo-version 19.0 --upgrade-report   # Upgrade readiness report (docs/upgrade-report.md)
odoo-doctor scan . --history h.jsonl --badge badge.svg
odoo-doctor history show h.jsonl --max-drop 3
odoo-doctor scan . --html report.html   # Self-contained HTML report
```

---

## Coding Style & Naming Conventions

- **Python**: Python 3.10–3.13, enforced by Ruff in CI (0.16 default rule set, pinned `ruff>=0.16,<0.17`). All files must pass `ruff format` and `ruff check`. Do not let isort reorder the rule-registration imports in `cli/app.py` and `reporters/json_report.py` (`isort: off` blocks; `tests/test_registration_order.py` guards the order).
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
3. Import the module in `cli/app.py` (registers the rule), add its `RuleDoc` entry to `rules/rule_docs.py` and an effort (1-3) to `core/roi.py::EFFORT_BY_RULE`, then run `odoo-doctor rules docs --out docs/rules.md`.
4. When a real scan shows a false positive, reduce it to a golden-corpus case under `tests/corpus/` before changing the rule.

A rule's confidence is decided by whether its pattern fires on Odoo core 19: a pattern that Odoo's own addons use is at most `medium`, and `high` needs a true positive with evidence and a positive golden-corpus case (see the Changed notes of the CHANGELOG).

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

1. Bump the version string in `pyproject.toml`, `src/odoo_doctor/__init__.py`, `README.md`, `CLAUDE.md`, and `AGENTS.md`, plus `editors/vscode/package.json` and `package-lock.json` (`tests/test_version.py` and `tests/test_vscode_extension.py` check consistency).
2. Update the `CHANGELOG.md` with release notes.
3. Commit and merge to `main`. The merge is the release: `.github/workflows/release.yml` sees the new version in `pyproject.toml`, checks it, pushes the tag `vX.Y.Z` and starts `.github/workflows/publish.yml`, which runs the tests, checks that the tag equals the package version, smoke-tests the wheel, publishes to PyPI via Trusted Publishing, creates the GitHub Release (notes from `CHANGELOG.md`, `.vsix` attached) and publishes the VS Code extension (`MinhHong.odoo-doctor`) with the `VSCE_PAT` repository secret. Do not tag or create the Release by hand. Without `VSCE_PAT` upload the `.vsix` from the Release at https://marketplace.visualstudio.com/manage/publishers/MinhHong. See `.claude/skills/release/SKILL.md` for re-running a release.

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
2. **Deduplicate**: Group by (module, file, line, category, rule, title), keep highest confidence
3. **Severity Overrides**: Apply config-driven severity changes (`"off"` removes)
4. **Ignore Filters**: Remove by rule name, file glob, module name
5. **Inline Suppressions**: Remove findings suppressed by inline comments
6. **Version/Capability Gates**: Filter by Odoo version and required/excluded capabilities
7. **Score Eligibility**: Mark HIGH-confidence findings as scoring-eligible

**Key Design**: Rules emit `Diagnostic` objects with confidence levels (HIGH/MEDIUM/LOW). Only HIGH confidence findings count toward scoring to minimize false positives. Tier impacts: P0=25, P1=10, P2=4, P3=1 point deductions.

- **HTML report** (`reporters/html_report.py`, assets in `reporters/html/`): `scan --html` embeds the `build_payload()` dict (the `--json` content) plus a small envelope into one self-contained file. Everything from the scanned repo is untrusted: JSON is escaped for a `<script>` element (`embed_json`), `report.js` only uses `textContent`/`createElement` (a test forbids `innerHTML` and friends), and a CSP meta pins the inline script and style by hash. Over 10 MiB it drops `low` findings from a copy. Tests: `tests/reporters/test_html_report*.py` (the Node smoke test skips without `node`).

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
| `src/odoo_doctor/core/git.py` | `run_git`: every git call goes through it (hardened config and environment); never `subprocess.run(["git", ...])` directly |
| `src/odoo_doctor/core/text.py` | `safe_text`: every repo-derived string in a log/stderr/stdout line goes through it; never interpolate file or module names raw |
| `src/odoo_doctor/core/reuse.py` | `ScanReuse`: the language server's per-folder reuse of the previous scan |
| `src/odoo_doctor/core/pipeline.py` | 7-stage post-processing pipeline |
| `src/odoo_doctor/core/scaffold.py` | Starter project for a third-party rule pack (`rules new`); generated rules import only `plugin_api` |
| `src/odoo_doctor/core/upgrade.py` | Upgrade readiness report (`scan --upgrade-report`): groups Upgrade Safety findings by change, mechanical vs needs-review table, readiness score; JSON key `upgrade_report` only with the flag (see `docs/upgrade-report.md`) |
| `src/odoo_doctor/core/suppression_stats.py` | Suppression analytics: per-rule counts of findings users switch off, noise verdict (`rules stats`) |
| `src/odoo_doctor/reporters/html_report.py` | HTML report (`scan --html`), assets in `reporters/html/`; `docs/html-report.md` |
| `src/odoo_doctor/lsp/` | Language server (experimental): `convert`/`actions`/`hover` are pure, `engine.py` keeps per-folder `core/reuse.py` state so a save redoes only what changed (equal to a scan from scratch as far as `tests/test_scan_reuse.py` backs it; file signature size + mtime + ctime + inode, no whole-result reuse when a plugin rule is registered, `odooDoctor.rescan` forgets first), `server.py` is the pygls glue; docs in `docs/lsp.md` |
| `editors/vscode/` | VS Code extension (TypeScript, `npm ci && npm run compile`); its version must match the package |
| `ci-templates/` | GitLab CI and Bitbucket Pipelines templates (same script in both); `tests/test_ci_templates.py` runs it in a temp git repo |
| `src/odoo_doctor/core/config.py` | Config loading & validation |
| `src/odoo_doctor/core/diagnostics.py` | Diagnostic dataclass, categories, tier impacts |
| `src/odoo_doctor/rules/` | Rule implementations (57 rules in 8 category dirs) |
| `src/odoo_doctor/graph/resolver.py` | Symbol resolution engine |
| `src/odoo_doctor/cli/app.py` | CLI entry point |
| `tests/` | Test suite; `tests/corpus/` + `tests/test_golden_corpus.py` is the golden corpus (`UPDATE_GOLDEN=1` refreshes it after an intentional rule change) |
| `scripts/measure.py` | Maintainer per-rule precision tool (manual, not shipped, not in CI) |
| `CLAUDE.md` | Detailed development guide |

---

## Quick Reference

- **Python Version**: 3.10–3.13
- **Build System**: Hatchling
- **Key Dependencies**: typer, rich, lxml, tomli
- **Exit Codes**: 0 (clean), 1 (findings triggered), 2 (score below threshold), 3 (invalid args/git error)
- **Terminal surface**: `[surfaces.terminal]` (default `min_confidence = "medium"` hides `low` findings); `scan --show-low` shows everything and changes nothing else (JSON/SARIF/HTML, `--fail-on` and scores are unchanged)
- **CI/CD**: GitHub Actions on push/PR — runs tests (Python 3.10–3.13), linting, formatting
- **pre-commit Hook**: Runs `odoo-doctor scan --diff HEAD --fail-on error` on Python/XML files

See `CLAUDE.md` for advanced topics (stubs generation, adapter development, fixer implementation, baseline mode, caching).
