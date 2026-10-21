# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Odoo Doctor** is a static analysis and health-scoring CLI for custom Odoo addons. It runs 55 native rules (8 categories: Security, Correctness, Performance, Module Hygiene, Maintainability, Data Integrity, Upgrade Safety, Frontend), optionally merges Ruff / Pylint-Odoo findings, and produces a 0–100 score per addon. It never imports Odoo — everything is AST/XML/CSV parsing plus packaged model stubs.

`AGENTS.md` is a parallel contributor guide that duplicates much of this file; keep the two in sync when changing shared facts (version, rule counts, structure).

## Commands

```bash
pip install -e ".[dev]" && pip install "ruff>=0.16,<0.17"   # setup (ruff is not in the dev extra but CI needs it)

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -p xdist -n auto   # what CI runs (parallel; drop the flags to run serially)

ruff check src tests && ruff format --check src tests   # both must pass in CI (ruff format to fix)
```

**Golden corpus** (`tests/corpus/`, run by `tests/test_golden_corpus.py`): each directory is a tiny sample addon scanned end to end through the CLI and compared with its `expected.json` (`[rule, file, confidence]` per finding). It guards true positives *and* known false positives. When a rule change is intentional, review the diff then refresh with `UPDATE_GOLDEN=1 pytest tests/test_golden_corpus.py`. When a real scan shows a false positive, reduce it to a corpus case first. The corpus is excluded from pytest collection (`tests/conftest.py`) and from ruff (`pyproject.toml`) because it holds scan inputs, not tests.

CI (`.github/workflows/ci.yml`) runs pytest + ruff on Python 3.10–3.13; the package supports 3.10–3.13. Ruff runs its 0.16 default rule set; CI pins `ruff>=0.16,<0.17` so a new minor cannot change what is enforced (bump it together with fixing the findings), and the few deliberate ignores live in `pyproject.toml`. The side-effect imports that register rules (`cli/app.py`, `reporters/json_report.py`) sit in `isort: off` blocks: registration order is import order and decides the order of `rules list` and of findings at the same location (`tests/test_registration_order.py`).

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
  Normalize paths → Deduplicate (module,file,line,category,rule,title) → Severity overrides → Ignore filters
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
- **Baseline** (`core/baseline.py`) v3 identifies findings by rule + module + scan-root-relative path + line snippet + title; v1/v2 absolute-path identities are still read. **Cache** (`core/cache.py`, `adapters/cache.py`) is all-or-nothing, keyed on scanned files (one `scandir` walk that skips the tooling directories in `core/source.py::SKIP_DIRS`, which every scan walker skips too, and every read guarded like the scan's), effective config, linter executables, ruff/pylint/pylint-odoo versions (the scanned repo's ruff/pylint configuration is not an input: both linters run isolated from it), rule-plugin identity (distribution version + source hash), configured Odoo source, ruleset and tool version; the entry also stores each module's Odoo version, suppression stats and line counts, so a hit reproduces the live result exactly (`tests/cli/test_cache_equality.py`); rule plugins loaded with `[plugins] enabled` bypass it.
- **CI failure policy** lives in `core/surfaces.py` (`[surfaces.ci_failure]`, default P0/P1 high-confidence) and is applied to `--fail-on`; the same module filters PR-comment surfaces.
- **Plugins**: third-party rules load via `entry_points` (`rules/plugins.py`, only when `[plugins] enabled = true`, with `allow` list/version check/rollback). `src/odoo_doctor/plugin_api.py` is the *only* stable import surface for plugins — don't break it.
- **Symbol resolution** (`graph/resolver.py`) answers "does this model/field/XML ID exist, and where" using parsed addons, optional `odoo_source_path` (`graph/source_index.py`) and packaged stubs in `graph/stubs/data/{17.0,18.0,19.0}.json` (loader tries exact version, then major).
- **Rule docs** are generated: `rules/rule_docs.py` (`RULE_DOCS`) is the single source for `docs/rules.md`, HTML, `rules explain` and SARIF `helpUri`.
- **Taint analysis** (`rules/_taint.py`): `TaintVisitor` tracks SAFE/UNKNOWN/UNSAFE states per variable (lists, branches, module constants) for the Security rules; subclass it and implement `check_call` (see `eval_usage.py`, `raw_sql_interpolation.py`).
- **Fix ROI** (`core/roi.py`): `rank_fixes` orders a module's score-eligible findings by marginal score gain per effort and fills `ScoreResult.fix_priorities` (via `scanner._score_module`, used by both the live and cached paths). Add an `EFFORT_BY_RULE` entry (1-3) for every new native rule — a test fails otherwise.
- **Upgrade readiness report** (`core/upgrade.py`, `docs/upgrade-report.md`): `scan --upgrade-report` (with `--odoo-version <target>`) groups the Upgrade Safety findings by kind of change via a static table, labels each mechanical or needs review (only `high` findings can be mechanical) and scores each module 0-100. Pure functions over the scan's diagnostics; adds the top-level `upgrade_report` JSON key only with the flag (`readiness_schema_version` 1, in `docs/stability.md`).
- **Suppression analytics** (`core/suppression_stats.py`): `pipeline.run_pipeline_with_stats` counts findings dropped by inline `disable`, `[ignore] rules` and `[severity] = "off"` (first channel wins; `files/modules` and baseline are not counted). Counts live on `ScoreResult.suppression_stats` and in the scan cache (`core/cache.py`, also stores Python line counts and module versions) because they cannot be recomputed from post-pipeline findings. `--diff` scans collect none.
- **HTML report** (`reporters/html_report.py`, assets in `reporters/html/`): `scan --html` embeds the `build_payload()` dict (the `--json` content) plus a small envelope into one self-contained file. Everything from the scanned repo is untrusted: JSON is escaped for a `<script>` element (`embed_json`), `report.js` only uses `textContent`/`createElement` (a test forbids `innerHTML` and friends), and a CSP meta pins the inline script and style by hash. Over 10 MiB it drops `low` findings from a copy. Tests: `tests/reporters/test_html_report*.py` (the Node smoke test skips without `node`).
- **Language server** (`src/odoo_doctor/lsp/`, experimental, see `docs/lsp.md`): `odoo-doctor lsp` serves LSP over stdio with pygls 2.x (optional extra `lsp`). `convert.py`, `actions.py` and `hover.py` are pure (no server state) and unit-tested; `server.py` is the pygls glue. A scan covers the whole workspace folder (`engine.scan_project`) on startup, on save (debounced) and on `odooDoctor.rescan`, one at a time on a worker thread; `engine.py` keeps a `core/reuse.py::ScanReuse` per folder (whole result, native file rules per file, Ruff/Pylint per addon, source index) so a save only redoes what changed, with results equal to a scan from scratch as far as `tests/test_scan_reuse.py` backs it (`ODOO_DOCTOR_LSP_REUSE=0` disables). A file is told apart by size + mtime + ctime + inode (plus a content hash for files written in the last 2 s); whole-result reuse is skipped whenever a plugin rule is registered; `odooDoctor.rescan` forgets the kept state first (the clean-scan escape hatch) and `forget` never waits for a running scan. Stdout carries the protocol, so nothing in a scan may print to stdout. The VS Code extension lives in `editors/vscode/` (TypeScript: `npm ci && npm run compile`; `npm run package` builds a `.vsix`). It is published on the VS Code Marketplace as `MinhHong.odoo-doctor` (preview); that identity is pinned by `tests/test_vscode_extension.py`, and each release must publish the matching version (see Releasing).
- **Git**: every git call goes through `core/git.py::run_git` (hardened config and environment); never call `subprocess.run(["git", ...])` directly.
- **Repo-derived text**: every string that comes from the scanned repo (file, module, version names, git's stderr) and goes into a log, stderr or stdout line goes through `core/text.py::safe_text`; never interpolate such names raw.
- **Precision tooling**: `scripts/measure.py` is the maintainer's per-rule precision tool (manual, not shipped, not in CI). The terminal surface is `[surfaces.terminal]` (default `min_confidence = "medium"` hides `low`); `scan --show-low` shows everything and changes nothing else (JSON/SARIF/HTML/`--fail-on`/scores).
- `skills/*/SKILL.md` are the agent skills installed by `odoo-doctor install`.
- `ci-templates/` holds the GitLab CI and Bitbucket Pipelines templates (the same POSIX `sh` script in both; the GitHub one is `action.yml`). `tests/test_ci_templates.py` checks the YAML, that every flag exists on `scan`, and executes the script in a temp git repo with a real `origin`. Keep the two scripts identical apart from the target-branch variable.

## Adding a Rule

1. `src/odoo_doctor/rules/<category>/my_rule.py` using `@rule(name=..., category=..., tier="P0".."P3", severity=..., default_confidence=..., needs_context=True, min_version=None, fixable=False)`; yield `Diagnostic(...)` (see an existing rule such as `rules/security/eval_usage.py` for the field set). Shared AST helpers: `rules/_ast_helpers.py`.
2. Test in `tests/rules/` — build a temp addon, assemble a `ModuleContext`, assert on emitted diagnostics (positive and negative cases). Shared fixture addons are in `tests/fixtures/`.
3. Add the import to `cli/app.py`, a `RuleDoc` entry to `rules/rule_docs.py` and an effort to `core/roi.py::EFFORT_BY_RULE`, then `odoo-doctor rules docs --out docs/rules.md`.

A rule's confidence is decided by whether its pattern fires on Odoo core 19: a pattern that Odoo's own addons use is at most `medium`, and `high` needs a true positive with evidence and a positive golden-corpus case (see the Changed notes of the CHANGELOG).

**Never hand-edit `docs/rules.md`.** `tests/test_rule_docs_complete.py` fails if any rule lacks a `RULE_DOCS` entry, a `RULE_DOCS` entry is stale, or the page isn't regenerated. A single `@rule` function can register several names (`create_write_in_loop.py` registers both `create-in-loop` and `write-in-loop`).

## Releasing

Follow the `release` skill (`.claude/skills/release/SKILL.md`). Never put the VS Code Marketplace publisher token in the repo or in chat.

Current version: `0.11.2`.

## Further Reading

`docs/custom-rules.md` (plugin / `@rule` contract), `docs/stubs.md` (generating stubs for a new Odoo version via `python -m odoo_doctor.graph.stubs.build_stubs source|rpc`), `docs/score-history.md`, `docs/stability.md` (public surface and exit codes, fenced by `tests/test_stability_contract.py`), `docs/support.md` (Python/Odoo matrix, support policy), `docs/performance.md` (reference scan timings), `CONTRIBUTING.md`.
