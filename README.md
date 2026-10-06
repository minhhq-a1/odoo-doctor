# Odoo Doctor 🩺

**Unified health scoring for Odoo custom addons.**

Combines confidence-aware static analysis with optional external linters (Ruff, Pylint-Odoo) to produce a single **0–100 score per addon** — designed for CI pipelines and AI coding agents.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Quick Start

```bash
# 1. Chạy ngay (không cần install)
pipx run odoo-doctor scan .

# 2. Install global
pip install odoo-doctor
odoo-doctor scan .

# 3. JSON output cho CI / agents
odoo-doctor scan . --json

# 4. Fail nếu score < 80
odoo-doctor scan . --min-score 80

# 5. Chỉ scan file đã thay đổi (PR review)
odoo-doctor scan . --diff main --json
```

---

## What it checks

| Rule | Tier | Category |
|------|------|----------|
| `raw-sql-string-interpolation` | P0 | Security |
| `missing-access-csv` | P0 | Security |
| `unknown-model-in-access-csv` | P1 | Correctness |
| `duplicate-xml-id` | P1 | Correctness |
| `view-field-not-in-model` | P1 | Correctness |
| `button-method-not-found` | P1 | Correctness |
| `missing-xml-ref` | P1 | Correctness |
| `manifest-missing-dependency` | P1 | Module Hygiene |
| `manifest-missing-required-fields` | P2 | Module Hygiene |
| `search-in-loop` | P1 | Performance |
| `public-controller-sudo-risk` | P1 | Security |
| `unbounded-search` | P2 | Performance |
| `manifest-data-order-risk` | P2 | Module Hygiene |
| `override-missing-super` | P1 | Correctness |
| `compute-missing-depends` | P2 | Correctness |
| `missing-ondelete` | P1 | Data Integrity |
| `data-noupdate-risk` | P2 | Data Integrity |
| `deprecated-api-usage` | P1 | Upgrade Safety |
| `removed-model-still-referenced` | P1 | Upgrade Safety |
| `asset-bundle-missing` | P2 | Frontend |
| `expensive-nonstored-compute` | P2 | Performance |
| `monetary-missing-currency-field` | P1 | Correctness |
| `missing-multicompany-rule` | P1 | Security |
| `unsafe-template-render` | P1 | Security |
| `hardcoded-company-or-currency` | P2 | Correctness |

Plus Ruff and Pylint-Odoo findings when those tools are installed.

The full, generated reference (37 rules, with before/after examples) is in
[`docs/rules.md`](docs/rules.md); every finding links to its entry. Disable a rule
with `odoo-doctor rules disable <rule-name>`; write your own with the stable
[plugin API](docs/custom-rules.md). What you can rely on across upgrades (CLI flags, exit
codes, JSON keys, rule IDs) is in the [stability contract](docs/stability.md).

---

## Score explained

Each category score starts at 100 and loses points per **high-confidence**
finding, where each finding deducts `tier_impact × category_weight`
(default weight 1.0; override via `[category_weights]`). The overall score
blends only **in-scope** categories (those with at least one active rule):

```
category_score = max(0, 100 − Σ(tier_impact × category_weight))
overall        = 0.4 × min(in_scope_category_scores)
               + 0.6 × avg(in_scope_category_scores)
```

Tier impacts: P0 = 25, P1 = 10, P2 = 4, P3 = 1.

| Label | Range |
|-------|-------|
| Excellent | 90–100 |
| Good | 75–89 |
| Needs work | 50–74 |
| Critical | 0–49 |

Each finding deducts points by tier: **P0 = −25**, **P1 = −10**, **P2 = −4**, **P3 = −1**.  
Only `high` confidence findings count toward the score.

### Fix first

Every scan ranks the score-eligible findings of each module by **marginal score
gain per effort**, so you (or an agent) fix the right thing first. The terminal
prints the top 5 under *Fix first*; `--json` has the top 10 per module as
`modules.<name>.fix_priorities`:

```json
{"rank": 1, "rule": "missing-ondelete", "file_path": "...", "line": 79,
 "impact": 10.0, "effort": 1, "roi": 10.0, "projected_score": 52.1,
 "score_gain": 4.7, "fixable": false}
```

- `effort` is a coarse 1-3 estimate per rule (1 mechanical, 2 local code change,
  3 restructuring); auto-fixable rules count as 1.
- `projected_score` is the module score after fixing this finding *and every one
  ranked before it*; `score_gain` is the change this step made. A category that is
  already at 0 shows `+0.0` until enough of its findings are fixed — the weakest
  category carries the `0.4 × min` term, so it is ranked first.

---

## Configuration

```bash
odoo-doctor init   # creates odoo-doctor.toml
```

```toml
[odoo-doctor]
odoo_version = "17.0"
addons_paths = ["."]
odoo_source_path = "/path/to/odoo/source"
capabilities = ["enterprise", "owl"]
min_score = 75

[adapters]
ruff = true
pylint_odoo = false

[severity]
"search-in-loop" = "warning"

[ignore]
rules = []
files = ["**/migrations/**"]
modules = []

[category_weights]
Security = 1.5

[surfaces.pr_comment]
min_confidence = "all"
categories = []

[surfaces.ci_failure]
min_confidence = "high"
categories = []
```

---

## CI Integration

### GitHub Actions

The easiest way to integrate Odoo Doctor into GitHub Actions is using our official composite action. See `.github/workflows/odoo-doctor.example.yml` for a full example.

```yaml
- name: Odoo Doctor Scan
  uses: minhhq-a1/odoo-doctor@v0.7.0
  with:
    fail-on: warning
    min-score: 75
    diff-base: main
    pr-comment: true
    paths: "."
```

If you prefer `pip install`, you can run it directly:

```yaml
- name: Odoo Doctor (pip)
  run: |
    pip install odoo-doctor
    odoo-doctor scan . --format github --min-score 75 --fail-on error
```

### SARIF & Baseline Mode

For GitHub Code Scanning and IDE integration:
```bash
odoo-doctor scan . --format sarif > results.sarif
# Then upload via github/codeql-action/upload-sarif
```

To capture current debt and block only new findings in CI:
```bash
odoo-doctor scan . --write-baseline .odoo-doctor-baseline.json
# Commit the baseline, then in CI:
odoo-doctor scan . --baseline .odoo-doctor-baseline.json --fail-on warning
```

### CI/PR Surfaces

- **`--format github`**: Emits GitHub Actions annotations inline.
- **`--score-delta <base-ref>`**: Opt-in PR score delta. It does a worktree-isolated second scan and needs git history (`fetch-depth: 0` in Actions).
- **Sticky PR comment**: Posted/updated via `gh` when `--format github` runs in a PR with a valid `GH_TOKEN`. Idempotent via a hidden marker.

### CI failure policy

`--fail-on <severity>` only counts findings admitted by `[surfaces.ci_failure]`,
which defaults to **P0/P1 at high confidence**: style/advisory (P2/P3) and
low-confidence findings are reported but never fail a build. Adjust it:

```toml
[surfaces.ci_failure]
tiers = ["P0", "P1", "P2"]   # [] = every tier
min_confidence = "high"
```

### Score history & badge

Track the score over time and publish a badge without any server (see
[`docs/score-history.md`](docs/score-history.md)):

```bash
odoo-doctor scan . --history .odoo-doctor/history.jsonl --badge badge.svg
odoo-doctor history show .odoo-doctor/history.jsonl --max-drop 3   # exit 2 on regression
odoo-doctor history import history.jsonl old-report.json           # pre-0.4.0 reports
```

### pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: odoo-doctor
        name: Odoo Doctor
        language: system
        entry: odoo-doctor scan --diff HEAD --fail-on error
        pass_filenames: false
        types: [python]
```

---

## Agent Usage

Odoo Doctor is designed for AI coding agents. Install the SKILL.md files:

```bash
odoo-doctor install   # installs to .odoo-doctor/skills/
```

Then in your agent workflow:

```bash
# After editing Odoo code
odoo-doctor scan . --diff main --json

# Fix P0/P1 findings with confidence: "high"
# Re-scan to verify fixes
odoo-doctor scan . --diff main --json
```

Use `odoo-doctor rules explain <rule-name>` to understand any finding (description, why, fix, examples and a docs link).

Use `odoo-doctor rules stats` to see which rules your team suppresses most (inline `# odoo-doctor: disable`, `[ignore] rules`, `[severity] = "off"`). Rules where most findings are suppressed are flagged as noisy, with a suggestion to lower their severity.

**In your editor (experimental).** `pip install 'odoo-doctor[lsp]'` adds `odoo-doctor lsp`, a language server that shows the same findings as diagnostics and offers quick fixes (apply the auto-fix, or disable the rule on a line, in a file or in `odoo-doctor.toml`). The VS Code extension is on the [Marketplace](https://marketplace.visualstudio.com/items?itemName=MinhHong.odoo-doctor) (`MinhHong.odoo-doctor`, preview; source in [`editors/vscode`](editors/vscode)); setup for VS Code, Neovim and Helix is in [`docs/lsp.md`](docs/lsp.md).

---

## Generating stubs for your Odoo version

Bundled stubs cover **17.0, 18.0, 19.0** (core models only).  
For full accuracy, generate from source or a live instance:

```bash
# From Odoo source checkout
python -m odoo_doctor.graph.stubs.build_stubs source \
  --odoo-path /path/to/odoo \
  --version 17.0

# From a live Odoo instance (no source needed)
python -m odoo_doctor.graph.stubs.build_stubs rpc \
  --rpc-url http://localhost:8069 \
  --rpc-db mydb \
  --rpc-password admin \
  --version 17.0
```

The generated JSON is written to `src/odoo_doctor/graph/stubs/data/<version>.json`  
(or `--output <path>` for a custom location).

---

## Inline suppression

```python
x = self.env.cr.execute(f"SELECT ...")  # odoo-doctor: disable=raw-sql-string-interpolation
```

```xml
<record id="my_record" model="ir.ui.view">  <!-- odoo-doctor: disable=duplicate-xml-id -->
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Clean — no triggered thresholds |
| `1` | Findings at or above `--fail-on` severity |
| `2` | One or more modules score below `--min-score` |
| `3` | Invalid argument, out-of-range `--min-score`, or git/ref failure |

`odoo-doctor history show --max-drop N` also exits `2` when the score regressed.

---

## Development

```bash
git clone https://github.com/minhhq-a1/odoo-doctor
cd odoo-doctor
pip install -e ".[dev]"
pytest                    # 492 test cases
pytest --cov=odoo_doctor  # with coverage
```
