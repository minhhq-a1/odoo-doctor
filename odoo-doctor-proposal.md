# Odoo Doctor - Final Strategic Proposal

Inspired by `millionco/react-doctor`, Odoo Doctor is a CLI and CI tool for diagnosing custom Odoo addons. It scans addon repositories, builds an Odoo-aware project graph, reports high-signal diagnostics, and produces a health score that helps developers and coding agents fix the right problems first.

## 1. Product Positioning

Odoo Doctor should not be a generic Python linter. Its value is Odoo-specific cross-file understanding:

```text
Python models define fields and methods.
XML views reference those fields and methods.
CSV files grant access to models.
Manifest files define load order and dependencies.
Data XML references external IDs across module boundaries.
```

The product message:

```text
Your agent writes risky Odoo customizations, this catches them.
```

Primary users:

- Odoo teams reviewing custom addon pull requests.
- Agencies maintaining many customer-specific modules.
- Developers preparing modules for upgrade.
- Coding agents that need deterministic feedback after editing Odoo code.

Core outputs:

- Terminal report with grouped diagnostics.
- JSON report for automation.
- GitHub Actions annotations.
- Sticky pull request summary.
- Local health score from 0 to 100.
- Rule explanations and fix guidance for agents.

## 2. What To Borrow From React Doctor

React Doctor works because it combines a few ideas that are stronger together:

- Focused rules, each catching one concrete bug pattern.
- A single diagnostic pipeline for severity overrides, ignores, suppressions, and output surfaces.
- Different surfaces for local CLI, PR comments, scoring, and CI failure gates.
- Project discovery and capability detection before rules are enabled.
- JSON reports and GitHub Action integration.
- Agent skills that teach coding agents how to triage and fix findings.

Odoo Doctor should keep those ideas, but replace React Doctor's file-linting center with an Odoo graph engine.

## 3. Core Design Decision: Graph-First

The most important decision is that Odoo Doctor should be graph-first, not linter-first.

Pipeline:

```text
discover addons
-> parse manifests
-> build dependency graph
-> parse Python model graph
-> parse XML/data graph
-> parse security CSV graph
-> resolve references
-> run graph-aware rules
-> filter diagnostics
-> score and report
```

This is the main moat. Many valuable Odoo issues cannot be detected reliably by scanning one file at a time:

- A view field exists only if the Python model graph knows that field.
- A button method is valid only if the resolved model has that method.
- A missing `depends` entry is visible only when XML/Python references cross module boundaries.
- Access CSV correctness requires model declarations and generated `model_<model_name>` external IDs.
- XML IDs require module-aware resolution, data load order, and dependency context.

## 4. Recommended Technology

Odoo Doctor should be Python-first.

Recommended stack:

- CLI: `typer` or `click`
- Terminal UI: `rich`
- Python parsing: `libcst` for source-preserving analysis and suppressions
- XML parsing: `lxml`
- Manifest parsing: Python AST plus `ast.literal_eval`, never `eval`
- Config: `odoo-doctor.toml`
- Tests: `pytest`
- Package: PyPI, with `uv`/`pipx` friendly install
- CI: composite GitHub Action

Why Python-first:

- Odoo developers already run Python tooling.
- Odoo manifests and Python model code are first-class inputs.
- PyPI distribution fits Odoo projects better than npm.
- Static Python/XML graph construction is simpler in Python.

TypeScript can still be used later for a website or documentation UI, but not for the core engine.

## 5. Proposed Repository Layout

```text
odoo-doctor/
  src/
    odoo_doctor/
      cli/
        main.py
        commands/
        renderers/
      core/
        diagnostics.py
        pipeline.py
        scoring.py
        config.py
        surfaces.py
      discovery/
        addons.py
        odoo_version.py
      graph/
        project_graph.py
        addon_graph.py
        model_graph.py
        xml_graph.py
        security_graph.py
      parsers/
        manifest.py
        python_models.py
        xml_records.py
        security_csv.py
      rules/
        manifest/
        orm/
        xml/
        security/
        performance/
        upgrade/
      reporters/
        terminal.py
        json_report.py
        github_annotations.py
  skills/
    odoo-doctor/
      SKILL.md
    odoo-doctor-explain/
      SKILL.md
  action.yml
  tests/
    fixtures/
```

If a monorepo is desired later, split `core`, `cli`, `rules`, and `api` into packages. For the MVP, a single Python package is simpler and faster.

## 6. Diagnostic Model

Odoo Doctor diagnostics should preserve module context.

```python
class Diagnostic:
    module: str
    file_path: str
    language: str  # "python" | "xml" | "csv" | "manifest" | "js"
    plugin: str    # "odoo-doctor"
    rule: str
    severity: str  # "error" | "warning"
    category: str
    title: str
    message: str
    help: str
    line: int
    column: int
    tags: list[str]
    odoo_versions: list[str]
    url: str | None
```

Recommended categories:

- Security
- Correctness
- Performance
- Data Integrity
- Upgrade Safety
- Module Hygiene
- Frontend
- Maintainability

These map cleanly to Odoo's real failure modes while staying compatible with scoring and surfaces.

## 7. Config Model

Use `odoo-doctor.toml`:

```toml
odoo_version = "17.0"
addons_paths = ["addons", "custom_addons"]
target_modules = ["sale_custom", "stock_custom"]

[rules]
"security/raw-sql-string-interpolation" = "error"
"performance/search-in-loop" = "warn"
"maintainability/style-only-rule" = "off"

[ignore]
tags = ["style"]
files = ["legacy/**"]

[surfaces.pr_comment]
exclude_tags = ["style", "low-confidence"]

[surfaces.score]
exclude_tags = ["style", "low-confidence"]

[surfaces.ci_failure]
exclude_tags = ["style", "low-confidence"]
```

Configuration principles:

- `rules` changes severity or disables a rule before reporting.
- `ignore.tags` disables whole families.
- `ignore.files` skips known legacy/vendor areas.
- `surfaces` only changes where diagnostics appear.
- CLI flags override config.

Output surfaces:

- `cli`: local terminal, most complete output.
- `pr_comment`: low-noise summary for reviewers.
- `score`: diagnostics counted in health score.
- `ci_failure`: diagnostics allowed to fail the build.

Default: style/low-confidence diagnostics should not affect PR comments, score, or CI failure.

## 8. Version Detection

Odoo version detection must be conservative.

Preferred source:

1. `odoo_version` in `odoo-doctor.toml`
2. CLI flag `--odoo-version`
3. Manifest version prefix if it follows Odoo conventions, for example `17.0.1.0.0`
4. Installed `odoo` Python package metadata, if available
5. Unknown version

Rules should be gated by capabilities:

```text
odoo:14
odoo:15
odoo:16
odoo:17
odoo:18
owl
legacy-web
enterprise
multi-company
```

Do not assume the module manifest version always reveals the target Odoo series. Many real projects use custom version strings.

## 9. MVP Rule Set

The MVP should be narrow and high-signal. It should catch install failures, broken views, security risks, and common ORM performance traps.

### Manifest and Module Graph

- `manifest-missing-required-fields`
  - Missing important manifest keys such as `license`, `depends`, `data`, or `installable`.

- `manifest-missing-dependency`
  - Module references external IDs, models, or inherited views from another addon but does not list that addon in `depends`.

- `manifest-data-order-risk`
  - Security/access files, views, actions, menus, and data files are ordered in a way likely to break module installation.

### Security

- `missing-access-csv`
  - A new persistent model is declared but no access CSV entry grants permissions.

- `unknown-model-in-access-csv`
  - `ir.model.access.csv` references a model external ID that cannot be resolved.

- `raw-sql-string-interpolation`
  - `env.cr.execute()` uses string formatting, f-strings, or concatenation instead of parameters.

- `public-controller-sudo-risk`
  - Public or unauthenticated controller uses `sudo()` or accesses sensitive models without an explicit access check.

### XML and Views

- `duplicate-xml-id`
  - Same XML ID is defined more than once in a module.

- `missing-xml-ref`
  - `ref`, `inherit_id`, menu/action references, or `env.ref()` target cannot be resolved.

- `view-field-not-in-model`
  - XML view references a field that is not known on the resolved model.

- `button-method-not-found`
  - Object button calls a method missing from the resolved model.

### ORM Correctness

- `override-missing-super`
  - Overrides `create`, `write`, `unlink`, or key lifecycle methods without calling `super()`.

- `compute-missing-depends`
  - Compute method reads fields that are not declared in `@api.depends`.

### Performance

- `search-in-loop`
  - ORM `search`, `search_count`, `browse`, `read`, `write`, or `create` is called inside a loop where batching is likely possible.

- `unbounded-search`
  - `search([])` or broad searches without `limit` in risky contexts such as controllers, cron jobs, or compute methods.

This MVP is enough to prove the product because it covers cross-file graph resolution and high-value local AST checks.

## 10. Rules To Defer

Some proposed rules are useful but should not be in the first release.

Defer:

- OWL and JavaScript rules.
- Multi-company and multi-currency rules.
- In-app Odoo reporting module.
- Remote score API.
- IDE integrations.
- Runtime database validation.
- Broad style rules.

Avoid as default MVP rules:

- `missing-string-attribute`
  - Odoo fields often inherit labels from model definitions; this can be noisy.

- `no-hardcoded-xml-id`
  - `env.ref("module.xml_id")` is a normal Odoo pattern. Better rules are missing dependency, missing XML ID, or optional ref without fallback.

- `no-compute-without-store`
  - Non-stored computed fields are valid. A safer future rule would detect expensive non-stored compute fields used in list/search contexts.

- `missing-ondelete`
  - Useful as an upgrade/data-integrity rule, but not high-signal enough for MVP unless scoped tightly to risky models.

## 11. Scoring

Start with deterministic local scoring. Add a remote score API only after the rule set and weighting are proven.

Severity tiers:

- P0: Security exploit, data leak, install blocker.
- P1: Production crash, broken view/action, missing access, severe ORM misuse.
- P2: Performance and upgrade-safety risk.
- P3: Maintainability or lower-confidence finding.

Suggested category weights:

- Security: 25%
- Correctness: 25%
- Performance: 15%
- Data Integrity: 10%
- Upgrade Safety: 10%
- Module Hygiene: 10%
- Frontend: 3%
- Maintainability: 2%

Scoring rules:

- A P0 issue should heavily cap the score.
- CI failure should default to P0/P1 errors only.
- Low-confidence and style rules should not affect score by default.
- Multi-module projects should report both module-level scores and an aggregate project score.

## 12. CLI Shape

Recommended commands:

```bash
odoo-doctor scan .
odoo-doctor scan ./custom_addons --odoo-version 17.0
odoo-doctor scan . --module sale_custom
odoo-doctor scan . --json
odoo-doctor scan . --diff main
odoo-doctor scan . --fail-on error
odoo-doctor rules list
odoo-doctor rules explain security/raw-sql-string-interpolation
odoo-doctor rules disable performance/search-in-loop
odoo-doctor install
```

`odoo-doctor install` should install agent skills and optional git hooks, following the React Doctor pattern.

## 13. GitHub Action

The GitHub Action should:

- Install Odoo Doctor from PyPI.
- Detect changed files in pull requests.
- Run `odoo-doctor scan --json`.
- Render a sticky PR comment.
- Emit GitHub annotations.
- Fail based on `--fail-on`.
- Support non-blocking advisory mode.

Example:

```yaml
name: Odoo Doctor

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  odoo-doctor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: your-org/odoo-doctor@v1
        with:
          odoo-version: "17.0"
          fail-on: error
```

## 14. Agent Skills

Ship two skills:

- `odoo-doctor`
  - Used after Odoo code changes or when the user asks to scan/fix diagnostics.
  - Runs `odoo-doctor scan --diff --verbose`.
  - Fixes P0/P1 first.

- `odoo-doctor-explain`
  - Used when the user asks why a rule fired or wants to tune config.
  - Runs `odoo-doctor rules explain <rule>`.
  - Applies the narrowest config change.

This mirrors React Doctor's strongest workflow: scan, triage, fix, validate, then keep the agent trained on rule-specific expectations.

## 15. Roadmap

### Phase 1 - Foundation and Graph

- CLI scaffold.
- Config loading.
- Addon discovery.
- Manifest parser.
- Python model graph.
- XML/data graph.
- Security CSV graph.
- Diagnostic schema.
- Terminal and JSON reporters.
- Local scoring.

### Phase 2 - MVP Rules

- Implement the 15 MVP rules listed above.
- Add fixtures for Odoo 16, 17, and 18 style projects.
- Add inline suppressions.
- Add rule docs and `rules explain`.

### Phase 3 - CI and Agent Workflow

- GitHub Action.
- PR comments.
- Annotations.
- `--fail-on`.
- `--diff`.
- `odoo-doctor install` for agent skills.

### Phase 4 - Runtime and Frontend Expansion

- Optional runtime probe through `odoo shell` or test database.
- OWL and asset rules.
- Multi-company and multi-currency rules.
- Migration and upgrade-safety rules.

### Phase 5 - Platform

- Remote score API.
- Rule documentation website.
- IDE integration.
- Optional Odoo module for in-app reporting.

## 16. Success Criteria

The first useful version should be able to scan a custom addon repository and catch:

- A model missing access rights.
- A view referencing a non-existent field.
- A button calling a missing method.
- A missing manifest dependency.
- A broken XML reference.
- Unsafe raw SQL.
- Risky public controller `sudo()`.
- Search calls inside loops.

If Odoo Doctor catches these reliably with low false positives, it is already valuable. Everything else can build from there.

## 17. Final Recommendation

Build Odoo Doctor as a Python-first, graph-first analyzer for custom Odoo addons.

Do not start with a broad rule catalog. Start with a small set of high-confidence graph-aware rules that catch module install failures, broken views, access issues, and serious ORM/security problems.

React Doctor's winning pattern is not just "many lint rules"; it is the combination of focused diagnostics, configurable surfaces, score/reporting, CI integration, and agent guidance. Odoo Doctor should copy that product shape while making the Odoo project graph the core engine.
