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

Plus Ruff and Pylint-Odoo findings when those tools are installed.

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
  uses: minhhq-a1/odoo-doctor@v0.3.0
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

Use `odoo-doctor rules explain <rule-name>` to understand any finding.

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

---

## Development

```bash
git clone https://github.com/minhhq-a1/odoo-doctor
cd odoo-doctor
pip install -e ".[dev]"
pytest                    # 324+ test cases
pytest --cov=odoo_doctor  # with coverage
```
