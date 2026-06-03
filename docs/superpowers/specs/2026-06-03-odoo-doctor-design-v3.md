# Odoo Doctor — Design Spec v3

**Date:** 2026-06-03
**Status:** Proposed final
**Approach:** Diagnostic-contract-first, confidence-aware graph analysis, adapter-assisted scoring

---

## Problem

Odoo teams already use tools such as Pylint-Odoo, Ruff, and OCA pre-commit hooks,
but those tools do not give one clear answer:

```text
Is this custom addon healthy enough to deploy?
```

They also miss or only partially cover many Odoo-specific failures because those
failures are cross-file and cross-module:

- Python models define fields and methods.
- XML views reference those fields and methods.
- Buttons call Python methods through XML.
- CSV files grant access to model external IDs.
- Manifests define dependencies and data load order.
- XML/data files reference external IDs across addon boundaries.

Odoo Doctor should not be a generic Python linter. Its core value is Odoo-aware
static understanding with low false positives.

---

## Product Definition

Odoo Doctor is a Python CLI that builds a confidence-aware Odoo addon graph, runs
high-signal native rules plus optional external lint adapters, normalizes all
findings into one diagnostic pipeline, and produces actionable reports plus a
local health score for developers and coding agents.

The product message:

```text
Your agent writes risky Odoo customizations, this catches them.
```

Primary users:

- Odoo teams reviewing custom addon pull requests.
- Agencies maintaining many customer-specific modules.
- Developers preparing modules for upgrade.
- Coding agents that need deterministic feedback after editing Odoo code.

MVP surfaces:

- Terminal report.
- JSON report for automation and agents.
- Rule listing and rule explanation.
- Configurable ignores, severity overrides, and inline suppression.
- Two agent skills (`odoo-doctor`, `odoo-doctor-explain`) consuming the JSON report.

Post-MVP surfaces:

- GitHub Action.
- Sticky PR comments.
- GitHub annotations.
- Score delta against base branch.
- Documentation site.

---

## Core Design Decision

The spec should not choose between pure aggregator-first and pure graph-first.
The optimal architecture is:

```text
Diagnostic-contract-first + Graph-first moat + Adapter-assisted scoring
```

Meaning:

- `Diagnostic` is the shared contract for every finding.
- The diagnostic pipeline is the technical spine.
- The Odoo graph and resolver are the product moat.
- External adapters are optional signal sources, not the center of the product.
- Scoring is deterministic and local.
- PR/CI integration is a renderer/surface, not core engine logic.

---

## Architecture

```text
odoo-doctor scan ./addons/sale_custom
      |
      v
  Discovery
      - find addons by __manifest__.py
      - load config
      - detect target Odoo version conservatively
      |
      v
  Parse Inputs
      - manifest files
      - Python model/controller files
      - XML/data/view files
      - security CSV files
      |
      v
  Build Module Graph
      - modules and dependencies
      - models, fields, methods
      - XML IDs and records
      - views and buttons
      - access rules
      |
      v
  Confidence-Aware Resolver
      - repo symbols
      - packaged stubs for common Odoo addons
      - optional odoo_source_path
      - FOUND / NOT_FOUND / UNKNOWN
      |
      +-------------------------+-----------------------------+
      |                         |                             |
      v                         v                             v
  Native Rules             Pylint-Odoo Adapter           Ruff Adapter
  graph-aware              optional                      optional
      |                         |                             |
      +-------------------------+-----------------------------+
                                |
                                v
                    Diagnostic Pipeline
                    - dedup
                    - severity override
                    - ignore filter
                    - inline suppression
                    - version gate
                                |
                                v
                    Scoring Engine
                    - tier impact
                    - category scores
                    - overall score
                                |
                                v
                    Renderers
                    - terminal
                    - JSON
                    - future PR comment / annotations
```

Boundary principles:

- Native rules and adapters only emit `Diagnostic` objects.
- Pipeline stages do not know whether a diagnostic came from native analysis or
  an adapter.
- Resolver uncertainty stays inside graph analysis.
- Adapters are optional. Missing, crashing, or timing-out tools produce warnings
  and do not fail the whole scan.
- Renderers consume final scan results only.

---

## Diagnostic Schema

Every finding uses one schema:

```python
@dataclass(frozen=True)
class Diagnostic:
    module: str
    file_path: str
    line: int
    column: int

    rule: str
    category: str
    severity: str      # "error" | "warning" | "info"
    tier: str          # "P0" | "P1" | "P2" | "P3"
    source: str        # "native" | "pylint-odoo" | "ruff" | "oca"
    confidence: str    # "high" | "medium" | "low"

    title: str
    message: str
    help: str
    odoo_version: str
    url: str | None
```

Important separation:

- `tier` is the fixed rule impact used for scoring.
- `severity` is display/CI behavior and can be overridden by config.
- `confidence` controls whether a diagnostic affects score by default.
- `source` is required for deduplication and debugging.

Default scoring only counts diagnostics with `confidence = "high"`.

---

## Categories

MVP categories:

- Security
- Correctness
- Performance
- Data Integrity
- Upgrade Safety
- Module Hygiene
- Maintainability

Post-MVP categories:

- Frontend
- Multi-company

Reasoning:

- `Frontend` should wait until OWL/JS rules exist.
- `Multi-company` is valuable but high-risk for false positives without deeper
  domain modeling.

Canonical category identifiers are these exact strings, used everywhere (rule
tags, adapter rule-mapping files, and `[category_weights]` keys): `Security`,
`Correctness`, `Performance`, `Data Integrity`, `Upgrade Safety`,
`Module Hygiene`, `Maintainability`. Multi-word identifiers keep the space and
must be quoted in TOML.

---

## Version Detection

Version detection must be conservative. Do not assume manifest `version` always
means target Odoo series because many real projects use custom version strings.

Detection order:

1. CLI flag `--odoo-version`.
2. `odoo_version` in `odoo-doctor.toml`.
3. Manifest version prefix if it clearly follows Odoo conventions, such as
   `17.0.1.0.0`.
4. Installed `odoo` Python package metadata, if available.
5. Unknown.

Rules should be gated by capabilities rather than only raw versions where
possible:

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

If version or capability is unknown, version-specific rules should stay silent
unless they can prove the issue independently.

---

## Module Graph

The graph builder parses one or more addon directories and produces structured
module context.

```python
@dataclass
class ModuleContext:
    name: str
    path: Path
    odoo_version: str
    manifest: dict
    depends: list[str]

    models: dict[str, ModelInfo]
    xml_ids: dict[str, XmlIdInfo]
    views: list[ViewInfo]
    controllers: list[ControllerInfo]
    access_rules: list[AccessRule]

    resolver: SymbolResolver  # reference to the shared project-level resolver
```

The `resolver` is a single project-level object shared by every `ModuleContext`.
It sees all scanned modules plus packaged stubs, so cross-module rules such as
`manifest-missing-dependency` and `missing-xml-ref` can resolve references that
originate in other addons. Per-module contexts hold a reference to it, not their
own private copy.

MVP parsing scope:

- `__manifest__.py` via AST plus `ast.literal_eval`, never `eval`.
- Python model classes using stdlib `ast`.
- Python controller route decorators using stdlib `ast`.
- XML records/views/actions/menus with `lxml`.
- `security/ir.model.access.csv` with Python CSV parser.

Do not attempt full Python execution or runtime Odoo environment simulation in
the MVP.

---

## Confidence-Aware Resolver

The resolver answers symbol questions with explicit uncertainty:

```text
FOUND
NOT_FOUND
UNKNOWN
```

Resolution order:

1. Symbols defined by modules being scanned.
2. Packaged stubs for common Odoo addons by version.
3. Optional `odoo_source_path` configured by user.
4. `UNKNOWN`.

MVP packaged stubs should cover common core/community addons first:

```text
base, web, mail, contacts, product, sale, purchase, stock, account
```

More stubs can be added later from an offline script that parses official Odoo
source per version.

Golden rule:

```text
Native graph rules only emit score-impacting diagnostics when the resolver can
prove NOT_FOUND with high confidence.
```

If the resolver returns `UNKNOWN`, the rule should not report an error by
default. It may emit an informational low-confidence diagnostic only when verbose
or debug output is enabled.

This intentionally trades some coverage for trust. False positives are more
damaging than missed low-confidence findings in the first release.

---

## Native MVP Rules

The MVP rule set should be narrow and high-signal. It should prove the product
by catching install failures, broken views, security risks, and common ORM
performance traps.

### Manifest and Module Graph

1. `manifest-missing-required-fields` [Module Hygiene, P2]
   Missing important manifest keys such as `license`, `depends`, `data`, or
   `installable`.

2. `manifest-missing-dependency` [Module Hygiene, P1]
   Module references external IDs, models, or inherited views from another addon
   but does not list that addon in `depends`.

### Security and Access

3. `missing-access-csv` [Security, P0]
   A new persistent model is declared but no access CSV entry grants permissions.

4. `unknown-model-in-access-csv` [Correctness, P1]
   `ir.model.access.csv` references a model external ID that cannot be resolved.
   (Grouped here by topic; scored under `Correctness`. Fires only on a proven
   `NOT_FOUND`, never on `UNKNOWN`.)

5. `raw-sql-string-interpolation` [Security, P0]
   `env.cr.execute()` or `cr.execute()` uses f-strings, string formatting, or
   concatenation instead of SQL parameters.

### XML and Views

6. `duplicate-xml-id` [Correctness, P1]
   The same XML ID is defined more than once in a module.

7. `missing-xml-ref` [Correctness, P1]
   `ref`, `inherit_id`, menu/action references, or `env.ref()` target cannot be
   resolved.

8. `view-field-not-in-model` [Correctness, P1]
   XML view references a field that is not known on the resolved model.

9. `button-method-not-found` [Correctness, P1]
   Object button calls a method missing from the resolved model.

### Performance

10. `search-in-loop` [Performance, P1]
    ORM `search`, `search_count`, `browse`, `read`, `write`, or `create` is
    called inside a loop where batching is likely possible.

These 10 rules are enough to validate the graph engine and produce real value
without expanding into noisy style or architecture checks too early.

### Rule Registration

Every native rule declares its metadata so the pipeline knows how to run and
score it:

```python
@rule(
    name="missing-access-csv",
    category="Security",
    tier="P0",
    severity="error",
    default_confidence="high",   # baseline; graph rules may downgrade per finding
    needs_context=True,          # True -> runs after ModuleContext + resolver
    min_version="14.0",          # optional capability/version gate
)
def check_missing_access_csv(ctx: ModuleContext) -> list[Diagnostic]:
    ...
```

Confidence assignment per finding:

- Pure AST rules (e.g. `raw-sql-string-interpolation`, `search-in-loop`) emit at
  their `default_confidence` (normally `high`) because they do not depend on the
  resolver.
- Graph rules derive confidence from the resolver: a proven `NOT_FOUND` yields
  `high`; an `UNKNOWN` yields `low` (informational only, never score-impacting by
  default).
- Adapter diagnostics take confidence from the adapter rule-mapping file.

`needs_context=False` rules run in the per-file phase (parallelizable per file);
`needs_context=True` rules run after the graph and resolver are built.

---

## Rules Deferred From MVP

Defer until the first 10 rules are reliable:

- `compute-missing-depends`
- `override-missing-super`
- `public-controller-sudo-risk`
- `unbounded-search`
- `deprecated-api`
- `manifest-data-order-risk`
- `missing-ondelete`
- OWL/JavaScript rules
- Multi-company and multi-currency rules
- Runtime database validation
- In-app Odoo reporting module
- Remote score API
- IDE integrations

Avoid as default MVP rules:

- `missing-string-attribute`
  - Odoo fields often inherit labels from model definitions; this can be noisy.

- `no-hardcoded-xml-id`
  - `env.ref("module.xml_id")` is normal Odoo code. Better checks are missing
    dependency, missing XML ID, or optional ref without fallback.

- `no-compute-without-store`
  - Non-stored computed fields are valid. A safer future rule would detect
    expensive non-stored computes used in list/search contexts.

- Broad `missing-ondelete`
  - Useful eventually, but noisy unless scoped to genuinely risky models.

---

## Backend Adapters

Adapters normalize external tool output into `Diagnostic`.

```python
class BackendAdapter(Protocol):
    name: str

    def is_available(self) -> bool:
        ...

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        ...
```

MVP adapters:

- Ruff
- Pylint-Odoo

Post-MVP adapter:

- OCA pre-commit

Adapter rules are mapped through data files:

```toml
"sql-injection" = { category = "Security", tier = "P0", confidence = "high" }
"manifest-required-key" = { category = "Module Hygiene", tier = "P2", confidence = "high" }
"translation-required" = { category = "Maintainability", tier = "P3", confidence = "medium" }
```

Unmapped adapter diagnostics:

- category: `Uncategorized`
- tier: `P3`
- confidence: `low`
- counted in score: no, by default

This prevents unknown external rules from unexpectedly lowering health scores.

---

## Diagnostic Pipeline

Pipeline stages are pure transformations:

```text
list[Diagnostic] -> list[Diagnostic]
```

Required order:

1. Normalize paths and fields.
2. Deduplicate.
3. Apply severity overrides.
4. Apply ignore filters.
5. Apply inline suppressions.
6. Apply version/capability gates.
7. Mark score eligibility.

Deduplication:

- Group by `(module, file_path, line, category)`.
- When merging a group, keep the highest `confidence` present so a
  high-confidence finding is never dropped in favor of a low-confidence one
  (confidence wins over source, to preserve score impact).
- Among equal confidence, prefer `source = "native"` over external adapters.
- Prefer more specific messages.
- Keep diagnostics at the same line if categories differ.

Dedup runs before scoring so one issue reported by two tools is counted once.

---

## Scoring

Scoring is local and deterministic.

Tier impact:

```text
P0 = -25
P1 = -10
P2 = -4
P3 = -1
```

Default score eligibility:

- Count only `confidence = "high"`.
- Do not count `Uncategorized`.
- Do not count ignored or suppressed diagnostics.
- Do not count diagnostics whose rules are gated off for the detected version.

Category score:

```text
category_score = max(0, 100 - weighted_impact)
```

Overall score is computed only over **in-scope categories** — those with at
least one active rule for the detected version. Categories with no active rule
are excluded from both `min` and `avg`, so empty categories cannot inflate the
result:

```text
overall = 0.4 * min(in_scope_scores) + 0.6 * avg(in_scope_scores)
```

This prevents a module with serious Security or Correctness failures from
receiving a high score just because other categories are clean or empty.

Labels:

```text
90-100  Excellent
75-89   Good
50-74   Needs work
0-49    Critical
```

Multi-module scans should report:

- score per module
- aggregate project score
- top findings across the project

---

## Configuration

Use `odoo-doctor.toml`.

```toml
[odoo-doctor]
odoo_version = "17.0"
addons_paths = ["addons", "custom_addons"]
target_modules = []
odoo_source_path = ""
min_score = 60

[adapters]
ruff = true
pylint_odoo = true
oca = false

[severity]
"search-in-loop" = "warning"
"manifest-missing-required-fields" = "warning"

[ignore]
rules = []
files = ["**/migrations/**", "**/tests/**"]
modules = []

[category_weights]
Security = 1.0
Correctness = 1.0
Performance = 1.0
"Data Integrity" = 1.0
"Upgrade Safety" = 1.0
"Module Hygiene" = 1.0
Maintainability = 1.0
```

Config principles:

- CLI flags override config.
- Nearby config overrides parent config.
- A positional scan path (`odoo-doctor scan .`) overrides `addons_paths`; when
  omitted, `addons_paths` is used. `--module` overrides `target_modules`; an
  empty `target_modules` means scan every discovered module.
- `severity` changes display/CI behavior, not rule `tier`.
- `ignore` removes diagnostics from output and score.
- Category weights modify score impact without changing rule tier. Weight keys
  use the canonical category identifiers (quoted in TOML when they contain a
  space).
- MVP does not need `[surfaces.*]`; add it when PR comments and CI failure
  policies are implemented.

---

## CLI

MVP commands:

```bash
odoo-doctor scan .
odoo-doctor scan ./custom_addons --odoo-version 17.0
odoo-doctor scan . --module sale_custom
odoo-doctor scan . --json
odoo-doctor scan . --diff main
odoo-doctor scan . --fail-on error
odoo-doctor rules list
odoo-doctor rules explain raw-sql-string-interpolation
odoo-doctor init
odoo-doctor install
```

`--diff main` and `install` are in the MVP because the agent skills depend on
them: skills run `scan --diff --json`, and `install` sets up the skills and
optional git hooks.

Post-MVP commands relate to CI/PR surfaces (emitting GitHub annotations, posting
sticky comments, score delta against base branch), not new core analysis.

Recommended implementation:

- CLI: `typer`
- Terminal output: `rich`
- JSON output: stable schema consumed by agents and future CI action

---

## Agent Skills

Ship two skills in the MVP. Both consume the JSON report, so agents and any
future CI action read from one stable source.

- `odoo-doctor` — used after editing Odoo code or when asked to scan/fix. Runs
  `odoo-doctor scan --diff --json`, fixes `P0`/`P1` findings first, then re-scans
  to confirm.
- `odoo-doctor-explain` — used when asked why a rule fired or to tune config.
  Runs `rules explain <rule>` and applies the narrowest config change (disable
  one rule in one file) rather than turning off a whole family.

`odoo-doctor install` installs these skills and optional git hooks.

## Inline Suppression

Python:

```python
# odoo-doctor: disable=search-in-loop
for record in records:
    partner = self.env["res.partner"].search([("email", "=", record.email)])
```

XML:

```xml
<!-- odoo-doctor: disable=view-field-not-in-model -->
<field name="x_dynamic_field"/>
```

Suppression rules:

- Suppressions should be narrow by rule name.
- File-wide disable should be supported but discouraged in docs.
- Suppressed diagnostics do not affect score.

---

## Testing Strategy

Use `pytest`.

Required test layers:

- Diagnostic schema tests.
- Pipeline input/output tests.
- Scoring numeric tests.
- Manifest parser fixtures.
- Python model parser fixtures.
- XML/view parser fixtures.
- Security CSV parser fixtures.
- Resolver tests for `FOUND`, `NOT_FOUND`, and `UNKNOWN`.
- Native rule fixtures with paired bad/clean modules.
- Adapter tests using recorded external tool output.

Rule fixture standard:

```text
tests/fixtures/rules/<rule-name>/bad_module
tests/fixtures/rules/<rule-name>/clean_module
```

Every MVP rule must prove both:

- it catches the intended failure
- it stays silent on a clean equivalent module

The resolver must explicitly test that rules do not flag when resolution returns
`UNKNOWN`.

---

## Technology Choices

| Concern | Choice | Reason |
| --- | --- | --- |
| Language | Python | Natural for Odoo ecosystem |
| CLI | `typer` | Type-hint friendly, clean command structure |
| Terminal UI | `rich` | Readable local reports |
| Python parsing | stdlib `ast` | Enough for MVP, low dependency cost |
| Comment scanning | `tokenize` | Needed for inline suppression |
| XML parsing | `lxml` | XPath and robust XML handling |
| Manifest parsing | `ast.literal_eval` | Safe parsing, never execute manifests |
| Config | TOML | Familiar Python project convention |
| Packaging | PyPI, uv/pipx friendly | Fits Odoo teams |
| Tests | `pytest` | Standard and fixture-friendly |

`libcst` is deferred until autofix/codemod or source-preserving advanced analysis
becomes necessary.

---

## Repository Layout

```text
odoo-doctor/
  src/odoo_doctor/
    cli/
      app.py
      renderers/
    core/
      diagnostics.py
      pipeline.py
      scoring.py
      config.py
    discovery/
      addons.py
      odoo_version.py
    parsers/
      manifest.py
      python_models.py
      xml_records.py
      security_csv.py
    graph/
      module_context.py
      resolver.py
      stubs/
    adapters/
      base.py
      ruff/
      pylint_odoo/
    rules/
      registry.py
      manifest/
      security/
      xml/
      performance/
    reporters/
      terminal.py
      json_report.py
  skills/
    odoo-doctor/
      SKILL.md
    odoo-doctor-explain/
      SKILL.md
  tests/
    fixtures/
```

Keep the MVP as one Python package. Split into multiple packages only when the
surface area justifies it.

---

## MVP Success Criteria

The first useful version should scan a custom addon repository and reliably catch:

- Missing access rights for a persistent model.
- Access CSV pointing to an unknown model.
- View referencing a non-existent field.
- Button calling a missing method.
- Missing manifest dependency.
- Broken XML reference.
- Duplicate XML ID.
- Unsafe raw SQL.
- ORM search inside loop.
- Missing important manifest metadata.

It should produce:

- terminal report
- JSON report
- per-module health score
- aggregate project score
- rule explanations
- low false positives by refusing to flag `UNKNOWN` resolver results

If these work reliably, Odoo Doctor has proven its core value. PR comments,
GitHub Actions, broader rule catalogs, OWL rules, and runtime validation can be
built on top without changing the core architecture.

---

## Final Recommendation

Build Odoo Doctor as a Python-first, diagnostic-contract-first analyzer whose
main moat is confidence-aware Odoo graph analysis.

Do not start with a broad rule catalog. Do not center the product on external
linters. Start with a small set of high-confidence graph-aware rules that catch
install failures, broken views, access issues, and serious ORM/security problems.

The winning shape borrowed from React Doctor is not "many lint rules"; it is the
combination of focused diagnostics, a unified pipeline, configurable reporting,
health scoring, and agent guidance. Odoo Doctor should keep that product shape
while making the Odoo project graph the core engine.
