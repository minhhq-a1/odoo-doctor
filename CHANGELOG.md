# Changelog

All notable changes to Odoo Doctor are documented here.

---

## [0.3.0] — 2026-06-12

### Added

- **Auto-Fix Engine**: Built `FixResult` for deterministic file modifications. Wired `--fix` and `--fix-dry-run` to safely apply non-destructive automated changes (e.g., missing manifest fields, data ordering).
- **Scanner Extraction & Caching**: Extracted orchestration logic to `core/scanner.py`. Introduced project-level `ScanCache` (`--cache`) based on content-hash fingerprinting to skip clean files and drastically speed up scans.
- **SARIF Reporter**: Developed `SARIF 2.1.0` output formatter (`--format sarif`) enabling native GitHub Code Scanning and advanced IDE integration.
- **Baseline Filtering**: Implemented a line-independent identity hash system (`--baseline` and `--write-baseline`) to freeze existing technical debt and only fail the CI on net-new issues.
- **Ecosystem Plugins**: Shipped an entry-point system allowing third-party Python packages to inject custom rules via the `odoo_doctor.rules` group. Gated by explicit `[plugins].enabled = true` config for security.
- **10 new native rules**: Spanning Security, Performance, and Correctness: `create-in-loop`, `write-in-loop`, `eval-usage`, `orphan-view`, `record-rule-without-domain`, `field-no-string-on-required`, `missing-translation`, `n-plus-one-read`, `sudo-without-comment`, `unsafe-template-render` (flags unescaped QWeb `t-raw` output as an XSS risk).

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
