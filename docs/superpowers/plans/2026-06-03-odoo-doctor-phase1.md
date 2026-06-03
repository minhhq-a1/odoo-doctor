# Odoo Doctor Phase 1 — Core + Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core diagnostic engine, backend adapters (Pylint-Odoo + Ruff), scoring system, and CLI so that `odoo-doctor scan ./addons/my_module` produces a health score with categorized findings.

**Architecture:** Aggregator-first — orchestrate existing lint tools (Pylint-Odoo, Ruff) via backend adapters that normalize their output into a unified `Diagnostic` schema. A diagnostic pipeline deduplicates, filters, and gates by Odoo version. A scoring engine computes a 0-100 health score per module. The CLI renders results to terminal or JSON.

**Tech Stack:** Python 3.10+, stdlib `ast`, `lxml`, `tomllib` (stdlib 3.11+ / `tomli` fallback), `click` for CLI, `pytest` for testing.

---

## File Structure

```
odoo-doctor/
├── pyproject.toml
├── src/
│   └── odoo_doctor/
│       ├── __init__.py
│       ├── __main__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── models.py            # Diagnostic, CategoryScore, ScanResult
│       │   ├── constants.py         # CATEGORIES, TIERS, LABELS, TIER_IMPACT
│       │   ├── config.py            # load_config(), OdooDoctorConfig
│       │   ├── discovery.py         # discover_modules(), detect_odoo_version()
│       │   ├── pipeline.py          # DiagnosticPipeline (dedup, filter, version gate)
│       │   └── scoring.py           # ScoreCalculator
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py              # BackendAdapter protocol
│       │   ├── pylint_odoo.py       # PylintOdooAdapter
│       │   ├── ruff_adapter.py      # RuffAdapter
│       │   └── mappings/
│       │       ├── pylint_odoo.toml
│       │       └── ruff.toml
│       └── cli/
│           ├── __init__.py
│           ├── app.py               # click CLI (scan, rules, explain, init)
│           ├── terminal_renderer.py # human-readable output
│           └── json_reporter.py     # JSON output
├── tests/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_models.py
│   │   ├── test_config.py
│   │   ├── test_discovery.py
│   │   ├── test_pipeline.py
│   │   └── test_scoring.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── test_pylint_odoo.py
│   │   └── test_ruff_adapter.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── test_app.py
│   └── fixtures/
│       ├── sample_module/
│       │   ├── __manifest__.py
│       │   ├── __init__.py
│       │   ├── models/
│       │   │   ├── __init__.py
│       │   │   └── sale.py
│       │   ├── views/
│       │   │   └── sale_views.xml
│       │   └── security/
│       │       └── ir.model.access.csv
│       ├── pylint_output.json
│       └── ruff_output.json
└── odoo-doctor.toml                 # example config
```

---

### Task 1: Project Skeleton + Diagnostic Model

**Files:**
- Create: `pyproject.toml`
- Create: `src/odoo_doctor/__init__.py`
- Create: `src/odoo_doctor/__main__.py`
- Create: `src/odoo_doctor/core/__init__.py`
- Create: `src/odoo_doctor/core/models.py`
- Create: `src/odoo_doctor/core/constants.py`
- Test: `tests/__init__.py`
- Test: `tests/core/__init__.py`
- Test: `tests/core/test_models.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "odoo-doctor"
version = "0.1.0"
description = "Unified health scoring for Odoo modules"
requires-python = ">=3.10"
license = "MIT"
dependencies = [
    "click>=8.0",
    "lxml>=4.9",
    "tomli>=2.0; python_version < '3.11'",
]

[project.scripts]
odoo-doctor = "odoo_doctor.cli.app:main"

[tool.hatch.build.targets.wheel]
packages = ["src/odoo_doctor"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]
```

- [ ] **Step 2: Write failing tests for Diagnostic model**

Create `tests/__init__.py` (empty), `tests/core/__init__.py` (empty), then `tests/core/test_models.py`:

```python
from odoo_doctor.core.models import Diagnostic


def test_diagnostic_creation():
    diag = Diagnostic(
        module="sale_custom",
        file_path="models/sale.py",
        line=42,
        column=0,
        rule="no-sql-injection",
        category="Security",
        severity="error",
        source="native",
        title="SQL injection via string formatting",
        message="Use parameterized queries instead of string formatting in cr.execute()",
        help="Replace cr.execute('SELECT * FROM %s' % table) with cr.execute('SELECT * FROM %s', (table,))",
        url=None,
        odoo_version="17.0",
    )
    assert diag.module == "sale_custom"
    assert diag.severity == "error"
    assert diag.source == "native"


def test_diagnostic_is_frozen():
    diag = Diagnostic(
        module="sale_custom",
        file_path="models/sale.py",
        line=42,
        column=0,
        rule="no-sql-injection",
        category="Security",
        severity="error",
        source="native",
        title="SQL injection",
        message="detail",
        help="fix it",
        url=None,
        odoo_version="17.0",
    )
    try:
        diag.module = "other"
        assert False, "Should not allow mutation"
    except AttributeError:
        pass


def test_diagnostic_identity():
    """Two diagnostics at same location+category should have same identity for dedup."""
    from odoo_doctor.core.models import diagnostic_identity

    diag = Diagnostic(
        module="sale_custom",
        file_path="models/sale.py",
        line=42,
        column=0,
        rule="no-sql-injection",
        category="Security",
        severity="error",
        source="native",
        title="SQL injection",
        message="detail",
        help="fix it",
        url=None,
        odoo_version="17.0",
    )
    identity = diagnostic_identity(diag)
    assert identity == "models/sale.py::42::Security"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd ~/odoo-doctor && pip install -e ".[dev]" --break-system-packages && pytest tests/core/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'odoo_doctor'`

- [ ] **Step 4: Implement models and constants**

Create `src/odoo_doctor/__init__.py`:

```python
"""Odoo Doctor — unified health scoring for Odoo modules."""
```

Create `src/odoo_doctor/__main__.py`:

```python
from odoo_doctor.cli.app import main

if __name__ == "__main__":
    main()
```

Create `src/odoo_doctor/core/__init__.py`:

```python
"""Core diagnostic engine."""
```

Create `src/odoo_doctor/core/constants.py`:

```python
"""Constants for categories, tiers, scoring, and labels."""

CATEGORIES = (
    "Security",
    "Correctness",
    "Performance",
    "Data Integrity",
    "Architecture",
    "UX",
    "Module Hygiene",
    "Multi-company",
)

TIER_IMPACT = {
    "P0": 25,
    "P1": 10,
    "P2": 4,
    "P3": 1,
}

TIERS = tuple(TIER_IMPACT.keys())

SCORE_LABELS = {
    (90, 101): "Excellent",
    (75, 90): "Good",
    (50, 75): "Needs work",
    (0, 50): "Critical",
}

SCORE_COLORS = {
    "Excellent": "green",
    "Good": "blue",
    "Needs work": "yellow",
    "Critical": "red",
}

PERFECT_SCORE = 100

MIN_BLEND_WEIGHT = 0.4
AVG_BLEND_WEIGHT = 0.6
```

Create `src/odoo_doctor/core/models.py`:

```python
"""Core data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostic:
    module: str
    file_path: str
    line: int
    column: int
    rule: str
    category: str
    severity: str
    source: str
    title: str
    message: str
    help: str
    url: str | None
    odoo_version: str


def diagnostic_identity(diag: Diagnostic) -> str:
    """Deterministic identity for deduplication.

    Two diagnostics at the same file+line+category are considered
    duplicates (likely the same issue caught by multiple tools).
    """
    return f"{diag.file_path}::{diag.line}::{diag.category}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/odoo-doctor && pip install -e ".[dev]" --break-system-packages && pytest tests/core/test_models.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "feat: project skeleton with Diagnostic model and constants"
```

---

### Task 2: Config Loading

**Files:**
- Create: `src/odoo_doctor/core/config.py`
- Create: `odoo-doctor.toml` (example config)
- Test: `tests/core/test_config.py`

- [ ] **Step 1: Write failing tests for config**

Create `tests/core/test_config.py`:

```python
import os
from pathlib import Path

from odoo_doctor.core.config import load_config, OdooDoctorConfig


def test_default_config():
    """When no config file exists, return defaults."""
    config = load_config(Path("/nonexistent/path"))
    assert config.odoo_version is None
    assert config.min_score == 0
    assert config.adapters.pylint_odoo is True
    assert config.adapters.ruff is True
    assert config.adapters.oca_precommit is False
    assert config.ignore_rules == []
    assert config.ignore_files == []
    assert config.ignore_modules == []
    assert config.severity_overrides == {}
    assert config.category_weights == {}


def test_load_config_from_toml(tmp_path: Path):
    """Load config from a TOML file."""
    config_file = tmp_path / "odoo-doctor.toml"
    config_file.write_text(
        '[odoo-doctor]\n'
        'odoo_version = "17.0"\n'
        'min_score = 60\n'
        '\n'
        '[adapters]\n'
        'pylint_odoo = true\n'
        'ruff = false\n'
        'oca_precommit = false\n'
        '\n'
        '[ignore]\n'
        'rules = ["no-deprecated-widget"]\n'
        'files = ["**/migrations/**"]\n'
        'modules = ["base_setup"]\n'
        '\n'
        '[severity]\n'
        '"missing-ondelete" = "warning"\n'
        '"no-search-in-loop" = "off"\n'
        '\n'
        '[category_weights]\n'
        'Performance = 1.5\n'
        'Architecture = 0.5\n'
    )
    config = load_config(tmp_path)
    assert config.odoo_version == "17.0"
    assert config.min_score == 60
    assert config.adapters.ruff is False
    assert config.ignore_rules == ["no-deprecated-widget"]
    assert config.ignore_files == ["**/migrations/**"]
    assert config.ignore_modules == ["base_setup"]
    assert config.severity_overrides == {
        "missing-ondelete": "warning",
        "no-search-in-loop": "off",
    }
    assert config.category_weights == {
        "Performance": 1.5,
        "Architecture": 0.5,
    }


def test_severity_off_means_disabled():
    """A rule with severity 'off' should be treated as disabled."""
    config = load_config(Path("/nonexistent"))
    assert config.is_rule_disabled("some-rule") is False

    # We'll test this with a real config in the next test
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement config loading**

Create `src/odoo_doctor/core/config.py`:

```python
"""Configuration loading from odoo-doctor.toml."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore[assignment]

CONFIG_FILENAME = "odoo-doctor.toml"


@dataclass(frozen=True)
class AdapterConfig:
    pylint_odoo: bool = True
    ruff: bool = True
    oca_precommit: bool = False


@dataclass(frozen=True)
class OdooDoctorConfig:
    odoo_version: str | None = None
    min_score: int = 0
    adapters: AdapterConfig = field(default_factory=AdapterConfig)
    ignore_rules: list[str] = field(default_factory=list)
    ignore_files: list[str] = field(default_factory=list)
    ignore_modules: list[str] = field(default_factory=list)
    severity_overrides: dict[str, str] = field(default_factory=dict)
    category_weights: dict[str, float] = field(default_factory=dict)

    def is_rule_disabled(self, rule: str) -> bool:
        return self.severity_overrides.get(rule) == "off"

    def get_severity_override(self, rule: str) -> str | None:
        override = self.severity_overrides.get(rule)
        if override == "off":
            return None
        return override


def load_config(search_dir: Path) -> OdooDoctorConfig:
    """Load config from odoo-doctor.toml, searching upward from search_dir.

    Returns default config if no file is found or tomllib is unavailable.
    """
    config_path = _find_config_file(search_dir)
    if config_path is None or tomllib is None:
        return OdooDoctorConfig()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    main = raw.get("odoo-doctor", {})
    adapters_raw = raw.get("adapters", {})
    ignore_raw = raw.get("ignore", {})
    severity_raw = raw.get("severity", {})
    weights_raw = raw.get("category_weights", {})

    adapters = AdapterConfig(
        pylint_odoo=adapters_raw.get("pylint_odoo", True),
        ruff=adapters_raw.get("ruff", True),
        oca_precommit=adapters_raw.get("oca_precommit", False),
    )

    return OdooDoctorConfig(
        odoo_version=main.get("odoo_version"),
        min_score=main.get("min_score", 0),
        adapters=adapters,
        ignore_rules=ignore_raw.get("rules", []),
        ignore_files=ignore_raw.get("files", []),
        ignore_modules=ignore_raw.get("modules", []),
        severity_overrides=dict(severity_raw),
        category_weights={k: float(v) for k, v in weights_raw.items()},
    )


def _find_config_file(search_dir: Path) -> Path | None:
    """Walk upward from search_dir to find odoo-doctor.toml."""
    current = search_dir.resolve()
    for _ in range(50):  # safety cap
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Create example config file**

Create `odoo-doctor.toml`:

```toml
[odoo-doctor]
# odoo_version = "17.0"  # auto-detected from __manifest__.py if omitted
# min_score = 60          # warn in PR comment if score drops below this

[adapters]
pylint_odoo = true
ruff = true
oca_precommit = false

[ignore]
rules = []
files = ["**/migrations/**", "**/tests/**"]
modules = []

[severity]
# "rule-name" = "warning"   # override severity
# "rule-name" = "off"       # disable a rule

[category_weights]
# Performance = 1.5   # amplify findings in this category
# Architecture = 0.5  # de-emphasize during migration
```

- [ ] **Step 6: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "feat: config loading from odoo-doctor.toml"
```

---

### Task 3: Module Discovery & Version Detection

**Files:**
- Create: `src/odoo_doctor/core/discovery.py`
- Create: `tests/fixtures/sample_module/__manifest__.py`
- Create: `tests/fixtures/sample_module/__init__.py`
- Create: `tests/fixtures/sample_module/models/__init__.py`
- Create: `tests/fixtures/sample_module/models/sale.py`
- Test: `tests/core/test_discovery.py`

- [ ] **Step 1: Create test fixtures**

Create `tests/fixtures/sample_module/__manifest__.py`:

```python
{
    "name": "Sale Custom",
    "version": "17.0.1.0.0",
    "depends": ["sale", "stock"],
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/sale_views.xml",
    ],
}
```

Create `tests/fixtures/sample_module/__init__.py`:

```python
from . import models
```

Create `tests/fixtures/sample_module/models/__init__.py`:

```python
from . import sale
```

Create `tests/fixtures/sample_module/models/sale.py`:

```python
from odoo import models, fields, api


class SaleOrderCustom(models.Model):
    _inherit = "sale.order"

    custom_field = fields.Char(string="Custom")
```

- [ ] **Step 2: Write failing tests for discovery**

Create `tests/core/test_discovery.py`:

```python
from pathlib import Path

from odoo_doctor.core.discovery import (
    discover_modules,
    detect_odoo_version,
    parse_manifest,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_manifest():
    manifest = parse_manifest(FIXTURES / "sample_module" / "__manifest__.py")
    assert manifest["name"] == "Sale Custom"
    assert manifest["version"] == "17.0.1.0.0"
    assert "sale" in manifest["depends"]


def test_detect_odoo_version_from_manifest():
    manifest = {"version": "17.0.1.0.0"}
    assert detect_odoo_version(manifest) == "17.0"


def test_detect_odoo_version_short_format():
    manifest = {"version": "1.0.0"}
    assert detect_odoo_version(manifest) is None


def test_detect_odoo_version_16():
    manifest = {"version": "16.0.2.1.0"}
    assert detect_odoo_version(manifest) == "16.0"


def test_detect_odoo_version_missing():
    manifest = {}
    assert detect_odoo_version(manifest) is None


def test_discover_modules(tmp_path: Path):
    """Discover modules by finding __manifest__.py files."""
    # Create two modules
    mod_a = tmp_path / "mod_a"
    mod_a.mkdir()
    (mod_a / "__manifest__.py").write_text("{'name': 'A', 'version': '17.0.1.0.0', 'depends': []}")
    (mod_a / "__init__.py").write_text("")

    mod_b = tmp_path / "mod_b"
    mod_b.mkdir()
    (mod_b / "__manifest__.py").write_text("{'name': 'B', 'version': '16.0.1.0.0', 'depends': ['mod_a']}")
    (mod_b / "__init__.py").write_text("")

    # Non-module directory should be ignored
    (tmp_path / "not_a_module").mkdir()
    (tmp_path / "not_a_module" / "random.py").write_text("")

    modules = discover_modules(tmp_path)
    assert len(modules) == 2
    names = {m.name for m in modules}
    assert names == {"mod_a", "mod_b"}


def test_discover_modules_respects_ignore(tmp_path: Path):
    mod_a = tmp_path / "mod_a"
    mod_a.mkdir()
    (mod_a / "__manifest__.py").write_text("{'name': 'A', 'version': '17.0.1.0.0', 'depends': []}")
    (mod_a / "__init__.py").write_text("")

    modules = discover_modules(tmp_path, ignore_modules=["mod_a"])
    assert len(modules) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/core/test_discovery.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement discovery**

Create `src/odoo_doctor/core/discovery.py`:

```python
"""Module discovery and version detection."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

VERSION_PATTERN = re.compile(r"^(\d+\.\d+)\.\d+\.\d+\.\d+$")


@dataclass
class DiscoveredModule:
    name: str
    path: Path
    manifest: dict
    odoo_version: str | None


def parse_manifest(manifest_path: Path) -> dict:
    """Parse __manifest__.py (or __openerp__.py) as a Python dict literal."""
    source = manifest_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(manifest_path), mode="eval")
    return ast.literal_eval(tree.body)


def detect_odoo_version(manifest: dict) -> str | None:
    """Extract Odoo series from manifest version string.

    Odoo modules use the format '<series>.<module_version>'
    e.g. '17.0.1.0.0' -> '17.0', '16.0.2.1.0' -> '16.0'.
    Short version strings like '1.0.0' indicate no Odoo series prefix.
    """
    version = manifest.get("version", "")
    match = VERSION_PATTERN.match(version)
    if match is None:
        return None
    series = match.group(1)
    major = int(series.split(".")[0])
    if major < 8:
        return None
    return series


def discover_modules(
    search_dir: Path,
    ignore_modules: list[str] | None = None,
) -> list[DiscoveredModule]:
    """Find all Odoo modules under search_dir.

    A directory is an Odoo module if it contains __manifest__.py
    (or __openerp__.py for Odoo <= 9).
    """
    ignored = set(ignore_modules or [])
    modules: list[DiscoveredModule] = []

    if not search_dir.is_dir():
        return modules

    # Check if search_dir itself is a module
    manifest_path = _find_manifest(search_dir)
    if manifest_path is not None:
        mod = _build_module(search_dir, manifest_path, ignored)
        if mod is not None:
            return [mod]

    # Otherwise scan immediate children (addons directory convention)
    for child in sorted(search_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        manifest_path = _find_manifest(child)
        if manifest_path is None:
            continue
        mod = _build_module(child, manifest_path, ignored)
        if mod is not None:
            modules.append(mod)

    return modules


def _find_manifest(directory: Path) -> Path | None:
    for name in ("__manifest__.py", "__openerp__.py"):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _build_module(
    module_dir: Path,
    manifest_path: Path,
    ignored: set[str],
) -> DiscoveredModule | None:
    name = module_dir.name
    if name in ignored:
        return None
    try:
        manifest = parse_manifest(manifest_path)
    except (SyntaxError, ValueError):
        return None
    odoo_version = detect_odoo_version(manifest)
    return DiscoveredModule(
        name=name,
        path=module_dir,
        manifest=manifest,
        odoo_version=odoo_version,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/core/test_discovery.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "feat: module discovery and Odoo version detection"
```

---

### Task 4: Scoring Engine

**Files:**
- Create: `src/odoo_doctor/core/scoring.py`
- Test: `tests/core/test_scoring.py`

- [ ] **Step 1: Write failing tests for scoring**

Create `tests/core/test_scoring.py`:

```python
from odoo_doctor.core.models import Diagnostic
from odoo_doctor.core.scoring import ScoreCalculator, ModuleScore


def _make_diag(
    rule: str = "test-rule",
    category: str = "Security",
    severity: str = "error",
    tier: str = "P1",
) -> Diagnostic:
    return Diagnostic(
        module="test",
        file_path="models/test.py",
        line=1,
        column=0,
        rule=rule,
        category=category,
        severity=severity,
        source="native",
        title="Test",
        message="test message",
        help="fix it",
        url=None,
        odoo_version="17.0",
    )


def test_perfect_score_no_diagnostics():
    calc = ScoreCalculator(tier_map={}, category_weights={})
    result = calc.calculate([], "test_module")
    assert result.overall_score == 100
    assert result.label == "Excellent"


def test_single_p0_drops_to_75():
    tier_map = {"no-sql-injection": "P0"}
    calc = ScoreCalculator(tier_map=tier_map, category_weights={})
    diags = [_make_diag(rule="no-sql-injection", category="Security")]
    result = calc.calculate(diags, "test_module")
    assert result.overall_score == 75


def test_two_p0_drops_to_50():
    tier_map = {"rule-a": "P0", "rule-b": "P0"}
    calc = ScoreCalculator(tier_map=tier_map, category_weights={})
    diags = [
        _make_diag(rule="rule-a", category="Security"),
        _make_diag(rule="rule-b", category="Security"),
    ]
    result = calc.calculate(diags, "test_module")
    assert result.overall_score == 50


def test_score_never_below_zero():
    tier_map = {f"rule-{i}": "P0" for i in range(10)}
    calc = ScoreCalculator(tier_map=tier_map, category_weights={})
    diags = [_make_diag(rule=f"rule-{i}") for i in range(10)]
    result = calc.calculate(diags, "test_module")
    assert result.overall_score == 0


def test_category_weight_amplifies_impact():
    tier_map = {"perf-rule": "P1"}  # base impact = 10
    weights = {"Performance": 1.5}  # amplified to 15
    calc = ScoreCalculator(tier_map=tier_map, category_weights=weights)
    diags = [_make_diag(rule="perf-rule", category="Performance")]
    result = calc.calculate(diags, "test_module")
    # 100 - 15 = 85
    assert result.overall_score == 85


def test_unknown_rule_defaults_to_p3():
    calc = ScoreCalculator(tier_map={}, category_weights={})
    diags = [_make_diag(rule="unknown-rule")]
    result = calc.calculate(diags, "test_module")
    # P3 = 1 point, 100 - 1 = 99
    assert result.overall_score == 99


def test_overall_blend_penalizes_worst_category():
    """Overall = 0.4 * min(categories) + 0.6 * avg(categories)."""
    tier_map = {"sec-rule": "P0", "perf-rule": "P3"}
    calc = ScoreCalculator(tier_map=tier_map, category_weights={})
    diags = [
        _make_diag(rule="sec-rule", category="Security"),
        _make_diag(rule="perf-rule", category="Performance"),
    ]
    result = calc.calculate(diags, "test_module")
    # Security sub-score: 100 - 25 = 75
    # Performance sub-score: 100 - 1 = 99
    # Other 6 categories: 100 each
    # min = 75, avg = (75 + 99 + 100*6) / 8 = 96.75
    # overall = 0.4 * 75 + 0.6 * 96.75 = 30 + 58.05 = 88.05 -> 88
    assert result.overall_score == 88
    assert len(result.category_scores) == 8


def test_score_labels():
    calc = ScoreCalculator(tier_map={}, category_weights={})
    assert calc.calculate([], "m").label == "Excellent"  # 100

    tier_map = {"r": "P1"}
    calc2 = ScoreCalculator(tier_map=tier_map, category_weights={})
    diags = [_make_diag(rule="r")]
    result = calc2.calculate(diags, "m")
    # 100 - 10 = 90 for Security
    # blend: 0.4*90 + 0.6*(90 + 7*100)/8 = 36 + 0.6*98.75 = 36 + 59.25 = 95
    assert result.label == "Excellent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_scoring.py -v`
Expected: FAIL

- [ ] **Step 3: Implement scoring**

Create `src/odoo_doctor/core/scoring.py`:

```python
"""Health score calculator."""

from __future__ import annotations

from dataclasses import dataclass, field

from odoo_doctor.core.constants import (
    CATEGORIES,
    MIN_BLEND_WEIGHT,
    AVG_BLEND_WEIGHT,
    PERFECT_SCORE,
    SCORE_LABELS,
    TIER_IMPACT,
)
from odoo_doctor.core.models import Diagnostic


@dataclass(frozen=True)
class CategoryScore:
    category: str
    score: int
    error_count: int
    warning_count: int


@dataclass(frozen=True)
class ModuleScore:
    module: str
    overall_score: int
    label: str
    category_scores: list[CategoryScore]
    total_diagnostics: int


class ScoreCalculator:
    def __init__(
        self,
        tier_map: dict[str, str],
        category_weights: dict[str, float],
    ) -> None:
        self._tier_map = tier_map
        self._category_weights = category_weights

    def calculate(self, diagnostics: list[Diagnostic], module_name: str) -> ModuleScore:
        category_diags: dict[str, list[Diagnostic]] = {cat: [] for cat in CATEGORIES}

        for diag in diagnostics:
            bucket = category_diags.get(diag.category)
            if bucket is not None:
                bucket.append(diag)
            else:
                category_diags.setdefault("Module Hygiene", []).append(diag)

        category_scores: list[CategoryScore] = []
        for cat in CATEGORIES:
            diags = category_diags[cat]
            weight = self._category_weights.get(cat, 1.0)
            total_impact = 0.0
            errors = 0
            warnings = 0
            for d in diags:
                tier = self._tier_map.get(d.rule, "P3")
                impact = TIER_IMPACT.get(tier, TIER_IMPACT["P3"])
                total_impact += impact * weight
                if d.severity == "error":
                    errors += 1
                else:
                    warnings += 1
            sub_score = max(0, int(PERFECT_SCORE - total_impact))
            category_scores.append(CategoryScore(
                category=cat,
                score=sub_score,
                error_count=errors,
                warning_count=warnings,
            ))

        scores = [cs.score for cs in category_scores]
        if scores:
            min_score = min(scores)
            avg_score = sum(scores) / len(scores)
            overall = int(MIN_BLEND_WEIGHT * min_score + AVG_BLEND_WEIGHT * avg_score)
        else:
            overall = PERFECT_SCORE

        overall = max(0, min(PERFECT_SCORE, overall))
        label = _score_to_label(overall)

        return ModuleScore(
            module=module_name,
            overall_score=overall,
            label=label,
            category_scores=category_scores,
            total_diagnostics=len(diagnostics),
        )


def _score_to_label(score: int) -> str:
    for (low, high), label in SCORE_LABELS.items():
        if low <= score < high:
            return label
    return "Critical"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_scoring.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "feat: scoring engine with tier-based impact and category blending"
```

---

### Task 5: Diagnostic Pipeline (dedup, filter, version gate)

**Files:**
- Create: `src/odoo_doctor/core/pipeline.py`
- Test: `tests/core/test_pipeline.py`

- [ ] **Step 1: Write failing tests for pipeline**

Create `tests/core/test_pipeline.py`:

```python
from odoo_doctor.core.models import Diagnostic
from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.pipeline import DiagnosticPipeline


def _make_diag(
    rule: str = "test-rule",
    category: str = "Security",
    severity: str = "error",
    source: str = "native",
    file_path: str = "models/sale.py",
    line: int = 42,
    message: str = "short",
    odoo_version: str = "17.0",
) -> Diagnostic:
    return Diagnostic(
        module="test",
        file_path=file_path,
        line=line,
        column=0,
        rule=rule,
        category=category,
        severity=severity,
        source=source,
        title="Test",
        message=message,
        help="fix it",
        url=None,
        odoo_version=odoo_version,
    )


def test_passthrough_no_filters():
    config = OdooDoctorConfig()
    pipeline = DiagnosticPipeline(config)
    diags = [_make_diag()]
    result = pipeline.apply(diags)
    assert len(result) == 1


def test_dedup_same_location_same_category():
    """Two diagnostics at same file+line+category: keep the longer message."""
    config = OdooDoctorConfig()
    pipeline = DiagnosticPipeline(config)
    diags = [
        _make_diag(source="pylint-odoo", message="short msg"),
        _make_diag(source="native", message="a much longer and more detailed message"),
    ]
    result = pipeline.apply(diags)
    assert len(result) == 1
    assert result[0].source == "native"


def test_dedup_same_location_different_category():
    """Two diagnostics at same file+line but different categories: keep both."""
    config = OdooDoctorConfig()
    pipeline = DiagnosticPipeline(config)
    diags = [
        _make_diag(category="Security"),
        _make_diag(category="Performance"),
    ]
    result = pipeline.apply(diags)
    assert len(result) == 2


def test_filter_ignored_rule():
    config = OdooDoctorConfig(ignore_rules=["test-rule"])
    pipeline = DiagnosticPipeline(config)
    diags = [_make_diag(rule="test-rule")]
    result = pipeline.apply(diags)
    assert len(result) == 0


def test_filter_ignored_file():
    config = OdooDoctorConfig(ignore_files=["**/migrations/**"])
    pipeline = DiagnosticPipeline(config)
    diags = [_make_diag(file_path="migrations/17.0.1/pre.py")]
    result = pipeline.apply(diags)
    assert len(result) == 0


def test_severity_override_off():
    config = OdooDoctorConfig(severity_overrides={"test-rule": "off"})
    pipeline = DiagnosticPipeline(config)
    diags = [_make_diag(rule="test-rule")]
    result = pipeline.apply(diags)
    assert len(result) == 0


def test_severity_override_changes_severity():
    config = OdooDoctorConfig(severity_overrides={"test-rule": "warning"})
    pipeline = DiagnosticPipeline(config)
    diags = [_make_diag(rule="test-rule", severity="error")]
    result = pipeline.apply(diags)
    assert len(result) == 1
    assert result[0].severity == "warning"


def test_version_gate_skips_old_rule():
    """Rule with min_version 17.0 should be skipped for Odoo 14.0 modules."""
    config = OdooDoctorConfig()
    version_gates = {"new-rule": "17.0"}
    pipeline = DiagnosticPipeline(config, version_gates=version_gates)
    diags = [_make_diag(rule="new-rule", odoo_version="14.0")]
    result = pipeline.apply(diags)
    assert len(result) == 0


def test_version_gate_keeps_matching_rule():
    config = OdooDoctorConfig()
    version_gates = {"new-rule": "17.0"}
    pipeline = DiagnosticPipeline(config, version_gates=version_gates)
    diags = [_make_diag(rule="new-rule", odoo_version="17.0")]
    result = pipeline.apply(diags)
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pipeline**

Create `src/odoo_doctor/core/pipeline.py`:

```python
"""Diagnostic pipeline: dedup, filter, severity override, version gate."""

from __future__ import annotations

import fnmatch
from dataclasses import replace

from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.models import Diagnostic, diagnostic_identity


class DiagnosticPipeline:
    def __init__(
        self,
        config: OdooDoctorConfig,
        version_gates: dict[str, str] | None = None,
    ) -> None:
        self._config = config
        self._version_gates = version_gates or {}

    def apply(self, diagnostics: list[Diagnostic]) -> list[Diagnostic]:
        filtered = self._filter(diagnostics)
        deduped = self._deduplicate(filtered)
        return deduped

    def _filter(self, diagnostics: list[Diagnostic]) -> list[Diagnostic]:
        result: list[Diagnostic] = []
        for diag in diagnostics:
            if self._should_drop(diag):
                continue
            diag = self._apply_severity_override(diag)
            if diag is None:
                continue
            result.append(diag)
        return result

    def _should_drop(self, diag: Diagnostic) -> bool:
        if diag.rule in self._config.ignore_rules:
            return True

        for pattern in self._config.ignore_files:
            if fnmatch.fnmatch(diag.file_path, pattern):
                return True

        min_version = self._version_gates.get(diag.rule)
        if min_version is not None and diag.odoo_version:
            if _version_lt(diag.odoo_version, min_version):
                return True

        return False

    def _apply_severity_override(self, diag: Diagnostic) -> Diagnostic | None:
        override = self._config.severity_overrides.get(diag.rule)
        if override is None:
            return diag
        if override == "off":
            return None
        return replace(diag, severity=override)

    def _deduplicate(self, diagnostics: list[Diagnostic]) -> list[Diagnostic]:
        groups: dict[str, list[Diagnostic]] = {}
        for diag in diagnostics:
            key = diagnostic_identity(diag)
            groups.setdefault(key, []).append(diag)

        result: list[Diagnostic] = []
        for group in groups.values():
            if len(group) == 1:
                result.append(group[0])
            else:
                best = _pick_best(group)
                result.append(best)
        return result


def _pick_best(group: list[Diagnostic]) -> Diagnostic:
    """From a group of duplicates, keep the most detailed one.

    Prefer native source, then longest message.
    """
    natives = [d for d in group if d.source == "native"]
    candidates = natives if natives else group
    return max(candidates, key=lambda d: len(d.message))


def _version_lt(version_a: str, version_b: str) -> bool:
    """Compare Odoo version strings like '14.0' < '17.0'."""
    try:
        parts_a = tuple(int(x) for x in version_a.split("."))
        parts_b = tuple(int(x) for x in version_b.split("."))
        return parts_a < parts_b
    except ValueError:
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_pipeline.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "feat: diagnostic pipeline with dedup, filters, and version gating"
```

---

### Task 6: Backend Adapter Interface + Pylint-Odoo Adapter

**Files:**
- Create: `src/odoo_doctor/adapters/__init__.py`
- Create: `src/odoo_doctor/adapters/base.py`
- Create: `src/odoo_doctor/adapters/pylint_odoo.py`
- Create: `src/odoo_doctor/adapters/mappings/pylint_odoo.toml`
- Create: `tests/fixtures/pylint_output.json`
- Test: `tests/adapters/__init__.py`
- Test: `tests/adapters/test_pylint_odoo.py`

- [ ] **Step 1: Create Pylint-Odoo fixture output**

Create `tests/fixtures/pylint_output.json`:

```json
[
    {
        "type": "convention",
        "module": "sale_custom",
        "obj": "SaleOrderCustom",
        "line": 15,
        "column": 0,
        "endLine": 15,
        "endColumn": 10,
        "path": "models/sale.py",
        "symbol": "manifest-required-key",
        "message": "Missing required key 'license' in manifest",
        "message-id": "C8101"
    },
    {
        "type": "error",
        "module": "sale_custom",
        "obj": "SaleOrderCustom.action_compute",
        "line": 42,
        "column": 8,
        "endLine": 42,
        "endColumn": 60,
        "path": "models/sale.py",
        "symbol": "sql-injection",
        "message": "SQL injection risk. Use parameters instead of string formatting",
        "message-id": "E8501"
    }
]
```

- [ ] **Step 2: Write failing tests**

Create `tests/adapters/__init__.py` (empty), then `tests/adapters/test_pylint_odoo.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from odoo_doctor.adapters.pylint_odoo import PylintOdooAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_pylint_output():
    adapter = PylintOdooAdapter()
    raw = json.loads((FIXTURES / "pylint_output.json").read_text())
    diagnostics = adapter._parse_output(raw, "sale_custom", "17.0")
    assert len(diagnostics) == 2

    sql_diag = next(d for d in diagnostics if d.rule == "sql-injection")
    assert sql_diag.category == "Security"
    assert sql_diag.severity == "error"
    assert sql_diag.source == "pylint-odoo"
    assert sql_diag.line == 42

    manifest_diag = next(d for d in diagnostics if d.rule == "manifest-required-key")
    assert manifest_diag.severity == "warning"


def test_unmapped_rule_defaults_to_uncategorized():
    adapter = PylintOdooAdapter()
    raw = [
        {
            "type": "warning",
            "module": "test",
            "obj": "",
            "line": 1,
            "column": 0,
            "endLine": 1,
            "endColumn": 0,
            "path": "test.py",
            "symbol": "totally-unknown-rule",
            "message": "Something",
            "message-id": "W9999"
        }
    ]
    diagnostics = adapter._parse_output(raw, "test", "17.0")
    assert len(diagnostics) == 1
    assert diagnostics[0].category == "Uncategorized"


def test_is_available_checks_shutil(monkeypatch):
    adapter = PylintOdooAdapter()
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert adapter.is_available() is False

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/pylint")
    assert adapter.is_available() is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/adapters/test_pylint_odoo.py -v`
Expected: FAIL

- [ ] **Step 4: Create rule mapping for Pylint-Odoo**

Create directory `src/odoo_doctor/adapters/mappings/` and file `src/odoo_doctor/adapters/mappings/pylint_odoo.toml`:

```toml
# Pylint-Odoo rule -> Odoo Doctor category + tier
# Rules not listed here default to category="Uncategorized", tier="P3"

[rules.sql-injection]
category = "Security"
tier = "P0"

[rules.manifest-required-key]
category = "Module Hygiene"
tier = "P3"

[rules.missing-return]
category = "Correctness"
tier = "P2"

[rules.attribute-deprecated]
category = "Architecture"
tier = "P2"

[rules.method-required-super]
category = "Correctness"
tier = "P1"

[rules.translation-required]
category = "UX"
tier = "P3"

[rules.except-pass]
category = "Correctness"
tier = "P2"

[rules.license-allowed]
category = "Module Hygiene"
tier = "P3"

[rules.no-utf8-coding-comment]
category = "Module Hygiene"
tier = "P3"

[rules.resource-not-exist]
category = "Correctness"
tier = "P1"

[rules.manifest-deprecated-key]
category = "Architecture"
tier = "P2"

[rules.eval-referenced]
category = "Security"
tier = "P1"
```

- [ ] **Step 5: Implement adapter base and Pylint-Odoo adapter**

Create `src/odoo_doctor/adapters/__init__.py`:

```python
"""Backend adapters for external lint tools."""
```

Create `src/odoo_doctor/adapters/base.py`:

```python
"""Backend adapter protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from odoo_doctor.core.models import Diagnostic


class BackendAdapter(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]: ...
```

Create `src/odoo_doctor/adapters/pylint_odoo.py`:

```python
"""Pylint-Odoo backend adapter."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore[assignment]

from odoo_doctor.core.models import Diagnostic

_MAPPING_PATH = Path(__file__).parent / "mappings" / "pylint_odoo.toml"
_PYLINT_SEVERITY_MAP = {
    "error": "error",
    "fatal": "error",
    "warning": "warning",
    "convention": "warning",
    "refactor": "warning",
    "info": "warning",
}


def _load_mapping() -> dict[str, dict[str, str]]:
    if tomllib is None or not _MAPPING_PATH.is_file():
        return {}
    with open(_MAPPING_PATH, "rb") as f:
        raw = tomllib.load(f)
    return raw.get("rules", {})


class PylintOdooAdapter:
    name = "pylint-odoo"

    def __init__(self) -> None:
        self._mapping = _load_mapping()

    def is_available(self) -> bool:
        return shutil.which("pylint") is not None

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        try:
            result = subprocess.run(
                [
                    "pylint",
                    "--load-plugins=pylint_odoo",
                    "--output-format=json",
                    str(module_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        if not result.stdout.strip():
            return []

        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        module_name = module_path.name
        return self._parse_output(raw, module_name, odoo_version)

    def _parse_output(
        self,
        raw: list[dict],
        module_name: str,
        odoo_version: str,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for item in raw:
            symbol = item.get("symbol", "")
            mapping = self._mapping.get(symbol, {})
            category = mapping.get("category", "Uncategorized")
            severity = _PYLINT_SEVERITY_MAP.get(item.get("type", ""), "warning")

            diagnostics.append(Diagnostic(
                module=module_name,
                file_path=item.get("path", ""),
                line=item.get("line", 0),
                column=item.get("column", 0),
                rule=symbol,
                category=category,
                severity=severity,
                source="pylint-odoo",
                title=symbol.replace("-", " ").title(),
                message=item.get("message", ""),
                help="",
                url=None,
                odoo_version=odoo_version,
            ))
        return diagnostics
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/adapters/test_pylint_odoo.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "feat: Pylint-Odoo backend adapter with rule mapping"
```

---

### Task 7: Ruff Adapter

**Files:**
- Create: `src/odoo_doctor/adapters/ruff_adapter.py`
- Create: `src/odoo_doctor/adapters/mappings/ruff.toml`
- Create: `tests/fixtures/ruff_output.json`
- Test: `tests/adapters/test_ruff_adapter.py`

- [ ] **Step 1: Create Ruff fixture output**

Create `tests/fixtures/ruff_output.json`:

```json
[
    {
        "cell": null,
        "code": "S608",
        "message": "Possible SQL injection vector through string-based query construction",
        "filename": "models/sale.py",
        "location": {"row": 42, "column": 8},
        "end_location": {"row": 42, "column": 60},
        "fix": null,
        "noqa_row": 42,
        "url": "https://docs.astral.sh/ruff/rules/hardcoded-sql-expression/"
    },
    {
        "cell": null,
        "code": "E501",
        "message": "Line too long (120 > 88)",
        "filename": "models/sale.py",
        "location": {"row": 10, "column": 89},
        "end_location": {"row": 10, "column": 120},
        "fix": null,
        "noqa_row": 10,
        "url": "https://docs.astral.sh/ruff/rules/line-too-long/"
    }
]
```

- [ ] **Step 2: Write failing tests**

Create `tests/adapters/test_ruff_adapter.py`:

```python
import json
from pathlib import Path

from odoo_doctor.adapters.ruff_adapter import RuffAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_ruff_output():
    adapter = RuffAdapter()
    raw = json.loads((FIXTURES / "ruff_output.json").read_text())
    diagnostics = adapter._parse_output(raw, "sale_custom", Path("/fake/sale_custom"), "17.0")
    assert len(diagnostics) == 2

    sql_diag = next(d for d in diagnostics if d.rule == "S608")
    assert sql_diag.category == "Security"
    assert sql_diag.severity == "error"
    assert sql_diag.source == "ruff"
    assert sql_diag.line == 42


def test_unmapped_ruff_rule():
    adapter = RuffAdapter()
    raw = [
        {
            "cell": None,
            "code": "XYZZY",
            "message": "Unknown rule",
            "filename": "test.py",
            "location": {"row": 1, "column": 0},
            "end_location": {"row": 1, "column": 10},
            "fix": None,
            "noqa_row": 1,
            "url": None,
        }
    ]
    diagnostics = adapter._parse_output(raw, "test", Path("/fake/test"), "17.0")
    assert len(diagnostics) == 1
    assert diagnostics[0].category == "Uncategorized"


def test_is_available(monkeypatch):
    adapter = RuffAdapter()
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert adapter.is_available() is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/adapters/test_ruff_adapter.py -v`
Expected: FAIL

- [ ] **Step 4: Create Ruff rule mapping**

Create `src/odoo_doctor/adapters/mappings/ruff.toml`:

```toml
# Ruff rule code -> Odoo Doctor category + tier

[rules.S608]
category = "Security"
tier = "P0"

[rules.S105]
category = "Security"
tier = "P0"

[rules.S106]
category = "Security"
tier = "P0"

[rules.S107]
category = "Security"
tier = "P0"

[rules.S101]
category = "Correctness"
tier = "P3"

[rules.E501]
category = "Module Hygiene"
tier = "P3"

[rules.F401]
category = "Module Hygiene"
tier = "P3"

[rules.F841]
category = "Module Hygiene"
tier = "P3"

[rules.B006]
category = "Correctness"
tier = "P2"

[rules.B007]
category = "Correctness"
tier = "P3"

[rules.C901]
category = "Architecture"
tier = "P2"
```

- [ ] **Step 5: Implement Ruff adapter**

Create `src/odoo_doctor/adapters/ruff_adapter.py`:

```python
"""Ruff backend adapter."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore[assignment]

from odoo_doctor.core.models import Diagnostic

_MAPPING_PATH = Path(__file__).parent / "mappings" / "ruff.toml"

# Ruff codes starting with these letters are typically errors
_ERROR_PREFIXES = {"S", "B", "F"}


def _load_mapping() -> dict[str, dict[str, str]]:
    if tomllib is None or not _MAPPING_PATH.is_file():
        return {}
    with open(_MAPPING_PATH, "rb") as f:
        raw = tomllib.load(f)
    return raw.get("rules", {})


class RuffAdapter:
    name = "ruff"

    def __init__(self) -> None:
        self._mapping = _load_mapping()

    def is_available(self) -> bool:
        return shutil.which("ruff") is not None

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        try:
            result = subprocess.run(
                [
                    "ruff",
                    "check",
                    "--output-format=json",
                    str(module_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        if not result.stdout.strip():
            return []

        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        module_name = module_path.name
        return self._parse_output(raw, module_name, module_path, odoo_version)

    def _parse_output(
        self,
        raw: list[dict],
        module_name: str,
        module_path: Path,
        odoo_version: str,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for item in raw:
            code = item.get("code", "")
            mapping = self._mapping.get(code, {})
            category = mapping.get("category", "Uncategorized")

            # Determine severity from mapping tier or code prefix
            tier = mapping.get("tier", "P3")
            if tier in ("P0", "P1"):
                severity = "error"
            elif code and code[0] in _ERROR_PREFIXES:
                severity = "error"
            else:
                severity = "warning"

            location = item.get("location", {})
            filename = item.get("filename", "")
            # Make path relative to module root
            try:
                rel_path = str(Path(filename).relative_to(module_path))
            except ValueError:
                rel_path = filename

            diagnostics.append(Diagnostic(
                module=module_name,
                file_path=rel_path,
                line=location.get("row", 0),
                column=location.get("column", 0),
                rule=code,
                category=category,
                severity=severity,
                source="ruff",
                title=code,
                message=item.get("message", ""),
                help="",
                url=item.get("url") or None,
                odoo_version=odoo_version,
            ))
        return diagnostics
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/adapters/test_ruff_adapter.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "feat: Ruff backend adapter with rule mapping"
```

---

### Task 8: CLI — scan, rules, explain, init

**Files:**
- Create: `src/odoo_doctor/cli/__init__.py`
- Create: `src/odoo_doctor/cli/app.py`
- Create: `src/odoo_doctor/cli/terminal_renderer.py`
- Create: `src/odoo_doctor/cli/json_reporter.py`
- Test: `tests/cli/__init__.py`
- Test: `tests/cli/test_app.py`

- [ ] **Step 1: Write failing tests for CLI**

Create `tests/cli/__init__.py` (empty), then `tests/cli/test_app.py`:

```python
from pathlib import Path
from click.testing import CliRunner
from odoo_doctor.cli.app import main

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_scan_single_module():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES / "sample_module")])
    assert result.exit_code == 0
    assert "sale_custom" in result.output or "Score" in result.output


def test_scan_json_output():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(FIXTURES / "sample_module"), "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert "modules" in data


def test_scan_nonexistent_path():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "/nonexistent/path"])
    assert result.exit_code != 0


def test_rules_command():
    runner = CliRunner()
    result = runner.invoke(main, ["rules"])
    assert result.exit_code == 0


def test_init_creates_config(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["init"], args=[], catch_exceptions=False)
    # init writes to cwd, so we test it can run without error
    assert result.exit_code == 0 or "already exists" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/test_app.py -v`
Expected: FAIL

- [ ] **Step 3: Implement terminal renderer**

Create `src/odoo_doctor/cli/__init__.py` (empty).

Create `src/odoo_doctor/cli/terminal_renderer.py`:

```python
"""Human-readable terminal output."""

from __future__ import annotations

import click

from odoo_doctor.core.constants import SCORE_COLORS
from odoo_doctor.core.scoring import ModuleScore


def render_module_score(score: ModuleScore) -> None:
    color = SCORE_COLORS.get(score.label, "white")
    click.echo()
    click.echo(click.style(f"  Module: {score.module}", bold=True))
    click.echo(
        f"  Score:  "
        + click.style(f"{score.overall_score}/100", fg=color, bold=True)
        + f"  ({score.label})"
    )
    click.echo(f"  Total findings: {score.total_diagnostics}")
    click.echo()

    if not score.category_scores:
        return

    for cs in score.category_scores:
        if cs.error_count == 0 and cs.warning_count == 0:
            continue
        bar = _score_bar(cs.score)
        findings = _findings_text(cs.error_count, cs.warning_count)
        click.echo(f"    {cs.category:<20s} {bar} {cs.score:>3d}/100  {findings}")

    click.echo()


def render_diagnostics(diagnostics: list, top_n: int = 5) -> None:
    if not diagnostics:
        return
    click.echo(click.style("  Top issues to fix:", bold=True))
    for i, diag in enumerate(diagnostics[:top_n], 1):
        sev = click.style("ERR", fg="red") if diag.severity == "error" else click.style("WRN", fg="yellow")
        click.echo(f"    {i}. [{sev}] {diag.rule} in {diag.file_path}:{diag.line}")
        click.echo(f"       {diag.message}")
    if len(diagnostics) > top_n:
        click.echo(f"    ... and {len(diagnostics) - top_n} more")
    click.echo()


def _score_bar(score: int, width: int = 10) -> str:
    filled = int(score / 100 * width)
    empty = width - filled
    return click.style("█" * filled, fg="green") + "░" * empty


def _findings_text(errors: int, warnings: int) -> str:
    parts = []
    if errors:
        parts.append(f"{errors} error{'s' if errors != 1 else ''}")
    if warnings:
        parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
    return ", ".join(parts) if parts else ""
```

- [ ] **Step 4: Implement JSON reporter**

Create `src/odoo_doctor/cli/json_reporter.py`:

```python
"""JSON output for CI/programmatic consumption."""

from __future__ import annotations

import json
from dataclasses import asdict

from odoo_doctor.core.models import Diagnostic
from odoo_doctor.core.scoring import ModuleScore


def build_json_report(
    modules: list[dict],
) -> str:
    """Build a JSON report from scan results.

    Each entry in modules is a dict with keys:
    - module_name: str
    - score: ModuleScore
    - diagnostics: list[Diagnostic]
    """
    output = {
        "version": "0.1.0",
        "modules": [],
    }
    for entry in modules:
        score: ModuleScore = entry["score"]
        diagnostics: list[Diagnostic] = entry["diagnostics"]
        output["modules"].append({
            "name": score.module,
            "score": score.overall_score,
            "label": score.label,
            "total_diagnostics": score.total_diagnostics,
            "categories": [
                {
                    "category": cs.category,
                    "score": cs.score,
                    "errors": cs.error_count,
                    "warnings": cs.warning_count,
                }
                for cs in score.category_scores
                if cs.error_count > 0 or cs.warning_count > 0
            ],
            "diagnostics": [asdict(d) for d in diagnostics],
        })
    return json.dumps(output, indent=2)
```

- [ ] **Step 5: Implement CLI app**

Create `src/odoo_doctor/cli/app.py`:

```python
"""CLI entry point."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click

from odoo_doctor.adapters.base import BackendAdapter
from odoo_doctor.adapters.pylint_odoo import PylintOdooAdapter
from odoo_doctor.adapters.ruff_adapter import RuffAdapter
from odoo_doctor.cli.json_reporter import build_json_report
from odoo_doctor.cli.terminal_renderer import render_diagnostics, render_module_score
from odoo_doctor.core.config import OdooDoctorConfig, load_config, CONFIG_FILENAME
from odoo_doctor.core.discovery import DiscoveredModule, discover_modules
from odoo_doctor.core.models import Diagnostic
from odoo_doctor.core.pipeline import DiagnosticPipeline
from odoo_doctor.core.scoring import ScoreCalculator


def _build_tier_map(adapters: list[BackendAdapter]) -> dict[str, str]:
    """Merge tier maps from all adapter mappings."""
    tier_map: dict[str, str] = {}
    for adapter in adapters:
        if hasattr(adapter, "_mapping"):
            for rule, info in adapter._mapping.items():
                tier = info.get("tier", "P3")
                tier_map[rule] = tier
    return tier_map


def _collect_adapters(config: OdooDoctorConfig) -> list[BackendAdapter]:
    candidates: list[tuple[bool, BackendAdapter]] = [
        (config.adapters.pylint_odoo, PylintOdooAdapter()),
        (config.adapters.ruff, RuffAdapter()),
    ]
    adapters: list[BackendAdapter] = []
    for enabled, adapter in candidates:
        if enabled and adapter.is_available():
            adapters.append(adapter)
        elif enabled:
            click.echo(
                click.style(f"  Warning: {adapter.name} not found, skipping", fg="yellow"),
                err=True,
            )
    return adapters


def _run_adapters(
    adapters: list[BackendAdapter],
    module: DiscoveredModule,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    odoo_version = module.odoo_version or ""

    with ThreadPoolExecutor(max_workers=len(adapters) or 1) as executor:
        futures = {
            executor.submit(adapter.run, module.path, odoo_version): adapter
            for adapter in adapters
        }
        for future in as_completed(futures):
            try:
                diagnostics.extend(future.result())
            except Exception:
                adapter = futures[future]
                click.echo(
                    click.style(f"  Warning: {adapter.name} failed for {module.name}", fg="yellow"),
                    err=True,
                )
    return diagnostics


def _scan_module(
    module: DiscoveredModule,
    adapters: list[BackendAdapter],
    pipeline: DiagnosticPipeline,
    scorer: ScoreCalculator,
) -> dict:
    diagnostics = _run_adapters(adapters, module)
    filtered = pipeline.apply(diagnostics)
    # Sort: errors first, then by tier impact (highest first)
    filtered.sort(key=lambda d: (0 if d.severity == "error" else 1, d.rule))
    score = scorer.calculate(filtered, module.name)
    return {
        "module_name": module.name,
        "score": score,
        "diagnostics": filtered,
    }


@click.group()
def main() -> None:
    """Odoo Doctor — unified health scoring for Odoo modules."""
    pass


@main.command()
@click.argument("directory", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True, help="Output JSON for CI")
@click.option("--diff", "diff_branch", default=None, help="Only scan files changed vs branch")
def scan(directory: str, json_output: bool, diff_branch: str | None) -> None:
    """Scan Odoo modules for issues and calculate health score."""
    target = Path(directory).resolve()
    config = load_config(target)

    modules = discover_modules(target, ignore_modules=config.ignore_modules)
    if not modules:
        click.echo(click.style("No Odoo modules found.", fg="red"), err=True)
        sys.exit(1)

    adapters = _collect_adapters(config)
    pipeline = DiagnosticPipeline(config)
    tier_map = _build_tier_map(adapters)
    scorer = ScoreCalculator(tier_map=tier_map, category_weights=config.category_weights)

    if not json_output:
        click.echo(click.style("Odoo Doctor", bold=True))
        click.echo(f"  Scanning {len(modules)} module(s)...")
        if not adapters:
            click.echo(click.style("  No adapters available — only native rules will run.", fg="yellow"))

    results: list[dict] = []
    for module in modules:
        result = _scan_module(module, adapters, pipeline, scorer)
        results.append(result)

    if json_output:
        click.echo(build_json_report(results))
    else:
        for result in results:
            render_module_score(result["score"])
            render_diagnostics(result["diagnostics"])


@main.command()
def rules() -> None:
    """List all known rules and their categories."""
    # For Phase 1, list adapter-mapped rules
    adapters = [PylintOdooAdapter(), RuffAdapter()]
    click.echo(click.style("Known rules:", bold=True))
    click.echo()
    for adapter in adapters:
        if hasattr(adapter, "_mapping"):
            click.echo(click.style(f"  {adapter.name}:", bold=True))
            for rule, info in sorted(adapter._mapping.items()):
                cat = info.get("category", "Uncategorized")
                tier = info.get("tier", "P3")
                click.echo(f"    {rule:<35s} {cat:<20s} {tier}")
            click.echo()


@main.command()
@click.argument("rule_name")
def explain(rule_name: str) -> None:
    """Explain a specific rule."""
    adapters = [PylintOdooAdapter(), RuffAdapter()]
    for adapter in adapters:
        if hasattr(adapter, "_mapping"):
            info = adapter._mapping.get(rule_name)
            if info:
                click.echo(click.style(f"Rule: {rule_name}", bold=True))
                click.echo(f"  Source:   {adapter.name}")
                click.echo(f"  Category: {info.get('category', 'Uncategorized')}")
                click.echo(f"  Tier:     {info.get('tier', 'P3')}")
                return
    click.echo(f"Rule '{rule_name}' not found.")


@main.command()
def init() -> None:
    """Create an odoo-doctor.toml config file in the current directory."""
    config_path = Path.cwd() / CONFIG_FILENAME
    if config_path.exists():
        click.echo(f"{CONFIG_FILENAME} already exists.")
        return

    template = """\
[odoo-doctor]
# odoo_version = "17.0"
# min_score = 60

[adapters]
pylint_odoo = true
ruff = true
oca_precommit = false

[ignore]
rules = []
files = ["**/migrations/**", "**/tests/**"]
modules = []

[severity]
# "rule-name" = "warning"
# "rule-name" = "off"

[category_weights]
# Performance = 1.5
# Architecture = 0.5
"""
    config_path.write_text(template)
    click.echo(f"Created {CONFIG_FILENAME}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pip install -e ".[dev]" --break-system-packages && pytest tests/cli/test_app.py -v`
Expected: 5 passed (some may skip adapter integration if pylint/ruff not installed — that's fine, the CLI gracefully handles missing tools)

- [ ] **Step 7: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "feat: CLI with scan, rules, explain, init commands"
```

---

### Task 9: End-to-End Integration Test

**Files:**
- Create: `tests/fixtures/sample_module/views/sale_views.xml`
- Create: `tests/fixtures/sample_module/security/ir.model.access.csv`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Complete test fixtures**

Create `tests/fixtures/sample_module/views/sale_views.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_sale_custom_form" model="ir.ui.view">
        <field name="name">sale.order.custom.form</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='partner_id']" position="after">
                <field name="custom_field"/>
            </xpath>
        </field>
    </record>
</odoo>
```

Create `tests/fixtures/sample_module/security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_sale_order_custom,sale.order.custom,sale.model_sale_order,base.group_user,1,1,1,0
```

- [ ] **Step 2: Write end-to-end test**

Create `tests/test_integration.py`:

```python
"""End-to-end integration test: discovery -> pipeline -> scoring -> output."""

import json
from pathlib import Path

from click.testing import CliRunner

from odoo_doctor.cli.app import main
from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.discovery import discover_modules
from odoo_doctor.core.models import Diagnostic
from odoo_doctor.core.pipeline import DiagnosticPipeline
from odoo_doctor.core.scoring import ScoreCalculator

FIXTURES = Path(__file__).parent / "fixtures"


def test_full_pipeline_with_synthetic_diagnostics():
    """Simulate the full pipeline with hand-crafted diagnostics."""
    modules = discover_modules(FIXTURES / "sample_module")
    assert len(modules) == 1
    module = modules[0]
    assert module.name == "sample_module"
    assert module.odoo_version == "17.0"

    # Simulate adapter output
    diagnostics = [
        Diagnostic(
            module="sample_module",
            file_path="models/sale.py",
            line=42,
            column=8,
            rule="sql-injection",
            category="Security",
            severity="error",
            source="pylint-odoo",
            title="SQL Injection",
            message="Use parameters instead of string formatting",
            help="Replace string formatting with %s params",
            url=None,
            odoo_version="17.0",
        ),
        Diagnostic(
            module="sample_module",
            file_path="models/sale.py",
            line=42,
            column=8,
            rule="S608",
            category="Security",
            severity="error",
            source="ruff",
            title="S608",
            message="Possible SQL injection",
            help="",
            url=None,
            odoo_version="17.0",
        ),
        Diagnostic(
            module="sample_module",
            file_path="models/sale.py",
            line=10,
            column=0,
            rule="E501",
            category="Module Hygiene",
            severity="warning",
            source="ruff",
            title="E501",
            message="Line too long",
            help="",
            url=None,
            odoo_version="17.0",
        ),
    ]

    config = OdooDoctorConfig()
    pipeline = DiagnosticPipeline(config)
    filtered = pipeline.apply(diagnostics)

    # Dedup should merge the two SQL injection findings (same file+line+category)
    assert len(filtered) == 2

    tier_map = {"sql-injection": "P0", "S608": "P0", "E501": "P3"}
    scorer = ScoreCalculator(tier_map=tier_map, category_weights={})
    score = scorer.calculate(filtered, "sample_module")

    # One P0 (25) + one P3 (1) = 26 total impact
    # Security sub-score: 75, Module Hygiene sub-score: 99
    # Others: 100. min=75, avg=(75+99+6*100)/8=96.75
    # overall = 0.4*75 + 0.6*96.75 = 30+58.05 = 88
    assert score.overall_score == 88
    assert score.label == "Good"


def test_cli_json_with_fixture_module():
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["scan", str(FIXTURES / "sample_module"), "--json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["modules"]) == 1
    assert data["modules"][0]["name"] == "sample_module"
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "test: end-to-end integration test for full pipeline"
```

---

### Task 10: Polish — README and .gitignore

**Files:**
- Modify: `README.md`
- Create: `.gitignore`

- [ ] **Step 1: Update README**

Write `README.md`:

```markdown
# Odoo Doctor

Unified health scoring for Odoo modules. Aggregates findings from Pylint-Odoo, Ruff, and native cross-file rules into a single 0-100 health score.

## Install

```bash
pip install odoo-doctor
```

## Usage

```bash
# Scan a single module
odoo-doctor scan ./addons/sale_custom

# Scan all modules in a directory
odoo-doctor scan ./addons

# JSON output for CI
odoo-doctor scan ./addons --json

# List known rules
odoo-doctor rules

# Explain a rule
odoo-doctor explain sql-injection

# Create config file
odoo-doctor init
```

## Configuration

Create `odoo-doctor.toml` in your repo root:

```toml
[odoo-doctor]
odoo_version = "17.0"
min_score = 60

[adapters]
pylint_odoo = true
ruff = true

[ignore]
rules = []
files = ["**/migrations/**", "**/tests/**"]

[severity]
# "rule-name" = "off"
```

## Scoring

Each finding has an impact tier:

- **P0** (25 pts): Critical — SQL injection, missing access rules
- **P1** (10 pts): Serious — N+1 queries, broken inheritance
- **P2** (4 pts): Moderate — deprecated API, missing ondelete
- **P3** (1 pt): Minor — style issues, manifest warnings

Score = `max(0, 100 - total_impact)`. Categories are blended: `0.4 * worst_category + 0.6 * average`.
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/
*.egg
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.so
.venv/
venv/
```

- [ ] **Step 3: Commit**

```bash
cd ~/odoo-doctor
git add -A
git commit -m "docs: README with usage and scoring explanation"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Diagnostic schema with all fields including `source`
- ✅ Config loading from `odoo-doctor.toml` with all sections
- ✅ Module discovery + version detection
- ✅ Scoring with tier impact, category sub-scores, blend formula, labels
- ✅ Diagnostic pipeline: dedup, ignore rules/files, severity overrides, version gating
- ✅ Backend adapter protocol + PylintOdooAdapter + RuffAdapter
- ✅ Rule mapping TOML configs
- ✅ CLI: scan, rules, explain, init
- ✅ JSON output
- ✅ Terminal renderer
- ⏭ ModuleContext — Phase 2 (native rules need this)
- ⏭ Native rules — Phase 2
- ⏭ Inline suppression — Phase 2
- ⏭ GitHub Action — Phase 3
- ⏭ PR comment renderer — Phase 3
- ⏭ Diff mode — Phase 3

**Placeholder scan:** No TBD, TODO, or vague steps. All code blocks are complete.

**Type consistency:** `Diagnostic`, `OdooDoctorConfig`, `ModuleScore`, `CategoryScore`, `DiscoveredModule`, `DiagnosticPipeline`, `ScoreCalculator` — names and signatures consistent across all tasks.
