# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Odoo Doctor** is a static analysis and health-scoring CLI for custom Odoo addons. It runs 37 native rules (8 categories: Security, Correctness, Performance, Module Hygiene, Maintainability, Data Integrity, Upgrade Safety, Frontend), optionally merges Ruff / Pylint-Odoo findings, and produces a 0–100 score per addon. It never imports Odoo — everything is AST/XML/CSV parsing plus packaged model stubs.

`AGENTS.md` is a parallel contributor guide that duplicates much of this file; keep the two in sync when changing shared facts (version, rule counts, structure).

## Commands

```bash
pip install -e ".[dev]" && pip install "ruff>=0.16,<0.17"   # setup (ruff is not in the dev extra but CI needs it)

pytest                                          # all tests
pytest tests/rules/test_eval_usage.py -xvs      # one file, stop on first failure, no capture
pytest tests/path.py::TestClass::test_method    # one test
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest         # what CI runs

ruff check src tests && ruff format --check src tests   # both must pass in CI (ruff format to fix)
```

**Golden corpus** (`tests/corpus/`, run by `tests/test_golden_corpus.py`): each directory is a tiny sample addon scanned end to end through the CLI and compared with its `expected.json` (`[rule, file, confidence]` per finding). It guards true positives *and* known false positives. When a rule change is intentional, review the diff then refresh with `UPDATE_GOLDEN=1 pytest tests/test_golden_corpus.py`. When a real scan shows a false positive, reduce it to a corpus case first. The corpus is excluded from pytest collection (`tests/conftest.py`) and from ruff (`pyproject.toml`) because it holds scan inputs, not tests.

CI (`.github/workflows/ci.yml`) runs pytest + ruff on Python 3.10–3.12; the package supports 3.10–3.13. Ruff runs its 0.16 default rule set; CI pins `ruff>=0.16,<0.17` so a new minor cannot change what is enforced (bump it together with fixing the findings), and the few deliberate ignores live in `pyproject.toml`. The side-effect imports that register rules (`cli/app.py`, `reporters/json_report.py`) sit in `isort: off` blocks: registration order is import order and decides the order of `rules list` and of findings at the same location (`tests/test_registration_order.py`).

Useful CLI invocations while developing (entry point `odoo-doctor = odoo_doctor.cli.app:app`, Typer):

```bash
odoo-doctor scan tests/fixtures/bad_addon --json       # fixtures: sample_addon (clean), bad_addon
odoo-doctor scan . --diff HEAD --fail-on error         # only changed files
odoo-doctor scan . --cache | --baseline F | --write-baseline F | --history h.jsonl --badge b.svg
odoo-doctor fix . [--fix-dry-run]                      # deterministic auto-fixes
odoo-doctor rules list | explain <rule> | disable <rule> | enable <rule>
odoo-doctor rules docs --out docs/rules.md [--check]   # regenerate rules reference
odoo-doctor rules stats [--path DIR] [--cache] [--json]   # which rules users suppress most
odoo-doctor lsp                                        # language server on stdio (needs the `lsp` extra, included in `dev`)
odoo-doctor history show h.jsonl --max-drop 3          # regression gate (exit 2)
```

Exit codes: `0` clean, `1` findings at/above `--fail-on`, `2` score below `--min-score` (or history regression), `3` invalid args / git failure.

## Architecture

Two phases: **scanner** (I/O, parsing, rule execution) then **pipeline** (pure transformations), then scoring.

```
odoo-doctor scan .
 Scanner (core/scanner.py, entry point collect_scores())
  1. Load odoo-doctor.toml (searched upward ≤20 levels, child merged over parent) → Config + capabilities
  2. Discover addons (any dir with __manifest__.py), detect Odoo version
  3. build_project_graph() — parse Python AST, XML, CSV, manifests into per-addon ModuleContext + symbol resolver
  4. Run native rules: context-based (func(ctx)) then file-based (func(file, module, version))
  5. Run external adapters (Ruff, Pylint-Odoo) → Diagnostics
  6. Collect inline suppressions
 Pipeline (core/pipeline.py) — 7 pure stages, in order:
  Normalize paths → Deduplicate (module,file,line,category,rule) → Severity overrides → Ignore filters
  → Inline suppressions → Version/capability gates → Score eligibility
 Scoring (core/scoring.py) — tier deductions per category, blended
```

Key concepts that span files:

- **`Diagnostic`** (`core/diagnostics.py`) is the one frozen dataclass every rule, adapter, reporter, baseline and cache speaks. Tier impact: P0=25, P1=10, P2=4, P3=1.
- **Confidence-aware scoring**: only HIGH-confidence findings are marked score-eligible. Overall score = `0.4 × min(categories) + 0.6 × avg(categories)`; per-category weights come from `[category_weights]`.
- **Rule registration is by import side effect.** `@rule(...)` (in `rules/registry.py`) adds to `default_registry` when the module is imported, and the import list lives in `cli/app.py` (plus `rules.manifest.fixers`). A new rule file that isn't imported there silently never runs; tests that need all rules `import odoo_doctor.cli.app`.
- **Gates**: rules declare `min_version` and capabilities (`enterprise`, `owl`, `odoo:17`…); the pipeline drops them when unmet.
- **Suppression**: `odoo-doctor: disable=rule-name` in Python/XML comments; line 0 is the sentinel for file-wide suppression.
- **Fixers** (`core/fixer.py`, e.g. `rules/manifest/fixers.py`): `(diagnostic, file_text) -> new_text | None`, must be deterministic and idempotent; rule must be `fixable=True`.
- **Baseline** (`core/baseline.py`) identifies findings by rule + module + path + line snippet. **Cache** (`core/cache.py`) is all-or-nothing, keyed on a fingerprint of every scanned file, config, version, ruleset and tool version.
- **CI failure policy** lives in `core/surfaces.py` (`[surfaces.ci_failure]`, default P0/P1 high-confidence) and is applied to `--fail-on`; the same module filters PR-comment surfaces.
- **Plugins**: third-party rules load via `entry_points` (`rules/plugins.py`, only when `[plugins] enabled = true`, with `allow` list/version check/rollback). `src/odoo_doctor/plugin_api.py` is the *only* stable import surface for plugins — don't break it.
- **Symbol resolution** (`graph/resolver.py`) answers "does this model/field/XML ID exist, and where" using parsed addons, optional `odoo_source_path` (`graph/source_index.py`) and packaged stubs in `graph/stubs/data/{17.0,18.0,19.0}.json` (loader tries exact version, then major).
- **Rule docs** are generated: `rules/rule_docs.py` (`RULE_DOCS`) is the single source for `docs/rules.md`, HTML, `rules explain` and SARIF `helpUri`.
- **Taint analysis** (`rules/_taint.py`): `TaintVisitor` tracks SAFE/UNKNOWN/UNSAFE states per variable (lists, branches, module constants) for the Security rules; subclass it and implement `check_call` (see `eval_usage.py`, `raw_sql_interpolation.py`).
- **Fix ROI** (`core/roi.py`): `rank_fixes` orders a module's score-eligible findings by marginal score gain per effort and fills `ScoreResult.fix_priorities` (via `scanner._score_module`, used by both the live and cached paths). Add an `EFFORT_BY_RULE` entry (1-3) for every new native rule — a test fails otherwise.
- **Suppression analytics** (`core/suppression_stats.py`): `pipeline.run_pipeline_with_stats` counts findings dropped by inline `disable`, `[ignore] rules` and `[severity] = "off"` (first channel wins; `files/modules` and baseline are not counted). Counts live on `ScoreResult.suppression_stats` and in the scan cache (`CACHE_VERSION` 2) because they cannot be recomputed from post-pipeline findings. `--diff` scans collect none.
- **Language server** (`src/odoo_doctor/lsp/`, experimental, see `docs/lsp.md`): `odoo-doctor lsp` serves LSP over stdio with pygls 2.x (optional extra `lsp`). `convert.py`, `actions.py` and `engine.py` are pure (no server state) and unit-tested; `server.py` is the pygls glue. A scan covers the whole workspace folder (`engine.scan_project`) on startup, on save and on `odooDoctor.rescan`, one at a time on a worker thread. Stdout carries the protocol, so nothing in a scan may print to stdout. The VS Code extension lives in `editors/vscode/` (TypeScript: `npm ci && npm run compile`; `npm run package` builds a `.vsix`). It is published on the VS Code Marketplace as `MinhHong.odoo-doctor` (preview); that identity is pinned by `tests/test_vscode_extension.py`, and each release must publish the matching version (see Releasing).
- `skills/*/SKILL.md` are the agent skills installed by `odoo-doctor install`.

## Adding a Rule

1. `src/odoo_doctor/rules/<category>/my_rule.py` using `@rule(name=..., category=..., tier="P0".."P3", severity=..., default_confidence=..., needs_context=True, min_version=None, fixable=False)`; yield `Diagnostic(...)` (see an existing rule such as `rules/security/eval_usage.py` for the field set). Shared AST helpers: `rules/_ast_helpers.py`.
2. Test in `tests/rules/` — build a temp addon, assemble a `ModuleContext`, assert on emitted diagnostics (positive and negative cases). Shared fixture addons are in `tests/fixtures/`.
3. Add the import to `cli/app.py`, a `RuleDoc` entry to `rules/rule_docs.py` and an effort to `core/roi.py::EFFORT_BY_RULE`, then `odoo-doctor rules docs --out docs/rules.md`.

**Never hand-edit `docs/rules.md`.** `tests/test_rule_docs_complete.py` fails if any rule lacks a `RULE_DOCS` entry, a `RULE_DOCS` entry is stale, or the page isn't regenerated. A single `@rule` function can register several names (`create_write_in_loop.py` registers both `create-in-loop` and `write-in-loop`).

## Releasing

1. Bump the version in `pyproject.toml`, `src/odoo_doctor/__init__.py` (read by the JSON report), `README.md` (including the `minhhq-a1/odoo-doctor@vX.Y.Z` action example), `CLAUDE.md` and `AGENTS.md`, plus both `version` fields of `editors/vscode/package.json` and `package-lock.json`. `tests/test_version.py` enforces pyproject == `__version__` and that `CHANGELOG.md` has a `## [X.Y.Z]` entry; `tests/test_vscode_extension.py` enforces the extension version; the README/CLAUDE/AGENTS bumps are not tested.
2. Update `CHANGELOG.md`; regenerate `docs/rules.md` if rules changed.
3. Merge to `main`, then `git tag vX.Y.Z && git push origin vX.Y.Z` and create a GitHub Release — `.github/workflows/publish.yml` publishes to PyPI via Trusted Publishing.
4. VS Code extension (not automated, needs the publisher's token): after the PyPI release, publish the same version from `main` with `cd editors/vscode && npm ci && npx vsce publish`, or upload the `.vsix` that `npm run package` builds at https://marketplace.visualstudio.com/manage/publishers/MinhHong. Never put the token in the repo or in chat.

Current version: `0.7.0`.

## Configuration

`odoo-doctor.toml` (generate with `odoo-doctor init`). Sections: `[odoo-doctor]` (`odoo_version` or `"auto"`, `addons_paths`, `odoo_source_path`, `capabilities`), `[plugins]` (`enabled`, `allow`), `[adapters]` (`ruff`, `pylint_odoo`), `[severity]` (per-rule override, `"off"` disables), `[ignore]` (`rules`, `files` globs, `modules`), `[category_weights]`, `[surfaces.pr_comment]` / `[surfaces.ci_failure]`. `rules disable/enable` edit `[ignore] rules` in place, preserving comments (`core/config_edit.py`). Config validation is in `core/config.py`.

## Further Reading

`docs/custom-rules.md` (plugin / `@rule` contract), `docs/stubs.md` (generating stubs for a new Odoo version via `python -m odoo_doctor.graph.stubs.build_stubs source|rpc`), `docs/score-history.md`, `CONTRIBUTING.md`.
