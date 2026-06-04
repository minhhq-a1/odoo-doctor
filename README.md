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

Plus Ruff and Pylint-Odoo findings when those tools are installed.

---

## Score explained

```
overall = 0.4 × min(category_scores) + 0.6 × avg(category_scores)
```

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
```

---

## CI Integration

### GitHub Actions

```yaml
- name: Odoo Doctor
  run: |
    pip install odoo-doctor
    odoo-doctor scan . --min-score 75 --fail-on error
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

---

## Development

```bash
git clone https://github.com/minhhq-a1/odoo-doctor
cd odoo-doctor
pip install -e ".[dev]"
pytest                    # 154+ tests
pytest --cov=odoo_doctor  # with coverage
```
