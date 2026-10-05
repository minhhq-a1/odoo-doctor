# Changelog

All notable changes to Odoo Doctor are documented here.

---

## [Unreleased]

Theme: trust the findings (golden corpus, taint analysis, fix ROI) and cover
multi-company / multi-currency. Also false-positive fixes found by scanning real
OCA/custom addons (`queue_job`, `purchase_request` and others): 229 -> 188
findings on one such repo.

### Added

- **Taint analysis for the Security rules** (`rules/_taint.py`). Values are
  classified SAFE (provably constant), UNKNOWN (opaque, e.g. a parameter) or
  UNSAFE (a string built from non-constant parts) and followed through local
  variables, lists (`append`/`extend`/`+=`), `if`/`try`/loop branches (worst case
  wins) and module-level constants.
  - `raw-sql-string-interpolation` no longer reports SQL built only from
    constants, `int()` casts, `self._table`, `SQL(...)` or
    `','.join(['%s'] * n)` placeholder lists, and now reports dynamic fragments
    that reach `execute()` through a `join()` over a list or through one branch
    of an `if`/`else` (previously missed).
  - `eval-usage` no longer reports `eval(expr)` when `expr` is bound only to
    constants.
  - Behaviour change: interpolating a variable that was bound to a string
    constant is no longer reported (it cannot be injected); a parameter still is.
- **Multi-company / multi-currency rules** (native rules: 30 -> 33):
  - `monetary-missing-currency-field` (Correctness, P1, high): a `fields.Monetary`
    whose currency field (`currency_id` or `currency_field=`) provably does not
    exist on the model, following `_inherit`/`_inherits` and extensions in other
    scanned modules. Models extending an upstream model are skipped.
  - `missing-multicompany-rule` (Security, P1, medium): a model defined in the
    addon with a `company_id` to `res.company` that no `ir.rule` in the scanned
    modules protects.
  - `hardcoded-company-or-currency` (Correctness, P2, medium):
    `env.ref('base.main_company')` / `env.ref('base.USD')` in business code
    (install hooks, `migrations/` and `tests/` are skipped).
  - The parser now records `currency_field` on Monetary fields and the resolver
    can tell whether any scanned module declares an `ir.rule` for a model.
- **Fix ROI ranking** (`core/roi.py`). Each module's score-eligible findings are
  ranked by marginal score gain per effort (greedy on the unclamped
  `0.4 x min + 0.6 x avg` blend, so the weakest category is attacked first).
  Terminal: a *Fix first* list per module. JSON: `modules.<name>.fix_priorities`
  (top 10: `rank`, `rule`, `file_path`, `line`, `tier`, `impact`, `effort`, `roi`,
  `projected_score`, `score_gain`, `fixable`). `EFFORT_BY_RULE` holds a 1-3 effort
  per native rule (a test enforces an entry for every rule).
- **Golden corpus** (`tests/corpus/`, `tests/test_golden_corpus.py`): sample addons
  scanned end to end and compared with a frozen list of findings, so both true
  positives and previously fixed false positives are regression-guarded.
  Refresh with `UPDATE_GOLDEN=1 pytest tests/test_golden_corpus.py`.

### Fixed

- **`missing-xml-ref`** no longer flags the implicit `model_<model_name>` XML IDs
  Odoo generates for every model (e.g. `ref="model_my_model"` in `ir.rule` and
  report actions).
- **`manifest-missing-dependency`** follows `depends` transitively through every
  manifest it has seen (scanned addons and `odoo_source_path`). When the chain
  passes through a module with an unknown manifest, the finding is medium
  confidence instead of high, so it no longer affects the score.
- **`view-field-not-in-model` / `button-method-not-found`** resolve fields and
  methods inherited through `_inherit` + a new `_name` (and `_inherits`).
- **`missing-ondelete`** skips required `Many2one` fields (Odoo defaults them to
  `restrict`).
- **`search-in-loop`** no longer flags `browse()`, which does not query the
  database.
- **Performance rules** (`search-in-loop`, `create-in-loop`, `write-in-loop`,
  `n-plus-one-read`, `unbounded-search`) skip files inside an addon's `tests/`
  directory.
- **`manifest-data-order-risk`**: a data file named like a view/action/menu is no
  longer treated as a security file just because it lives in `security/`.
- **`data-noupdate-risk`**: `ir.rule` records are reported with medium confidence
  (not scored). Core and OCA disagree on `noupdate` for rules, so neither is a
  defect; `ir.config_parameter` and `ir.cron` stay high confidence.
- **`raw-sql-string-interpolation`** honours pylint-odoo's
  `# pylint: disable=sql-injection` marker (trailing comment: that line; own-line
  comment: the rest of the enclosing function), so explicitly vetted dynamic
  `WHERE` fragments are no longer reported.
- **`manifest-missing-required-fields`** no longer requires `installable` (Odoo
  defaults it to `True`) and no longer requires `data` when the manifest declares
  `assets` or `demo`. `odoo-doctor fix` no longer inserts `installable`.

---

## [0.5.0] — 2026-10-03

Theme: close the proposal backlog and make findings explainable and trackable
without adding a hosted service.

### Added

- **Rules documentation from one source.** `src/odoo_doctor/rules/rule_docs.py`
  feeds `odoo-doctor rules explain` (now with description, why, fix and
  before/after examples), the generated `docs/rules.md`, SARIF `helpUri` and
  `Diagnostic.url`. New `odoo-doctor rules docs [--out FILE] [--format
  markdown|html] [--check]`; a test fails when `docs/rules.md` is stale.
- **Deep links.** Native findings carry a link to their rule docs, shown in the
  terminal, GitHub annotations, the PR comment and SARIF.
- **`rules disable|enable <rule>`** edit `[ignore] rules` in `odoo-doctor.toml`
  (comments and other keys untouched); `rules list` marks disabled rules.
- **Rule `expensive-nonstored-compute`** (Performance, P2, medium confidence).
  Native rules: 29 -> 30.
- **Score history** (`scan --history FILE`), **trend and regression detection**
  (`history show --max-drop N`, exit 2) and **legacy ingestion** (`history import`)
  that normalizes pre-0.4.0 reports lacking `score_schema_version` as schema 1.
  Scores of different schema versions are never compared. See
  `docs/score-history.md`.
- **Score badge** (`scan --badge FILE`): SVG or shields.io endpoint JSON, generated
  locally.
- **Plugin API v1 (GA).** Stable `odoo_doctor.plugin_api`; `@rule` validates
  category/tier/severity/confidence; duplicate names are rejected so plugins can't
  override built-ins; a failing plugin is rolled back; `ODOO_DOCTOR_PLUGIN_API`
  version check; `[plugins].allow` allowlist. `docs/custom-rules.md` rewritten.

### Changed

- **Default CI policy:** `--fail-on` now only counts findings admitted by
  `[surfaces.ci_failure]`, which defaults to **P0/P1 at high confidence**. P2/P3 and
  low-confidence findings are still reported but no longer fail the build. To keep
  the old behavior set `[surfaces.ci_failure] tiers = []` and `min_confidence = "low"`.
  New `tiers` key for every surface.
- `__version__` is now the single version source (it was stale at 0.1.0) and the
  JSON report reads it. `SCORE_SCHEMA_VERSION` and `project_score()` live in
  `core.scoring`.
- `rule()` registration is stricter: invalid metadata or a duplicate rule name
  raises `ValueError`.

### Roadmap decisions (explicit close-or-defer)

Closed in 0.5.0: advisory mode, `--fail-on`, multi-module scoring, `--module`,
`--odoo-version`, `rules list/disable`, `[severity]`/`[ignore]` config, version
detection from the installed `odoo` package, CI policy, `expensive-nonstored-compute`,
plugin API GA, rules docs, score history/badge.

Deferred, with owner version:

| Item | Target | Reason |
|------|--------|--------|
| Multi-company / multi-currency rules | 0.6.0 | needs model-level heuristics and fixtures; rule quality pass |
| LSP server + VS Code extension | 0.6.0 | new stack (pygls + TypeScript); builds on the fixer engine and rule docs links |
| Hosted remote score service, auth, server-side trends | 0.7.0 (needs a product decision) | serverless history/badge covers the trend use case first |
| Odoo in-app reporting module | 0.7.0 (depends on the remote service decision) | separate codebase per Odoo version |
| Split monorepo into `core`/`cli`/`rules`/`api` | not scheduled | high churn for users, no feature gain until `api` exists |
| Plugin marketplace/registry | not scheduled | plugin API only just reached GA; naming convention `odoo-doctor-rules-*` documented |
| OCA standards cross-check | not scheduled | scope undefined |

---

## [0.4.0] — 2026-06-28

### Added

- **5 new native rules** across 3 new categories:
  - **Data Integrity**: `missing-ondelete` (P1) — flags Many2one fields without explicit `ondelete`; `data-noupdate-risk` (P2) — flags critical model records (ir.rule, ir.config_parameter, ir.cron) not wrapped in `noupdate="1"`.
  - **Upgrade Safety**: `deprecated-api-usage` (P1) — detects old-API patterns (`from openerp`, `_columns`, `osv.osv`, `.pool`); `removed-model-still-referenced` (P1) — flags `_inherit` references to models not found in project or stubs.
  - **Frontend**: `asset-bundle-missing` (P2) — detects asset files listed in manifest `assets` dict that don't exist on disk (Odoo 15.0+).
- **Default Category Weights**: Scoring now applies sensible default weights per category (Security/Correctness: 1.5, Performance/Data Integrity/Upgrade Safety: 1.0, Module Hygiene: 0.8, Maintainability/Frontend: 0.5). User config overrides merge with defaults.
- **Score Schema Version**: JSON output now includes `score_schema_version: 2` for downstream tooling compatibility.
- **Parser Enhancements**: `FieldInfo` now tracks `ondelete` keyword; `XmlIdInfo` now tracks `noupdate` context from ancestor XML elements.
- **Manifest Assets Parsing**: `ManifestData` now parses the `assets` dict from `__manifest__.py` for frontend rule support.

### Changed

- Total native rules: 24 → 29. Active categories: 5 → 8.
- Version bumped to 0.4.0.

---

## [0.3.0] — 2026-06-12

### Added

- **Auto-Fix Engine**: Built `FixResult` for deterministic file modifications. Wired `--fix` and `--fix-dry-run` to safely apply non-destructive automated changes (e.g., missing manifest fields, data ordering).
- **Scanner Extraction & Caching**: Extracted orchestration logic to `core/scanner.py`. Introduced project-level `ScanCache` (`--cache`) based on content-hash fingerprinting to skip clean files and drastically speed up scans.
- **SARIF Reporter**: Developed `SARIF 2.1.0` output formatter (`--format sarif`) enabling native GitHub Code Scanning and advanced IDE integration.
- **Baseline Filtering**: Implemented a line-independent identity hash system (`--baseline` and `--write-baseline`) to freeze existing technical debt and only fail the CI on net-new issues.
- **Ecosystem Plugins**: Shipped an entry-point system allowing third-party Python packages to inject custom rules via the `odoo_doctor.rules` group. Gated by explicit `[plugins].enabled = true` config for security.
- **9 new native rules**: Spanning Security, Performance, and Correctness: `create-in-loop`, `write-in-loop`, `eval-usage`, `orphan-view`, `record-rule-without-domain`, `field-no-string-on-required`, `missing-translation`, `n-plus-one-read`, `sudo-without-comment`.

### Fixed

- **AST Heuristics**: Improved `receiver_is_orm` helper to accurately track loop variables originating from ORM records (`for rec in self: rec.write()`), fixing false negatives in loop-based rules.
- Odoo version detection regex adjusted to strictly match standard Odoo manifest formats (e.g., `17.0.1.0.0`).

---

## [0.2.0] — 2026-06-08

### Added

- **Capability Gates**: Gating mechanism to run rules only if version and capabilities criteria are met. Gating is evaluated before execution in CLI (preventing crashes/improving performance) and also filtered defensively in the pipeline. Supports `capabilities` configuration in `odoo-doctor.toml`.
- **LOCAL_NOT_FOUND Resolver State**: Explicit representation of local-scope missing symbols. Treat proven local absence as high confidence and score-impacting, eliminating ad-hoc rule-level logic.
- **Aggregated Dependency Inference**: Expanded `manifest-missing-dependency` to scan XML references, eval ref attributes, and inherited views. Diagnostics are aggregated by missing dependency module, presenting multiple evidence items in a single report.
- **eval="ref(...)" Parsing**: XML parser extracts referenced IDs within `eval` attributes using a conservative regex, enabling XML ref and missing dependency checks.
- **odoo_source_path Indexing**: Lightweight indexer (`build_source_index`) scans configured Odoo source addons for model ownership and XML IDs, resolving them without importing Odoo.
- **5 new native rules:** public-controller-sudo-risk (Security/P1), unbounded-search (Performance/P2), manifest-data-order-risk (Module Hygiene/P2), override-missing-super (Correctness/P1), compute-missing-depends (Correctness/P2). Registry now 15 native rules.
- **CI/PR surfaces:** `--format {terminal,json,github}` (GitHub Actions annotations); opt-in `--score-delta <base-ref>` (worktree-isolated base scan, aggregate delta); sticky idempotent PR comment via `gh`; composite `action.yml`; `[surfaces.pr_comment]` / `[surfaces.ci_failure]` config (min_confidence + categories).
- pylint-odoo D7 mapping: E8103=sql-injection (Security/P0) added; E8102=invalid-commit re-tiered to P2.

### Fixed

- `missing-xml-ref` now reports missing local/current-module XML references, including view `inherit_id` refs.
- `--diff` now preserves module context diagnostics when any file in that module changed, preventing missed findings such as missing ACLs after adding a model.
- `--fail-on` now treats the selected severity as a threshold, so `--fail-on warning` also fails on errors.
- Deduplication key now includes `rule` to ensure different rules reporting at the same location are not erroneously merged.
- Crash safety (Part B): non-UTF-8 source files, null adapter JSON fields, and non-zero adapter subprocess exits no longer abort a scan or fake a clean module.
- Part C correctness: `--diff` typos / unresolvable refs fail loudly (exit 3); `--min-score` out of 0–100 rejected (exit 3).
- Overall score rounded to 1 decimal so the terminal report and the `--min-score` gate agree.

### Changed

- `schema_version` remains `1.0` — the JSON shape is unchanged; 0.2.0 adds findings and render surfaces, not new payload fields.
- `oca` adapter key dropped from the `init` template (tolerated-but-inert if present in existing configs).

---

## [0.1.0] — 2026-06-03

### Added

**Core pipeline**
- `Diagnostic` dataclass — shared contract for all findings (frozen, typed)
- 7-stage pipeline: dedup → severity-override → ignore-filter → inline-suppression → version-gate → score-eligibility
- Scoring engine: `0.4 × min(category) + 0.6 × avg(category)` blend with per-category weights
- Config loader from `odoo-doctor.toml` (tomllib / tomli)

**Discovery & graph**
- Addon discovery from `__manifest__.py`
- Odoo version detection from manifest version string
- Manifest parser (ast.literal_eval)
- Python AST parser: `_name`, `_inherit`, `_fields`, methods, controllers
- XML/view parser: record IDs, field refs, button refs, inline suppression comments
- Security CSV parser: `ir.model.access.csv`
- `ModuleContext` + `ProjectGraph` builder with shared `SymbolResolver`
- Confidence-aware resolver: repo → stubs → UNKNOWN (no false positives)
- Bundled stubs for **17.0**, **18.0**, **19.0**
- `build_stubs.py`: generate stubs from Odoo source (AST) or live instance (XML-RPC)

**Rules (10 native)**
- `raw-sql-string-interpolation` — P0, Security
- `missing-access-csv` — P0, Security
- `unknown-model-in-access-csv` — P1, Correctness (UNKNOWN→finding only for current-module models)
- `duplicate-xml-id` — P1, Correctness
- `view-field-not-in-model` — P1, Correctness
- `button-method-not-found` — P1, Correctness
- `missing-xml-ref` — P1, Correctness
- `manifest-missing-dependency` — P1, Module Hygiene
- `manifest-missing-required-fields` — P2, Module Hygiene
- `search-in-loop` — P1, Performance
- Inline suppression scanner (`# odoo-doctor: disable=<rule>` in Python and XML)

**Adapters**
- Ruff adapter with `rule_mapping.toml`
- Pylint-Odoo adapter with `rule_mapping.toml`

**CLI** (`odoo-doctor`)
- `scan PATH` — scan addons, terminal or `--json` output
  - `--odoo-version` — override detected version
  - `--module` — scan only one module
  - `--diff BRANCH` — only findings on changed files (absolute-path resolved from git root)
  - `--fail-on error|warning` — exit 1 if severity found
  - `--min-score N` — exit 2 if any module scores below N (CLI flag overrides config)
- `rules list` — list all registered rules
- `rules explain <name>` — show rule metadata
- `init` — create `odoo-doctor.toml`
- `install` — copy SKILL.md files to `.odoo-doctor/skills/`

**Agent skills**
- `skills/odoo-doctor/SKILL.md` — scan & fix workflow
- `skills/odoo-doctor-explain/SKILL.md` — explain & configure workflow

### Fixed
- Resolver now checks extended fields from `_inherit` extensions (fixes false positives on `view-field-not-in-model` for custom fields on Odoo models)
- XML view parser: `_extract_arch_refs` no longer includes the `<field name="arch">` element itself as a field reference
- `unknown-model-in-access-csv`: UNKNOWN resolution upgraded to high-confidence finding when the CSV's external ID belongs to the current module
- `--diff`: paths resolved from git worktree root; absolute path comparison instead of fragile `endswith()`

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/).  
Breaking changes to the JSON output schema or CLI exit codes will be documented here.
