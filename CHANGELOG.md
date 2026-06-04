# Changelog

All notable changes to Odoo Doctor are documented here.

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
