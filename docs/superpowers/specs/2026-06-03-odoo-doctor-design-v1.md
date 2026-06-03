# Odoo Doctor — Design Spec

**Date:** 2026-06-03
**Status:** Approved
**Approach:** Aggregator-first (Approach A)

---

## Problem

Team 10+ Odoo developers đã có Pylint-Odoo, OCA pre-commit hooks, và Ruff nhưng thiếu unified scoring. Mỗi tool báo lỗi riêng lẻ, không ai trả lời được "module này có đủ chất lượng để deploy không?". Pain points thực tế: code style inconsistency, upgrade failures, performance issues, lỗi bảo mật.

## Solution

Odoo Doctor là một Python CLI tool hoạt động như **orchestrator + scorer**. Nó chạy các external tools (Pylint-Odoo, Ruff, OCA hooks) song song, normalize output thành diagnostic format thống nhất, bổ sung native rules cho deep/cross-file analysis mà external tools không cover, rồi tính health score 0-100 per module.

Primary workflow: **PR advisory (non-blocking)** — GitHub Action post sticky comment trên PR với score delta, không block merge.

Target: multi-version Odoo (14-18), phục vụ cả developer lẫn integrator.

---

## Architecture

```
CLI input: odoo-doctor scan ./addons/my_module
    |
    +-- Backend Adapters (parallel)
    |   +-- PylintOdooAdapter --> [Diagnostic, ...]
    |   +-- RuffAdapter --> [Diagnostic, ...]
    |   +-- OcaPrecommitAdapter --> [Diagnostic, ...]
    |
    +-- Native Rules Engine
    |   +-- ModuleDiscovery --> ModuleContext
    |   +-- PythonAnalyzer --> [Diagnostic, ...]
    |   +-- XmlAnalyzer --> [Diagnostic, ...]
    |   +-- ManifestAnalyzer --> [Diagnostic, ...]
    |   +-- CrossFileAnalyzer --> [Diagnostic, ...]
    |
    +-- Diagnostic Pipeline
    |   +-- Deduplicate (same finding from multiple tools)
    |   +-- Severity overrides (user config)
    |   +-- Ignore filters (rules, files, patterns)
    |   +-- Version gating (skip rules not for this Odoo version)
    |
    +-- Scoring & Output
        +-- Score calculator (weighted by category + tier)
        +-- Terminal renderer (human-readable)
        +-- JSON reporter (CI/programmatic)
        +-- PR comment renderer (markdown)
```

### Three Layers

**Layer 1 — Backend Adapters.** Each adapter runs an external tool and parses its output into `Diagnostic` format. Adapters are optional — if a tool isn't installed, the adapter is skipped with a warning. Adapters run in parallel.

**Layer 2 — Native Rules Engine.** Custom rules for what external tools can't cover: cross-file analysis (needs `ModuleContext`), deep pattern detection (ORM calls in loops), and version-aware checks. Rules are registered via `@rule()` decorator.

**Layer 3 — Scoring & Reporting.** Receives all diagnostics, applies pipeline (dedup, severity overrides, ignore filters, version gating), calculates score, renders output.

---

## Diagnostic Schema

```python
@dataclass(frozen=True)
class Diagnostic:
    module: str           # "sale_custom"
    file_path: str        # "models/sale.py" (relative to module root)
    line: int
    column: int
    rule: str             # "no-sql-injection"
    category: str         # "Security" | "Correctness" | "Performance" | ...
    severity: str         # "error" | "warning"
    source: str           # "native" | "pylint-odoo" | "ruff" | "oca-precommit"
    title: str            # "SQL injection via string formatting"
    message: str          # detailed: which line, what pattern
    help: str             # concrete fix suggestion
    url: str | None       # link to rule docs
    odoo_version: str     # "17.0" -- version detected for this module
```

The `source` field is critical for deduplication and debugging — it tells whether a finding came from an adapter or a native rule.

---

## Module Context

Built per module before cross-file analysis runs. Contains everything needed to reason about the module as a whole:

```python
@dataclass
class ModuleContext:
    name: str                          # from __manifest__.py
    path: Path                         # absolute path to module root
    odoo_version: str                  # detected from manifest version string
    manifest: dict                     # parsed __manifest__.py
    depends: list[str]                 # declared dependencies
    models: dict[str, ModelInfo]       # model_name -> fields, methods, constraints
    xml_ids: dict[str, XmlIdInfo]      # xml_id -> file, record type
    views: list[ViewInfo]              # parsed view definitions
    controllers: list[ControllerInfo]  # HTTP endpoints
    access_rules: list[AccessRule]     # from ir.model.access.csv
    record_rules: list[RecordRule]     # from XML data files
```

Cross-file rules receive `ModuleContext` and can check relationships like "view references field not in model" or "model has no access rules".

---

## Scoring Model

### Impact tiers

Each rule has a fixed impact score per finding:

- **P0** (critical): 25 points — SQL injection, missing access rules, hardcoded secrets
- **P1** (serious): 10 points — N+1 queries, unsafe sudo, broken inheritance
- **P2** (moderate): 4 points — missing ondelete, deprecated API, no index
- **P3** (minor): 1 point — style issues, missing string attribute, manifest warnings

### Formula

Module score = `max(0, 100 - total_impact)`.

One P0 finding (25 points) drops score to 75. Two P0 findings drop to 50. Four P0 findings drop to 0.

### Category sub-scores

Each category has its own sub-score calculated with the same formula. Overall score blends them: `overall = 0.4 * min(category_scores) + 0.6 * avg(category_scores)`. This ensures a single terrible category (e.g., Security at 20) drags the overall score down hard.

### Category weights (config override)

`category_weights` in config multiplies each finding's impact within that category before scoring. Example: `Performance = 1.5` means a P1 finding (10 points) in Performance counts as 15 points. Default weight is 1.0 for all categories. This lets teams temporarily deprioritize categories (e.g., `Architecture = 0.5` during migration phase) or emphasize known problem areas.

### Labels

- 90-100: "Excellent" (green)
- 75-89: "Good" (blue)
- 50-74: "Needs work" (yellow)
- 0-49: "Critical" (red)

### Categories

Eight categories, each with its own sub-score:

1. **Security** — SQL injection, unsafe sudo, missing access rules, hardcoded secrets, controller auth
2. **Correctness** — Invalid field types, broken inheritance, XML ID mismatches, deprecated API, wrong return types
3. **Performance** — N+1 in compute, search in loop, unbounded search, missing index
4. **Data Integrity** — Missing SQL constraints, unsafe unlink, cascade delete risks
5. **Architecture** — Monkey-patching, hardcoded XML IDs, direct SQL DDL, missing migration scripts
6. **UX** — Missing string attributes, hardcoded text, OWL antipatterns, view-field mismatches
7. **Module Hygiene** — Manifest issues, unused/phantom dependencies, legacy JS in OWL
8. **Multi-company** — Missing company filters, hardcoded currency

---

## Backend Adapter Interface

```python
class BackendAdapter(Protocol):
    name: str

    def is_available(self) -> bool:
        """Check if the tool is installed."""

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        """Run the tool and return normalized diagnostics."""
```

Each adapter has a rule mapping config (`adapters/pylint_odoo/rule_mapping.toml`) that maps external tool rules to Odoo Doctor categories and tiers. Unmapped rules go to "Uncategorized" with tier P3.

### Deduplication

When multiple tools report the same issue:

1. Group diagnostics by `(file_path, line, category)`
2. Within each group, keep the diagnostic with the more detailed `message`, preferring `source="native"`
3. Diagnostics at same file+line but different categories are kept — they represent genuinely different issues

---

## Native Rules — MVP Set (10 rules)

### Cross-file analysis (needs ModuleContext)

1. **missing-access-rules** [Security, P0] — Model declared in Python with no entry in `ir.model.access.csv`
2. **view-field-not-in-model** [Correctness, P1] — View XML references field not defined on the model
3. **phantom-dependency** [Module Hygiene, P1] — Code uses `self.env['stock.picking']` but `stock` not in `depends`
4. **unused-dependency** [Module Hygiene, P2] — Module in `depends` but nothing from it is referenced

### Deep pattern detection

5. **no-search-in-loop** [Performance, P1] — ORM calls (`search`, `browse`, `write`) inside `for` loop
6. **no-n-plus-one-in-compute** [Performance, P1] — `search()`/`browse()` inside `@api.depends` computed field
7. **no-unsafe-sudo-write** [Security, P1] — `sudo().write()` or `sudo().create()` on models with access rules

### Version-aware checks

8. **deprecated-api** [Architecture, P2] — `api.multi`, `api.one`, `osv.osv` etc., gated by Odoo version
9. **missing-ondelete** [Correctness, P2] — `Many2one` without explicit `ondelete`, severity varies by version
10. **no-deprecated-widget** [UX, P2] — View widgets removed or renamed in target Odoo version

### Rule registration

```python
@rule(
    name="missing-access-rules",
    category="Security",
    severity="error",
    tier="P0",
    min_version="14.0",
    needs_context=True,
)
def check_missing_access_rules(ctx: ModuleContext) -> list[Diagnostic]:
    ...
```

Rules with `needs_context=False` run in per-file analyzer phase (parallelizable per file). Rules with `needs_context=True` run in CrossFileAnalyzer phase after ModuleContext is built.

---

## Config

File: `odoo-doctor.toml` at repo root or module directory.

```toml
[odoo-doctor]
odoo_version = "17.0"
min_score = 60

[adapters]
pylint_odoo = true
ruff = true
oca_precommit = false

[ignore]
rules = ["no-deprecated-widget"]
files = ["**/migrations/**", "**/tests/**"]
modules = ["base_setup"]

[severity]
"missing-ondelete" = "warning"
"no-search-in-loop" = "off"

[category_weights]
Security = 1.0
Performance = 1.5
Architecture = 0.5
```

---

## CLI Interface

```bash
odoo-doctor scan ./addons/sale_custom       # scan one module
odoo-doctor scan ./addons                    # scan all modules in directory
odoo-doctor scan ./addons --diff main        # scan only changed files vs main
odoo-doctor scan ./addons --json             # JSON output for CI
odoo-doctor rules                            # list all active rules
odoo-doctor explain no-search-in-loop        # explain a rule
odoo-doctor init                             # create config file
```

---

## PR Integration

GitHub Action composite, advisory mode (non-blocking):

```yaml
name: Odoo Doctor
on: [pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/odoo-doctor-action@v1
        with:
          directory: ./addons
          diff: main
          comment: true
          fail-on: none
          min-score: 60
```

Action flow: (1) install odoo-doctor + adapters, (2) scan with `--diff --json`, (3) render markdown comment, (4) post/update sticky comment on PR.

### PR comment format

```markdown
## Odoo Doctor -- sale_custom

Score: **62/100** (Needs work)  |  Delta from main: **-8**

| Category | Score | Findings |
|----------|-------|----------|
| Security | 80 | 1 warning |
| Performance | 60 | 2 errors, 1 warning |
| Architecture | 40 | 3 errors |

### Top issues to fix
1. [P0] SQL injection in models/sale.py:42
2. [P1] N+1 query in models/sale.py:87
3. [P1] Deprecated api.multi in models/sale.py:12
```

---

## Inline Suppression

Python:
```python
# odoo-doctor: disable=no-search-in-loop
for record in records:
    partners = self.env['res.partner'].search([...])
```

XML:
```xml
<!-- odoo-doctor: disable=view-field-not-in-model -->
<field name="x_custom_field"/>
```

---

## Technology Choices

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Language | Python | Natural for Odoo ecosystem, team already knows it |
| Python AST | stdlib `ast` | No dependencies, sufficient for pattern detection |
| XML parsing | `lxml` | Fast, XPath support for view analysis |
| Config format | TOML | PEP 518 style, familiar to Python devs |
| Package manager | pip/uv, published to PyPI | Standard Python distribution |
| Scoring | Local weighted formula | No external API dependency, simple and transparent |
| CI | GitHub Actions composite | Same proven pattern as react-doctor |

---

## MVP Phases

### Phase 1 — Core + Scoring (3-4 weeks)
- Diagnostic schema and pipeline (dedup, severity overrides, ignore filters, version gating)
- Backend adapter interface + PylintOdooAdapter + RuffAdapter
- Rule mapping configs for both adapters
- Module discovery (`__manifest__.py` finder) and version detection
- Scoring engine (tier-based impact, category sub-scores, overall blend)
- CLI with terminal renderer (`scan`, `rules`, `explain`, `init`)
- Config file support (`odoo-doctor.toml`)
- JSON output (`--json`)

### Phase 2 — Native Rules (2-3 weeks)
- ModuleContext builder (Python AST + XML + manifest + access CSV parsing)
- PythonAnalyzer, XmlAnalyzer, ManifestAnalyzer, CrossFileAnalyzer
- 10 native rules (listed above)
- Inline suppression comments
- `@rule()` decorator and rule registry

### Phase 3 — CI Integration (1-2 weeks)
- GitHub Action composite
- PR comment renderer (markdown)
- Sticky comment post/update
- Diff mode (`--diff main`)
- Score delta calculation (compare current vs base branch)

### Phase 4 — Breadth (ongoing)
- OcaPrecommitAdapter
- Additional native rules based on team feedback
- OWL/JS analysis (if team adopts OWL heavily)
- Multi-company rules
- Rule documentation site
