# Odoo Doctor MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Odoo Doctor MVP — a Python CLI producing a unified health score (0–100) per Odoo addon by combining confidence-aware graph analysis with optional external lint adapters.

**Architecture:** Diagnostic-contract-first pipeline. All findings (10 native graph rules + Ruff/Pylint-Odoo adapters) normalize into a shared `Diagnostic` dataclass, flow through a 7-stage pipeline, and produce a local health score. The confidence-aware resolver (repo → stubs → optional source path → UNKNOWN) ensures low false positives.

**Tech Stack:** Python 3.10+, typer, rich, lxml, stdlib `ast` + `tokenize`, tomllib/tomli, pytest

**Spec:** `docs/superpowers/specs/2026-06-03-odoo-doctor-design-v3.md`

**Corrections from review:** This plan incorporates the final pre-implementation review findings:

- Resolver `UNKNOWN` does not emit error diagnostics in normal scan mode. UNKNOWN may only appear as `info` diagnostics in a future verbose mode.
- `unknown-model-in-access-csv` is high-confidence only when the CSV model external ID is owned by the scanned module and the corresponding model is absent from the project graph.
- Duplicate XML ID detection uses a full XML record occurrence list, not the deduplicated `xml_ids` map.
- Resolver stubs use the detected project Odoo version when CLI/config version is unknown.
- CLI path precedence is explicit: positional `scan PATH` chooses the config root; config `addons_paths` are resolved from that root unless explicit CLI paths are added later; `--module` filters target modules.
- Raw SQL detection handles direct interpolation and simple variable indirection inside the same function.

---

## File Structure

Every file listed below will be created during this plan. Files are grouped by responsibility.

```text
odoo-doctor/
  pyproject.toml
  src/odoo_doctor/
    __init__.py                          # package version
    core/
      __init__.py
      diagnostics.py                     # Diagnostic dataclass, constants
      pipeline.py                        # 7 pipeline stages
      scoring.py                         # ScoreResult, score_diagnostics()
      config.py                          # OdooDoctorConfig, load_config()
    discovery/
      __init__.py
      addons.py                          # discover_addons()
      odoo_version.py                    # detect_odoo_version()
    parsers/
      __init__.py
      manifest.py                        # parse_manifest()
      python_models.py                   # parse_models(), parse_controllers()
      xml_records.py                     # parse_xml_records(), parse_views()
      security_csv.py                    # parse_access_csv()
    graph/
      __init__.py
      module_context.py                  # ModuleContext, ProjectGraph
      resolver.py                        # SymbolResolver, ResolveResult
      stubs/
        __init__.py
        loader.py                        # load_stubs()
        build_stubs.py                   # offline script
        data/                            # generated JSON per version
    adapters/
      __init__.py
      base.py                            # BackendAdapter protocol
      ruff/
        __init__.py
        adapter.py
        rule_mapping.toml
      pylint_odoo/
        __init__.py
        adapter.py
        rule_mapping.toml
    rules/
      __init__.py
      registry.py                        # @rule decorator, RuleRegistry
      manifest/
        __init__.py
        missing_required_fields.py
        missing_dependency.py
      security/
        __init__.py
        missing_access_csv.py
        unknown_model_in_access_csv.py
        raw_sql_interpolation.py
      xml/
        __init__.py
        duplicate_xml_id.py
        missing_xml_ref.py
        view_field_not_in_model.py
        button_method_not_found.py
      performance/
        __init__.py
        search_in_loop.py
    reporters/
      __init__.py
      terminal.py                        # rich terminal output
      json_report.py                     # JSON schema output
    cli/
      __init__.py
      app.py                             # typer app, all commands
  skills/
    odoo-doctor/SKILL.md
    odoo-doctor-explain/SKILL.md
  tests/
    __init__.py
    conftest.py                          # shared fixtures
    core/
      __init__.py
      test_diagnostics.py
      test_pipeline.py
      test_scoring.py
      test_config.py
    discovery/
      __init__.py
      test_addons.py
      test_odoo_version.py
    parsers/
      __init__.py
      test_manifest.py
      test_python_models.py
      test_xml_records.py
      test_security_csv.py
    graph/
      __init__.py
      test_module_context.py
      test_resolver.py
    rules/
      __init__.py
      test_manifest_rules.py
      test_security_rules.py
      test_xml_rules.py
      test_performance_rules.py
    adapters/
      __init__.py
      test_ruff.py
      test_pylint_odoo.py
    reporters/
      __init__.py
      test_terminal.py
      test_json_report.py
    cli/
      __init__.py
      test_app.py
    fixtures/
      sample_addon/                      # minimal valid addon for integration
        __manifest__.py
        models/sale_custom.py
        views/sale_custom_views.xml
        security/ir.model.access.csv
      bad_addon/                         # addon with known issues for rule tests
        __manifest__.py
        models/broken.py
        views/broken_views.xml
        security/ir.model.access.csv
      adapters/
        ruff_output.json                 # recorded ruff output
        pylint_odoo_output.txt           # recorded pylint output
    integration/
      __init__.py
      test_end_to_end.py
```

---

## Phase A — Spine

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: all `__init__.py` files in `src/` and `tests/`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "odoo-doctor"
version = "0.1.0"
description = "Unified health scoring for Odoo custom addons"
requires-python = ">=3.10"
license = "MIT"
dependencies = [
    "typer>=0.12",
    "rich>=13.0",
    "lxml>=5.0",
    "tomli>=2.0; python_version < '3.11'",
]

[project.scripts]
odoo-doctor = "odoo_doctor.cli.app:app"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/odoo_doctor"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Create package __init__.py files**

Create every `__init__.py` in the file structure above. `src/odoo_doctor/__init__.py` gets:

```python
"""Odoo Doctor — unified health scoring for custom Odoo addons."""

__version__ = "0.1.0"
```

All other `__init__.py` files are empty.

- [ ] **Step 3: Create tests/conftest.py**

```python
"""Shared test fixtures for odoo-doctor."""

from __future__ import annotations

import pytest
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_addon(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_addon"


@pytest.fixture
def bad_addon(fixtures_dir: Path) -> Path:
    return fixtures_dir / "bad_addon"
```

- [ ] **Step 4: Verify project installs and pytest runs**

Run: `pip install -e ".[dev]" && pytest --co -q`
Expected: `no tests ran` (collection succeeds, zero tests found)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: project scaffold with pyproject.toml and package structure"
```

---

### Task 2: Diagnostic Schema

**Files:**
- Create: `src/odoo_doctor/core/diagnostics.py`
- Create: `tests/core/test_diagnostics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_diagnostics.py
"""Tests for the Diagnostic dataclass and constants."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import (
    CATEGORIES,
    TIER_IMPACT,
    Diagnostic,
)


def test_diagnostic_creation():
    d = Diagnostic(
        module="sale_custom",
        file_path="models/sale.py",
        line=42,
        column=0,
        rule="raw-sql-string-interpolation",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="SQL injection via string formatting",
        message="cr.execute() uses f-string at line 42",
        help="Use parameterized queries: cr.execute('SELECT ...', (param,))",
        odoo_version="17.0",
        url=None,
    )
    assert d.module == "sale_custom"
    assert d.rule == "raw-sql-string-interpolation"
    assert d.url is None


def test_diagnostic_is_frozen():
    d = Diagnostic(
        module="m", file_path="f.py", line=1, column=0,
        rule="r", category="Security", severity="error", tier="P0",
        source="native", confidence="high", title="t", message="msg",
        help="h", odoo_version="17.0",
    )
    try:
        d.module = "other"  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass


def test_categories_are_canonical():
    expected = [
        "Security", "Correctness", "Performance", "Data Integrity",
        "Upgrade Safety", "Module Hygiene", "Maintainability",
    ]
    assert CATEGORIES == expected


def test_tier_impact_values():
    assert TIER_IMPACT["P0"] == 25
    assert TIER_IMPACT["P1"] == 10
    assert TIER_IMPACT["P2"] == 4
    assert TIER_IMPACT["P3"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_diagnostics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'odoo_doctor.core.diagnostics'`

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/core/diagnostics.py
"""Diagnostic dataclass — the shared contract for every finding."""

from __future__ import annotations

from dataclasses import dataclass


CATEGORIES: list[str] = [
    "Security",
    "Correctness",
    "Performance",
    "Data Integrity",
    "Upgrade Safety",
    "Module Hygiene",
    "Maintainability",
]

TIER_IMPACT: dict[str, int] = {
    "P0": 25,
    "P1": 10,
    "P2": 4,
    "P3": 1,
}


@dataclass(frozen=True)
class Diagnostic:
    """A single finding from any source (native rule or external adapter)."""

    module: str
    file_path: str
    line: int
    column: int

    rule: str
    category: str
    severity: str       # "error" | "warning" | "info"
    tier: str           # "P0" | "P1" | "P2" | "P3"
    source: str         # "native" | "pylint-odoo" | "ruff" | "oca"
    confidence: str     # "high" | "medium" | "low"

    title: str
    message: str
    help: str
    odoo_version: str
    url: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_diagnostics.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/core/diagnostics.py tests/core/test_diagnostics.py
git commit -m "feat: Diagnostic dataclass and category/tier constants"
```

---

### Task 3: Config Loader

**Files:**
- Create: `src/odoo_doctor/core/config.py`
- Create: `tests/core/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_config.py
"""Tests for config loading from odoo-doctor.toml."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.core.config import OdooDoctorConfig, load_config


def test_default_config():
    cfg = OdooDoctorConfig()
    assert cfg.odoo_version is None
    assert cfg.addons_paths == ["."]
    assert cfg.adapters["ruff"] is True
    assert cfg.adapters["pylint_odoo"] is True
    assert cfg.adapters["oca"] is False
    assert cfg.min_score == 0
    assert cfg.severity_overrides == {}
    assert cfg.ignore_rules == []
    assert cfg.ignore_files == []
    assert cfg.ignore_modules == []
    assert cfg.category_weights == {}


def test_load_config_from_toml(tmp_path: Path):
    toml_content = dedent("""\
        [odoo-doctor]
        odoo_version = "17.0"
        addons_paths = ["addons"]
        min_score = 60
        odoo_source_path = "/opt/odoo/src"

        [adapters]
        ruff = true
        pylint_odoo = false
        oca = false

        [severity]
        "search-in-loop" = "warning"

        [ignore]
        rules = ["deprecated-api"]
        files = ["**/migrations/**"]
        modules = ["legacy"]

        [category_weights]
        Security = 1.5
        "Module Hygiene" = 0.5
    """)
    config_file = tmp_path / "odoo-doctor.toml"
    config_file.write_text(toml_content)

    cfg = load_config(tmp_path)
    assert cfg.odoo_version == "17.0"
    assert cfg.addons_paths == ["addons"]
    assert cfg.min_score == 60
    assert cfg.odoo_source_path == "/opt/odoo/src"
    assert cfg.adapters["pylint_odoo"] is False
    assert cfg.severity_overrides == {"search-in-loop": "warning"}
    assert cfg.ignore_rules == ["deprecated-api"]
    assert cfg.ignore_files == ["**/migrations/**"]
    assert cfg.ignore_modules == ["legacy"]
    assert cfg.category_weights["Security"] == 1.5
    assert cfg.category_weights["Module Hygiene"] == 0.5


def test_load_config_missing_file(tmp_path: Path):
    cfg = load_config(tmp_path)
    assert cfg == OdooDoctorConfig()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/core/config.py
"""Configuration loading from odoo-doctor.toml."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class OdooDoctorConfig:
    """Parsed configuration from odoo-doctor.toml + CLI overrides."""

    odoo_version: str | None = None
    addons_paths: list[str] = field(default_factory=lambda: ["."])
    target_modules: list[str] = field(default_factory=list)
    odoo_source_path: str = ""
    min_score: int = 0

    adapters: dict[str, bool] = field(
        default_factory=lambda: {"ruff": True, "pylint_odoo": True, "oca": False}
    )

    severity_overrides: dict[str, str] = field(default_factory=dict)
    ignore_rules: list[str] = field(default_factory=list)
    ignore_files: list[str] = field(default_factory=list)
    ignore_modules: list[str] = field(default_factory=list)
    category_weights: dict[str, float] = field(default_factory=dict)


def load_config(directory: Path) -> OdooDoctorConfig:
    """Load config from odoo-doctor.toml in *directory*. Returns defaults if missing."""
    config_path = directory / "odoo-doctor.toml"
    if not config_path.exists():
        return OdooDoctorConfig()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    main = raw.get("odoo-doctor", {})
    adapters_raw = raw.get("adapters", {})
    severity_raw = raw.get("severity", {})
    ignore_raw = raw.get("ignore", {})
    weights_raw = raw.get("category_weights", {})

    defaults = OdooDoctorConfig()
    adapters = dict(defaults.adapters)
    for key, val in adapters_raw.items():
        adapters[key] = bool(val)

    return OdooDoctorConfig(
        odoo_version=main.get("odoo_version"),
        addons_paths=main.get("addons_paths", defaults.addons_paths),
        target_modules=main.get("target_modules", defaults.target_modules),
        odoo_source_path=main.get("odoo_source_path", defaults.odoo_source_path),
        min_score=main.get("min_score", defaults.min_score),
        adapters=adapters,
        severity_overrides=dict(severity_raw),
        ignore_rules=ignore_raw.get("rules", []),
        ignore_files=ignore_raw.get("files", []),
        ignore_modules=ignore_raw.get("modules", []),
        category_weights=dict(weights_raw),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/core/config.py tests/core/test_config.py
git commit -m "feat: config loader from odoo-doctor.toml"
```

---

### Task 4: Pipeline Stages

**Files:**
- Create: `src/odoo_doctor/core/pipeline.py`
- Create: `tests/core/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_pipeline.py
"""Tests for the 7-stage diagnostic pipeline."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.config import OdooDoctorConfig
from odoo_doctor.core.pipeline import (
    deduplicate,
    apply_severity_overrides,
    apply_ignore_filters,
    apply_inline_suppressions,
    apply_version_gates,
    mark_score_eligibility,
    run_pipeline,
)


def _diag(**overrides) -> Diagnostic:
    defaults = dict(
        module="m", file_path="f.py", line=1, column=0,
        rule="r", category="Security", severity="error", tier="P0",
        source="native", confidence="high", title="t", message="msg",
        help="h", odoo_version="17.0",
    )
    defaults.update(overrides)
    return Diagnostic(**defaults)


# --- deduplicate ---

def test_dedup_same_file_line_category_keeps_higher_confidence():
    native_low = _diag(source="native", confidence="low", message="short")
    adapter_high = _diag(source="ruff", confidence="high", message="detailed msg")
    result = deduplicate([native_low, adapter_high])
    assert len(result) == 1
    assert result[0].confidence == "high"


def test_dedup_different_categories_kept():
    sec = _diag(category="Security", rule="r1")
    cor = _diag(category="Correctness", rule="r2")
    result = deduplicate([sec, cor])
    assert len(result) == 2


def test_dedup_same_confidence_prefers_native():
    native = _diag(source="native", message="native msg")
    adapter = _diag(source="ruff", message="adapter msg")
    result = deduplicate([native, adapter])
    assert len(result) == 1
    assert result[0].source == "native"


# --- severity overrides ---

def test_severity_override_changes_severity():
    d = _diag(rule="search-in-loop", severity="error")
    cfg = OdooDoctorConfig(severity_overrides={"search-in-loop": "warning"})
    result = apply_severity_overrides([d], cfg)
    assert result[0].severity == "warning"


def test_severity_override_off_removes():
    d = _diag(rule="search-in-loop")
    cfg = OdooDoctorConfig(severity_overrides={"search-in-loop": "off"})
    result = apply_severity_overrides([d], cfg)
    assert len(result) == 0


# --- ignore filters ---

def test_ignore_by_rule():
    d = _diag(rule="deprecated-api")
    cfg = OdooDoctorConfig(ignore_rules=["deprecated-api"])
    result = apply_ignore_filters([d], cfg)
    assert len(result) == 0


def test_ignore_by_module():
    d = _diag(module="legacy")
    cfg = OdooDoctorConfig(ignore_modules=["legacy"])
    result = apply_ignore_filters([d], cfg)
    assert len(result) == 0


def test_ignore_by_file_glob():
    d = _diag(file_path="migrations/17.0/pre.py")
    cfg = OdooDoctorConfig(ignore_files=["**/migrations/**"])
    result = apply_ignore_filters([d], cfg)
    assert len(result) == 0


# --- inline suppressions ---

def test_inline_suppression_removes_matching():
    d = _diag(file_path="models/sale.py", line=10, rule="search-in-loop")
    suppressions = {("models/sale.py", 10, "search-in-loop")}
    result = apply_inline_suppressions([d], suppressions)
    assert len(result) == 0


def test_inline_suppression_keeps_non_matching():
    d = _diag(file_path="models/sale.py", line=10, rule="search-in-loop")
    suppressions = {("models/sale.py", 10, "other-rule")}
    result = apply_inline_suppressions([d], suppressions)
    assert len(result) == 1


# --- version gates ---

def test_version_gate_removes_inapplicable():
    d = _diag(rule="owl-rule", odoo_version="14.0")
    active_rules = {"search-in-loop": "14.0", "owl-rule": "16.0"}
    result = apply_version_gates([d], active_rules, detected_version="14.0")
    assert len(result) == 0


def test_version_gate_keeps_applicable():
    d = _diag(rule="search-in-loop", odoo_version="17.0")
    active_rules = {"search-in-loop": "14.0"}
    result = apply_version_gates([d], active_rules, detected_version="17.0")
    assert len(result) == 1


def test_version_gate_keeps_when_no_min():
    d = _diag(rule="raw-sql")
    active_rules = {"raw-sql": None}
    result = apply_version_gates([d], active_rules, detected_version="17.0")
    assert len(result) == 1


# --- score eligibility ---

def test_score_eligible_high_confidence():
    d = _diag(confidence="high", category="Security")
    result = mark_score_eligibility([d])
    assert result[0] is True


def test_score_ineligible_low_confidence():
    d = _diag(confidence="low", category="Security")
    result = mark_score_eligibility([d])
    assert result[0] is False


def test_score_ineligible_uncategorized():
    d = _diag(confidence="high", category="Uncategorized")
    result = mark_score_eligibility([d])
    assert result[0] is False


# --- full pipeline ---

def test_run_pipeline_smoke():
    diags = [_diag(rule="r1"), _diag(rule="r2", confidence="low")]
    cfg = OdooDoctorConfig()
    active_rules = {"r1": None, "r2": None}
    result_diags, eligible = run_pipeline(
        diags, cfg, suppressions=set(), active_rules=active_rules,
        detected_version="17.0",
    )
    assert len(result_diags) == 2
    assert eligible[0] is True   # r1: high confidence
    assert eligible[1] is False  # r2: low confidence
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/core/pipeline.py
"""Seven-stage diagnostic pipeline — pure transformations."""

from __future__ import annotations

import fnmatch
from dataclasses import replace
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import CATEGORIES, Diagnostic

if TYPE_CHECKING:
    from odoo_doctor.core.config import OdooDoctorConfig


# Type aliases
Suppressions = set[tuple[str, int, str]]  # (file_path, line, rule)
ActiveRules = dict[str, str | None]       # rule_name -> min_version or None


# --- Helpers ---

_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
_SOURCE_RANK = {"native": 2, "pylint-odoo": 1, "ruff": 1, "oca": 1}


def _version_gte(detected: str, minimum: str) -> bool:
    """Return True if detected >= minimum using first segment (e.g. '17.0' >= '14.0')."""
    try:
        det = float(detected.split(".")[0])
        mn = float(minimum.split(".")[0])
        return det >= mn
    except (ValueError, IndexError):
        return False


# --- Stage 1: Deduplicate ---

def deduplicate(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    """Group by (module, file_path, line, category). Keep highest confidence,
    then prefer native source, then longest message."""
    groups: dict[tuple[str, str, int, str], list[Diagnostic]] = {}
    for d in diagnostics:
        key = (d.module, d.file_path, d.line, d.category)
        groups.setdefault(key, []).append(d)

    result: list[Diagnostic] = []
    for group in groups.values():
        best = max(
            group,
            key=lambda d: (
                _CONFIDENCE_RANK.get(d.confidence, 0),
                _SOURCE_RANK.get(d.source, 0),
                len(d.message),
            ),
        )
        result.append(best)
    return result


# --- Stage 2: Severity overrides ---

def apply_severity_overrides(
    diagnostics: list[Diagnostic], config: OdooDoctorConfig
) -> list[Diagnostic]:
    """Change severity per config. severity='off' removes the diagnostic."""
    result: list[Diagnostic] = []
    for d in diagnostics:
        override = config.severity_overrides.get(d.rule)
        if override is None:
            result.append(d)
        elif override == "off":
            continue
        else:
            result.append(replace(d, severity=override))
    return result


# --- Stage 3: Ignore filters ---

def apply_ignore_filters(
    diagnostics: list[Diagnostic], config: OdooDoctorConfig
) -> list[Diagnostic]:
    """Remove diagnostics matching ignore rules, files, or modules."""
    result: list[Diagnostic] = []
    for d in diagnostics:
        if d.rule in config.ignore_rules:
            continue
        if d.module in config.ignore_modules:
            continue
        if any(fnmatch.fnmatch(d.file_path, pat) for pat in config.ignore_files):
            continue
        result.append(d)
    return result


# --- Stage 4: Inline suppressions ---

def apply_inline_suppressions(
    diagnostics: list[Diagnostic], suppressions: Suppressions
) -> list[Diagnostic]:
    """Remove diagnostics covered by inline suppression comments."""
    return [
        d for d in diagnostics
        if (d.file_path, d.line, d.rule) not in suppressions
    ]


# --- Stage 5: Version gates ---

def apply_version_gates(
    diagnostics: list[Diagnostic],
    active_rules: ActiveRules,
    detected_version: str,
) -> list[Diagnostic]:
    """Remove diagnostics whose rule requires a newer Odoo version."""
    result: list[Diagnostic] = []
    for d in diagnostics:
        min_ver = active_rules.get(d.rule)
        if min_ver is None:
            result.append(d)
        elif _version_gte(detected_version, min_ver):
            result.append(d)
    return result


# --- Stage 6: Score eligibility ---

def mark_score_eligibility(
    diagnostics: list[Diagnostic],
) -> list[bool]:
    """Return parallel list of booleans — True if the diagnostic counts toward score."""
    return [
        d.confidence == "high" and d.category in CATEGORIES
        for d in diagnostics
    ]


# --- Composed pipeline ---

def run_pipeline(
    diagnostics: list[Diagnostic],
    config: OdooDoctorConfig,
    suppressions: Suppressions,
    active_rules: ActiveRules,
    detected_version: str,
) -> tuple[list[Diagnostic], list[bool]]:
    """Run all 7 pipeline stages in order. Returns (diagnostics, eligibility)."""
    diags = deduplicate(diagnostics)
    diags = apply_severity_overrides(diags, config)
    diags = apply_ignore_filters(diags, config)
    diags = apply_inline_suppressions(diags, suppressions)
    diags = apply_version_gates(diags, active_rules, detected_version)
    eligible = mark_score_eligibility(diags)
    return diags, eligible
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_pipeline.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/core/pipeline.py tests/core/test_pipeline.py
git commit -m "feat: 7-stage diagnostic pipeline"
```

---

### Task 5: Scoring Engine

**Files:**
- Create: `src/odoo_doctor/core/scoring.py`
- Create: `tests/core/test_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_scoring.py
"""Tests for the scoring engine."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import CategoryScore, ScoreResult, score_diagnostics


def _diag(**overrides) -> Diagnostic:
    defaults = dict(
        module="m", file_path="f.py", line=1, column=0,
        rule="r", category="Security", severity="error", tier="P0",
        source="native", confidence="high", title="t", message="msg",
        help="h", odoo_version="17.0",
    )
    defaults.update(overrides)
    return Diagnostic(**defaults)


def test_perfect_score_no_findings():
    result = score_diagnostics([], [])
    assert result.overall == 100.0
    assert result.label == "Excellent"


def test_single_p0_security():
    diags = [_diag(tier="P0", category="Security")]
    eligible = [True]
    result = score_diagnostics(diags, eligible, category_weights={})
    sec = next(c for c in result.categories if c.category == "Security")
    assert sec.score == 75  # 100 - 25
    assert sec.finding_count == 1


def test_ineligible_not_counted():
    diags = [_diag(tier="P0", category="Security", confidence="low")]
    eligible = [False]
    result = score_diagnostics(diags, eligible)
    sec = next(c for c in result.categories if c.category == "Security")
    assert sec.score == 100  # not counted


def test_category_weights_applied():
    diags = [_diag(tier="P1", category="Performance")]
    eligible = [True]
    result = score_diagnostics(diags, eligible, category_weights={"Performance": 2.0})
    perf = next(c for c in result.categories if c.category == "Performance")
    assert perf.score == 80  # 100 - (10 * 2.0)


def test_only_in_scope_categories_in_overall():
    """Empty categories (no active rules) should not inflate the overall score."""
    diags = [_diag(tier="P0", category="Security")]
    eligible = [True]
    in_scope = ["Security", "Correctness"]
    result = score_diagnostics(diags, eligible, in_scope_categories=in_scope)
    # Security=75, Correctness=100 (no findings but in scope)
    # overall = 0.4 * min(75, 100) + 0.6 * avg(75, 100) = 30 + 52.5 = 82.5
    assert result.overall == 82.5
    assert result.in_scope_categories == ["Security", "Correctness"]


def test_blend_formula_punishes_weak_category():
    """A category at 0 should drag overall hard via 0.4*min."""
    diags = [
        _diag(tier="P0", category="Security"),
        _diag(tier="P0", category="Security", line=2),
        _diag(tier="P0", category="Security", line=3),
        _diag(tier="P0", category="Security", line=4),
    ]
    eligible = [True, True, True, True]
    in_scope = ["Security", "Correctness"]
    result = score_diagnostics(diags, eligible, in_scope_categories=in_scope)
    # Security = max(0, 100 - 100) = 0, Correctness = 100
    # overall = 0.4 * 0 + 0.6 * 50 = 30.0
    assert result.overall == 30.0
    assert result.label == "Critical"


def test_labels():
    assert ScoreResult(95.0, "", [], [], 0).compute_label() == "Excellent"
    assert ScoreResult(80.0, "", [], [], 0).compute_label() == "Good"
    assert ScoreResult(60.0, "", [], [], 0).compute_label() == "Needs work"
    assert ScoreResult(30.0, "", [], [], 0).compute_label() == "Critical"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_scoring.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/core/scoring.py
"""Scoring engine — deterministic local health score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import CATEGORIES, TIER_IMPACT, Diagnostic

if TYPE_CHECKING:
    pass


@dataclass
class CategoryScore:
    category: str
    score: int          # 0–100
    finding_count: int
    total_impact: float


@dataclass
class ScoreResult:
    overall: float
    label: str
    categories: list[CategoryScore]
    in_scope_categories: list[str]
    diagnostics_counted: int

    def compute_label(self) -> str:
        if self.overall >= 90:
            return "Excellent"
        if self.overall >= 75:
            return "Good"
        if self.overall >= 50:
            return "Needs work"
        return "Critical"


def score_diagnostics(
    diagnostics: list[Diagnostic],
    eligible: list[bool],
    category_weights: dict[str, float] | None = None,
    in_scope_categories: list[str] | None = None,
) -> ScoreResult:
    """Compute per-category and overall health scores.

    Only diagnostics where eligible[i] is True are counted.
    Only in_scope_categories (those with ≥1 active rule) affect the overall blend.
    """
    weights = category_weights or {}
    scope = in_scope_categories if in_scope_categories is not None else list(CATEGORIES)

    # Accumulate impact per category
    impact: dict[str, float] = {cat: 0.0 for cat in CATEGORIES}
    counts: dict[str, int] = {cat: 0 for cat in CATEGORIES}
    counted = 0

    for d, elig in zip(diagnostics, eligible):
        if not elig:
            continue
        if d.category not in impact:
            continue
        tier_pts = TIER_IMPACT.get(d.tier, 0)
        w = weights.get(d.category, 1.0)
        impact[d.category] += tier_pts * w
        counts[d.category] += 1
        counted += 1

    # Build category scores
    cat_scores: list[CategoryScore] = []
    for cat in CATEGORIES:
        score = max(0, int(100 - impact[cat]))
        cat_scores.append(CategoryScore(
            category=cat,
            score=score,
            finding_count=counts[cat],
            total_impact=impact[cat],
        ))

    # Overall: blend over in-scope categories only
    in_scope_scores = [cs.score for cs in cat_scores if cs.category in scope]
    if not in_scope_scores:
        overall = 100.0
    else:
        overall = 0.4 * min(in_scope_scores) + 0.6 * (sum(in_scope_scores) / len(in_scope_scores))

    result = ScoreResult(
        overall=overall,
        label="",
        categories=cat_scores,
        in_scope_categories=list(scope),
        diagnostics_counted=counted,
    )
    result.label = result.compute_label()
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_scoring.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/core/scoring.py tests/core/test_scoring.py
git commit -m "feat: scoring engine with tier impact and in-scope blend"
```

---

## Phase B — Parsing & Graph

### Task 6: Addon Discovery

**Files:**
- Create: `src/odoo_doctor/discovery/addons.py`
- Create: `tests/discovery/test_addons.py`
- Create: `tests/fixtures/sample_addon/__manifest__.py`

- [ ] **Step 1: Create sample addon fixture**

```python
# tests/fixtures/sample_addon/__manifest__.py
{
    "name": "Sale Custom",
    "version": "17.0.1.0.0",
    "depends": ["sale", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/sale_custom_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/discovery/test_addons.py
"""Tests for addon discovery."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.discovery.addons import AddonInfo, discover_addons


def test_discover_single_addon(sample_addon: Path):
    addons = discover_addons([sample_addon.parent])
    assert len(addons) == 1
    assert addons[0].name == "sample_addon"
    assert addons[0].path == sample_addon


def test_discover_filters_by_target(sample_addon: Path):
    addons = discover_addons([sample_addon.parent], target_modules=["nonexistent"])
    assert len(addons) == 0


def test_discover_empty_directory(tmp_path: Path):
    addons = discover_addons([tmp_path])
    assert addons == []


def test_discover_skips_non_installable(tmp_path: Path):
    mod = tmp_path / "disabled_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "Disabled", "installable": False}')
    addons = discover_addons([tmp_path])
    assert len(addons) == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/discovery/test_addons.py -v`
Expected: FAIL

- [ ] **Step 4: Write implementation**

```python
# src/odoo_doctor/discovery/addons.py
"""Discover Odoo addons by scanning for __manifest__.py."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AddonInfo:
    name: str
    path: Path
    manifest: dict


def discover_addons(
    addons_paths: list[Path],
    target_modules: list[str] | None = None,
) -> list[AddonInfo]:
    """Find all installable addons under the given paths."""
    found: list[AddonInfo] = []

    for base in addons_paths:
        if not base.is_dir():
            continue
        # Check if base itself is an addon
        manifest_file = base / "__manifest__.py"
        if manifest_file.exists():
            _try_add(base, manifest_file, target_modules, found)
            continue
        # Otherwise scan children
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            mf = child / "__manifest__.py"
            if mf.exists():
                _try_add(child, mf, target_modules, found)

    return found


def _try_add(
    addon_dir: Path,
    manifest_file: Path,
    target_modules: list[str] | None,
    out: list[AddonInfo],
) -> None:
    try:
        manifest = ast.literal_eval(manifest_file.read_text())
    except (SyntaxError, ValueError):
        return

    if not isinstance(manifest, dict):
        return
    if not manifest.get("installable", True):
        return

    name = addon_dir.name
    if target_modules and name not in target_modules:
        return

    out.append(AddonInfo(name=name, path=addon_dir, manifest=manifest))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/discovery/test_addons.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/odoo_doctor/discovery/addons.py tests/discovery/test_addons.py tests/fixtures/sample_addon/__manifest__.py
git commit -m "feat: addon discovery from __manifest__.py"
```

---

### Task 7: Version Detection

**Files:**
- Create: `src/odoo_doctor/discovery/odoo_version.py`
- Create: `tests/discovery/test_odoo_version.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/discovery/test_odoo_version.py
"""Tests for Odoo version detection."""

from __future__ import annotations

from odoo_doctor.discovery.odoo_version import detect_odoo_version


def test_cli_flag_wins():
    assert detect_odoo_version(cli_version="16.0", config_version="17.0", manifest_version="15.0.1.0.0") == "16.0"


def test_config_fallback():
    assert detect_odoo_version(cli_version=None, config_version="17.0", manifest_version=None) == "17.0"


def test_manifest_prefix():
    assert detect_odoo_version(cli_version=None, config_version=None, manifest_version="17.0.1.0.0") == "17.0"


def test_manifest_short():
    assert detect_odoo_version(cli_version=None, config_version=None, manifest_version="16.0") == "16.0"


def test_unknown():
    assert detect_odoo_version(cli_version=None, config_version=None, manifest_version=None) == "unknown"


def test_non_standard_manifest_version():
    """Custom version strings should not be treated as Odoo version."""
    assert detect_odoo_version(cli_version=None, config_version=None, manifest_version="2.3.1") == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/discovery/test_odoo_version.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/discovery/odoo_version.py
"""Conservative Odoo version detection."""

from __future__ import annotations

import re

_ODOO_VERSION_RE = re.compile(r"^(1[4-9]|[2-9]\d)\.0")


def detect_odoo_version(
    cli_version: str | None = None,
    config_version: str | None = None,
    manifest_version: str | None = None,
) -> str:
    """Detect Odoo version using priority: CLI > config > manifest > unknown."""
    if cli_version:
        return cli_version

    if config_version:
        return config_version

    if manifest_version:
        m = _ODOO_VERSION_RE.match(manifest_version)
        if m:
            return f"{m.group(1)}.0"

    return "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/discovery/test_odoo_version.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/discovery/odoo_version.py tests/discovery/test_odoo_version.py
git commit -m "feat: conservative Odoo version detection"
```

---

### Task 8: Manifest Parser

**Files:**
- Create: `src/odoo_doctor/parsers/manifest.py`
- Create: `tests/parsers/test_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/parsers/test_manifest.py
"""Tests for manifest parsing."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.parsers.manifest import ManifestData, parse_manifest


def test_parse_valid_manifest(sample_addon: Path):
    result = parse_manifest(sample_addon)
    assert result.name == "Sale Custom"
    assert result.version == "17.0.1.0.0"
    assert "sale" in result.depends
    assert "stock" in result.depends
    assert result.license == "LGPL-3"
    assert result.installable is True
    assert "security/ir.model.access.csv" in result.data


def test_parse_minimal_manifest(tmp_path: Path):
    mod = tmp_path / "minimal"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "Min"}')
    result = parse_manifest(mod)
    assert result.name == "Min"
    assert result.depends == []
    assert result.data == []
    assert result.version is None
    assert result.license is None


def test_parse_missing_manifest(tmp_path: Path):
    result = parse_manifest(tmp_path)
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/parsers/test_manifest.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/parsers/manifest.py
"""Parse __manifest__.py safely using ast.literal_eval."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ManifestData:
    name: str
    version: str | None = None
    depends: list[str] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    license: str | None = None
    installable: bool = True
    raw: dict = field(default_factory=dict)


def parse_manifest(addon_path: Path) -> ManifestData | None:
    """Parse __manifest__.py from an addon directory. Returns None if missing/invalid."""
    manifest_file = addon_path / "__manifest__.py"
    if not manifest_file.exists():
        return None

    try:
        raw = ast.literal_eval(manifest_file.read_text())
    except (SyntaxError, ValueError):
        return None

    if not isinstance(raw, dict):
        return None

    return ManifestData(
        name=raw.get("name", addon_path.name),
        version=raw.get("version"),
        depends=raw.get("depends", []),
        data=raw.get("data", []),
        license=raw.get("license"),
        installable=raw.get("installable", True),
        raw=raw,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/parsers/test_manifest.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/parsers/manifest.py tests/parsers/test_manifest.py
git commit -m "feat: manifest parser with ast.literal_eval"
```

---

### Task 9: Python Model & Controller Parser

**Files:**
- Create: `src/odoo_doctor/parsers/python_models.py`
- Create: `tests/parsers/test_python_models.py`
- Create: `tests/fixtures/sample_addon/models/sale_custom.py`

- [ ] **Step 1: Create sample Python model fixture**

```python
# tests/fixtures/sample_addon/models/sale_custom.py
from odoo import api, fields, models


class SaleOrderCustom(models.Model):
    _inherit = "sale.order"

    custom_note = fields.Text(string="Custom Note")
    total_weight = fields.Float(compute="_compute_total_weight", store=True)

    @api.depends("order_line.product_id")
    def _compute_total_weight(self):
        for order in self:
            order.total_weight = sum(line.product_id.weight for line in order.order_line)

    def action_confirm_custom(self):
        self.ensure_one()
        return self.action_confirm()


class SaleCustomWizard(models.TransientModel):
    _name = "sale.custom.wizard"
    _description = "Sale Custom Wizard"

    name = fields.Char(required=True)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/parsers/test_python_models.py
"""Tests for Python model/controller parser."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.parsers.python_models import (
    ControllerInfo,
    FieldInfo,
    MethodInfo,
    ModelInfo,
    parse_controllers,
    parse_models,
)


def test_parse_inherit_model(sample_addon: Path):
    models = parse_models(sample_addon / "models" / "sale_custom.py")
    assert len(models) == 2

    sale = next(m for m in models if "sale.order" in m.inherit)
    assert "custom_note" in sale.fields
    assert sale.fields["custom_note"].field_type == "Text"
    assert "total_weight" in sale.fields
    assert sale.fields["total_weight"].compute == "_compute_total_weight"

    assert "_compute_total_weight" in sale.methods
    assert sale.methods["_compute_total_weight"].depends == ["order_line.product_id"]
    assert "action_confirm_custom" in sale.methods


def test_parse_new_model(sample_addon: Path):
    models = parse_models(sample_addon / "models" / "sale_custom.py")
    wizard = next(m for m in models if m.name == "sale.custom.wizard")
    assert wizard.is_transient is True
    assert "name" in wizard.fields


def test_parse_controller(tmp_path: Path):
    code = dedent("""\
        from odoo import http

        class MyController(http.Controller):
            @http.route("/api/data", auth="public", type="json")
            def get_data(self):
                records = http.request.env["res.partner"].sudo().search([])
                return records.read(["name"])
    """)
    f = tmp_path / "controller.py"
    f.write_text(code)
    controllers = parse_controllers(f)
    assert len(controllers) == 1
    assert controllers[0].route == "/api/data"
    assert controllers[0].auth == "public"
    assert controllers[0].uses_sudo is True


def test_parse_empty_file(tmp_path: Path):
    f = tmp_path / "empty.py"
    f.write_text("")
    assert parse_models(f) == []
    assert parse_controllers(f) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/parsers/test_python_models.py -v`
Expected: FAIL

- [ ] **Step 4: Write implementation**

```python
# src/odoo_doctor/parsers/python_models.py
"""Parse Odoo Python models and controllers using stdlib ast."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FieldInfo:
    name: str
    field_type: str        # "Char", "Many2one", "Float", etc.
    comodel: str | None = None
    compute: str | None = None
    depends: list[str] = field(default_factory=list)
    store: bool = True


@dataclass
class MethodInfo:
    name: str
    decorators: list[str] = field(default_factory=list)
    depends: list[str] = field(default_factory=list)
    is_override: bool = False
    calls_super: bool = False


@dataclass
class ModelInfo:
    name: str | None         # _name value, None if only _inherit
    inherit: list[str] = field(default_factory=list)
    inherits: dict[str, str] = field(default_factory=dict)
    fields: dict[str, FieldInfo] = field(default_factory=dict)
    methods: dict[str, MethodInfo] = field(default_factory=dict)
    is_transient: bool = False
    is_abstract: bool = False
    file_path: str = ""
    line: int = 0


@dataclass
class ControllerInfo:
    method_name: str
    route: str
    auth: str = "user"
    uses_sudo: bool = False
    file_path: str = ""
    line: int = 0


# --- Odoo base class names ---
_MODEL_BASES = {"models.Model", "Model"}
_TRANSIENT_BASES = {"models.TransientModel", "TransientModel"}
_ABSTRACT_BASES = {"models.AbstractModel", "AbstractModel"}
_ALL_BASES = _MODEL_BASES | _TRANSIENT_BASES | _ABSTRACT_BASES

_ODOO_FIELD_TYPES = {
    "Char", "Text", "Html", "Integer", "Float", "Boolean", "Date", "Datetime",
    "Binary", "Selection", "Many2one", "One2many", "Many2many", "Monetary",
    "Reference",
}

_LIFECYCLE_METHODS = {"create", "write", "unlink", "default_get", "read", "copy"}


def parse_models(file_path: Path) -> list[ModelInfo]:
    """Parse all Odoo model classes from a Python file."""
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return []

    models: list[ModelInfo] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_odoo_model(node):
            continue
        models.append(_extract_model(node, str(file_path)))
    return models


def parse_controllers(file_path: Path) -> list[ControllerInfo]:
    """Parse all http.route controllers from a Python file."""
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except SyntaxError:
        return []

    controllers: list[ControllerInfo] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_info = _extract_route(item)
            if route_info is None:
                continue
            route, auth = route_info
            uses_sudo = _body_uses_sudo(item, source)
            controllers.append(ControllerInfo(
                method_name=item.name,
                route=route,
                auth=auth,
                uses_sudo=uses_sudo,
                file_path=str(file_path),
                line=item.lineno,
            ))
    return controllers


# --- Helpers ---

def _is_odoo_model(cls: ast.ClassDef) -> bool:
    for base in cls.bases:
        name = _dotted_name(base)
        if name and name in _ALL_BASES:
            return True
    return False


def _extract_model(cls: ast.ClassDef, file_path: str) -> ModelInfo:
    model = ModelInfo(name=None, file_path=file_path, line=cls.lineno)

    # Detect transient/abstract
    for base in cls.bases:
        name = _dotted_name(base)
        if name in _TRANSIENT_BASES:
            model.is_transient = True
        elif name in _ABSTRACT_BASES:
            model.is_abstract = True

    for item in cls.body:
        # _name, _inherit, _inherits assignments
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    if target.id == "_name" and isinstance(item.value, ast.Constant):
                        model.name = item.value.value
                    elif target.id == "_inherit":
                        model.inherit = _extract_inherit(item.value)
                    elif target.id == "_inherits" and isinstance(item.value, ast.Dict):
                        for k, v in zip(item.value.keys, item.value.values):
                            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                                model.inherits[k.value] = v.value

        # Field definitions
        if isinstance(item, ast.Assign) and len(item.targets) == 1:
            target = item.targets[0]
            if isinstance(target, ast.Name) and isinstance(item.value, ast.Call):
                field_info = _extract_field(target.id, item.value)
                if field_info:
                    model.fields[field_info.name] = field_info

        # Method definitions
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method = _extract_method(item)
            model.methods[method.name] = method

    return model


def _extract_inherit(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.List):
        return [
            e.value for e in node.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
    return []


def _extract_field(name: str, call: ast.Call) -> FieldInfo | None:
    func_name = _dotted_name(call.func)
    if func_name is None:
        return None

    # Strip "fields." prefix
    short = func_name.split(".")[-1] if "." in func_name else func_name
    if short not in _ODOO_FIELD_TYPES:
        return None

    comodel = None
    compute = None
    depends: list[str] = []
    store = True

    # First positional arg for relational fields is comodel
    if call.args and isinstance(call.args[0], ast.Constant):
        if short in ("Many2one", "One2many", "Many2many"):
            comodel = call.args[0].value

    for kw in call.keywords:
        if kw.arg == "comodel_name" and isinstance(kw.value, ast.Constant):
            comodel = kw.value.value
        elif kw.arg == "compute" and isinstance(kw.value, ast.Constant):
            compute = kw.value.value
        elif kw.arg == "store" and isinstance(kw.value, ast.Constant):
            store = bool(kw.value.value)

    return FieldInfo(
        name=name,
        field_type=short,
        comodel=comodel,
        compute=compute,
        depends=depends,
        store=store if compute is None else store,
    )


def _extract_method(func: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo:
    decorators: list[str] = []
    depends: list[str] = []

    for dec in func.decorator_list:
        dec_name = _dotted_name(dec) if not isinstance(dec, ast.Call) else _dotted_name(dec.func)
        if dec_name:
            decorators.append(dec_name)
        # Extract @api.depends("field1", "field2")
        if isinstance(dec, ast.Call) and _dotted_name(dec.func) == "api.depends":
            for arg in dec.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    depends.append(arg.value)

    is_override = func.name in _LIFECYCLE_METHODS
    calls_super = _body_calls_super(func)

    return MethodInfo(
        name=func.name,
        decorators=decorators,
        depends=depends,
        is_override=is_override,
        calls_super=calls_super,
    )


def _body_calls_super(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "super":
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "super":
            return True
    return False


def _body_uses_sudo(func: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "sudo":
                return True
    return False


def _dotted_name(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/parsers/test_python_models.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/odoo_doctor/parsers/python_models.py tests/parsers/test_python_models.py tests/fixtures/sample_addon/models/sale_custom.py
git commit -m "feat: Python model and controller parser using stdlib ast"
```

---

### Task 10: XML/View Parser

**Files:**
- Create: `src/odoo_doctor/parsers/xml_records.py`
- Create: `tests/parsers/test_xml_records.py`
- Create: `tests/fixtures/sample_addon/views/sale_custom_views.xml`

- [ ] **Step 1: Create sample XML fixture**

```xml
<!-- tests/fixtures/sample_addon/views/sale_custom_views.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_sale_order_custom_form" model="ir.ui.view">
        <field name="name">sale.order.custom.form</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='partner_id']" position="after">
                <field name="custom_note"/>
            </xpath>
        </field>
    </record>

    <record id="action_custom_wizard" model="ir.actions.act_window">
        <field name="name">Custom Wizard</field>
        <field name="res_model">sale.custom.wizard</field>
        <field name="view_mode">form</field>
    </record>

    <menuitem id="menu_custom_wizard"
              name="Custom Wizard"
              action="action_custom_wizard"
              parent="sale.sale_menu_root"/>
</odoo>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/parsers/test_xml_records.py
"""Tests for XML/view parser."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.parsers.xml_records import (
    ViewInfo,
    XmlIdInfo,
    parse_views,
    parse_xml_records,
)


def test_parse_xml_records(sample_addon: Path):
    xml_file = sample_addon / "views" / "sale_custom_views.xml"
    records = parse_xml_records(xml_file, module_name="sample_addon")
    ids = {r.xml_id for r in records}
    assert "sample_addon.view_sale_order_custom_form" in ids
    assert "sample_addon.action_custom_wizard" in ids
    assert "sample_addon.menu_custom_wizard" in ids


def test_parse_views(sample_addon: Path):
    xml_file = sample_addon / "views" / "sale_custom_views.xml"
    views = parse_views(xml_file, module_name="sample_addon")
    assert len(views) == 1
    v = views[0]
    assert v.model == "sale.order"
    assert v.inherit_id == "sale.view_order_form"
    assert "custom_note" in v.field_refs


def test_parse_view_with_button(tmp_path: Path):
    xml = dedent("""\
        <?xml version="1.0"?>
        <odoo>
            <record id="view_form" model="ir.ui.view">
                <field name="model">sale.order</field>
                <field name="arch" type="xml">
                    <form>
                        <field name="partner_id"/>
                        <button name="action_confirm" type="object" string="Confirm"/>
                    </form>
                </field>
            </record>
        </odoo>
    """)
    f = tmp_path / "views.xml"
    f.write_text(xml)
    views = parse_views(f, module_name="test_mod")
    assert "partner_id" in views[0].field_refs
    assert "action_confirm" in views[0].button_methods


def test_parse_empty_xml(tmp_path: Path):
    f = tmp_path / "empty.xml"
    f.write_text('<?xml version="1.0"?><odoo></odoo>')
    assert parse_xml_records(f, module_name="m") == []
    assert parse_views(f, module_name="m") == []


def test_ref_extraction(tmp_path: Path):
    xml = dedent("""\
        <?xml version="1.0"?>
        <odoo>
            <record id="rec1" model="ir.actions.act_window">
                <field name="res_model">res.partner</field>
            </record>
        </odoo>
    """)
    f = tmp_path / "data.xml"
    f.write_text(xml)
    records = parse_xml_records(f, module_name="mymod")
    assert records[0].xml_id == "mymod.rec1"
    assert records[0].model == "ir.actions.act_window"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/parsers/test_xml_records.py -v`
Expected: FAIL

- [ ] **Step 4: Write implementation**

```python
# src/odoo_doctor/parsers/xml_records.py
"""Parse XML records, views, and data files using lxml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


@dataclass
class XmlIdInfo:
    xml_id: str             # "module.xml_id"
    model: str | None
    record_type: str        # "record", "template", "menuitem", etc.
    file_path: str
    line: int
    refs: list[str] = field(default_factory=list)  # referenced xml IDs


@dataclass
class ViewInfo:
    xml_id: str
    model: str
    view_type: str | None = None
    inherit_id: str | None = None
    field_refs: list[str] = field(default_factory=list)
    button_methods: list[str] = field(default_factory=list)
    file_path: str = ""
    line: int = 0


def parse_xml_records(file_path: Path, module_name: str) -> list[XmlIdInfo]:
    """Extract all XML IDs from an Odoo data/view file."""
    try:
        tree = etree.parse(str(file_path))
    except etree.XMLSyntaxError:
        return []

    root = tree.getroot()
    records: list[XmlIdInfo] = []

    for elem in root.iter():
        xml_id = elem.get("id")
        if xml_id is None:
            continue

        full_id = f"{module_name}.{xml_id}" if "." not in xml_id else xml_id

        model = None
        refs: list[str] = []

        if elem.tag == "record":
            model = elem.get("model")
        elif elem.tag == "menuitem":
            model = "ir.ui.menu"
        elif elem.tag == "template":
            model = "ir.ui.view"

        # Collect ref attributes
        for child in elem.iter():
            ref = child.get("ref")
            if ref:
                refs.append(ref)

        records.append(XmlIdInfo(
            xml_id=full_id,
            model=model,
            record_type=elem.tag,
            file_path=str(file_path),
            line=elem.sourceline or 0,
            refs=refs,
        ))

    return records


def parse_views(file_path: Path, module_name: str) -> list[ViewInfo]:
    """Extract view definitions (ir.ui.view records) with field/button references."""
    try:
        tree = etree.parse(str(file_path))
    except etree.XMLSyntaxError:
        return []

    root = tree.getroot()
    views: list[ViewInfo] = []

    for record in root.iter("record"):
        if record.get("model") != "ir.ui.view":
            continue

        xml_id_raw = record.get("id", "")
        xml_id = f"{module_name}.{xml_id_raw}" if "." not in xml_id_raw else xml_id_raw

        model = ""
        inherit_id = None
        field_refs: list[str] = []
        button_methods: list[str] = []

        for field_elem in record.findall("field"):
            fname = field_elem.get("name")
            if fname == "model":
                model = (field_elem.text or "").strip()
            elif fname == "inherit_id":
                inherit_id = field_elem.get("ref")
            elif fname == "arch":
                # Parse the arch content for field/button refs
                _extract_arch_refs(field_elem, field_refs, button_methods)

        if not model:
            continue

        views.append(ViewInfo(
            xml_id=xml_id,
            model=model,
            inherit_id=inherit_id,
            field_refs=field_refs,
            button_methods=button_methods,
            file_path=str(file_path),
            line=record.sourceline or 0,
        ))

    return views


def _extract_arch_refs(
    arch_elem: etree._Element,
    field_refs: list[str],
    button_methods: list[str],
) -> None:
    """Walk arch XML to find <field name="..."> and <button name="..." type="object">."""
    for elem in arch_elem.iter():
        if elem.tag == "field":
            name = elem.get("name")
            if name and name not in field_refs:
                field_refs.append(name)
        elif elem.tag == "button":
            btn_name = elem.get("name")
            btn_type = elem.get("type")
            if btn_name and btn_type == "object" and btn_name not in button_methods:
                button_methods.append(btn_name)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/parsers/test_xml_records.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/odoo_doctor/parsers/xml_records.py tests/parsers/test_xml_records.py tests/fixtures/sample_addon/views/sale_custom_views.xml
git commit -m "feat: XML/view parser with field and button ref extraction"
```

---

### Task 11: Security CSV Parser

**Files:**
- Create: `src/odoo_doctor/parsers/security_csv.py`
- Create: `tests/parsers/test_security_csv.py`
- Create: `tests/fixtures/sample_addon/security/ir.model.access.csv`

- [ ] **Step 1: Create sample CSV fixture**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_sale_custom_wizard_user,sale.custom.wizard user,model_sale_custom_wizard,base.group_user,1,1,1,1
```

Save as `tests/fixtures/sample_addon/security/ir.model.access.csv`.

- [ ] **Step 2: Write the failing test**

```python
# tests/parsers/test_security_csv.py
"""Tests for security CSV parser."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.parsers.security_csv import AccessRule, parse_access_csv


def test_parse_access_csv(sample_addon: Path):
    csv_file = sample_addon / "security" / "ir.model.access.csv"
    rules = parse_access_csv(csv_file, module_name="sample_addon")
    assert len(rules) == 1
    r = rules[0]
    assert r.id == "access_sale_custom_wizard_user"
    assert r.model_external_id == "model_sale_custom_wizard"
    assert r.model_external_id_module == "sample_addon"
    assert r.group_id == "base.group_user"
    assert r.perm_read is True


def test_parse_access_csv_model_name_extraction():
    """model_sale_custom_wizard -> sale.custom.wizard"""
    from odoo_doctor.parsers.security_csv import model_external_id_to_name
    assert model_external_id_to_name("model_sale_custom_wizard") == "sale.custom.wizard"
    assert model_external_id_to_name("model_res_partner") == "res.partner"


def test_parse_empty_csv(tmp_path: Path):
    f = tmp_path / "ir.model.access.csv"
    f.write_text("id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n")
    assert parse_access_csv(f, module_name="m") == []


def test_parse_missing_file(tmp_path: Path):
    assert parse_access_csv(tmp_path / "missing.csv", module_name="m") == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/parsers/test_security_csv.py -v`
Expected: FAIL

- [ ] **Step 4: Write implementation**

```python
# src/odoo_doctor/parsers/security_csv.py
"""Parse ir.model.access.csv files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AccessRule:
    id: str
    name: str
    model_external_id: str   # e.g. "model_sale_custom_wizard"
    model_external_id_module: str  # e.g. "base" from "base.model_res_partner"; current module if unqualified
    group_id: str | None
    perm_read: bool
    perm_write: bool
    perm_create: bool
    perm_unlink: bool
    file_path: str
    line: int


def parse_access_csv(file_path: Path, module_name: str) -> list[AccessRule]:
    """Parse an ir.model.access.csv file into AccessRule objects."""
    if not file_path.exists():
        return []

    rules: list[AccessRule] = []
    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for lineno, row in enumerate(reader, start=2):
            raw_model_id = row.get("model_id:id", row.get("model_id/id", ""))
            model_id_module = module_name
            model_id = raw_model_id
            if "." in raw_model_id:
                model_id_module, model_id = raw_model_id.split(".", 1)

            rules.append(AccessRule(
                id=row.get("id", ""),
                name=row.get("name", ""),
                model_external_id=model_id,
                model_external_id_module=model_id_module,
                group_id=row.get("group_id:id", row.get("group_id/id")) or None,
                perm_read=row.get("perm_read", "0") == "1",
                perm_write=row.get("perm_write", "0") == "1",
                perm_create=row.get("perm_create", "0") == "1",
                perm_unlink=row.get("perm_unlink", "0") == "1",
                file_path=str(file_path),
                line=lineno,
            ))

    return rules


def model_external_id_to_name(external_id: str) -> str:
    """Convert 'model_sale_custom_wizard' to 'sale.custom.wizard'."""
    if external_id.startswith("model_"):
        return external_id[len("model_"):].replace("_", ".")
    return external_id.replace("_", ".")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/parsers/test_security_csv.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/odoo_doctor/parsers/security_csv.py tests/parsers/test_security_csv.py tests/fixtures/sample_addon/security/ir.model.access.csv
git commit -m "feat: security CSV parser for ir.model.access.csv"
```

---

### Task 12: Stub Infrastructure

**Files:**
- Create: `src/odoo_doctor/graph/stubs/loader.py`
- Create: `src/odoo_doctor/graph/stubs/build_stubs.py`
- Create: `src/odoo_doctor/graph/stubs/data/17.0.json` (minimal hand-crafted stub)
- Create: `tests/graph/test_resolver.py` (stub-related portion)

- [ ] **Step 1: Create minimal 17.0 stub data**

```json
{
    "version": "17.0",
    "models": {
        "res.partner": {
            "fields": ["name", "email", "phone", "street", "city", "country_id", "company_id", "parent_id", "child_ids", "user_ids", "active", "display_name", "create_date", "write_date"],
            "methods": ["name_get", "name_search", "create", "write", "unlink", "read", "copy", "default_get", "onchange", "action_archive", "action_unarchive"]
        },
        "res.users": {
            "fields": ["name", "login", "password", "partner_id", "company_id", "company_ids", "groups_id", "active"],
            "methods": ["name_get", "create", "write", "unlink", "read", "has_group", "action_reset_password"]
        },
        "res.company": {
            "fields": ["name", "partner_id", "currency_id", "logo", "street", "city", "country_id"],
            "methods": ["name_get", "create", "write"]
        },
        "sale.order": {
            "fields": ["name", "partner_id", "date_order", "state", "order_line", "amount_total", "amount_untaxed", "amount_tax", "company_id", "user_id", "pricelist_id", "currency_id"],
            "methods": ["name_get", "create", "write", "unlink", "action_confirm", "action_cancel", "action_draft", "action_quotation_sent", "_compute_amount_all"]
        },
        "sale.order.line": {
            "fields": ["name", "order_id", "product_id", "product_uom_qty", "price_unit", "price_subtotal", "price_total", "tax_id", "sequence"],
            "methods": ["create", "write", "unlink", "_compute_amount"]
        },
        "product.product": {
            "fields": ["name", "default_code", "barcode", "list_price", "standard_price", "categ_id", "type", "active", "weight", "volume"],
            "methods": ["name_get", "name_search", "create", "write"]
        },
        "product.template": {
            "fields": ["name", "default_code", "list_price", "standard_price", "categ_id", "type", "active", "description"],
            "methods": ["name_get", "create", "write"]
        },
        "account.move": {
            "fields": ["name", "partner_id", "date", "state", "move_type", "amount_total", "amount_residual", "journal_id", "company_id", "line_ids", "invoice_line_ids"],
            "methods": ["name_get", "create", "write", "unlink", "action_post", "button_draft", "button_cancel"]
        },
        "stock.picking": {
            "fields": ["name", "partner_id", "location_id", "location_dest_id", "state", "move_ids", "picking_type_id", "scheduled_date"],
            "methods": ["name_get", "create", "write", "action_confirm", "action_assign", "button_validate"]
        },
        "purchase.order": {
            "fields": ["name", "partner_id", "date_order", "state", "order_line", "amount_total", "company_id"],
            "methods": ["name_get", "create", "write", "button_confirm", "button_cancel", "button_draft"]
        },
        "mail.thread": {
            "fields": ["message_ids", "message_follower_ids", "message_partner_ids"],
            "methods": ["message_post", "message_subscribe", "message_unsubscribe"]
        },
        "ir.ui.view": {
            "fields": ["name", "model", "type", "arch", "inherit_id", "priority", "active"],
            "methods": ["create", "write", "unlink"]
        }
    },
    "xml_ids": {
        "base.main_company": "res.company",
        "base.user_root": "res.users",
        "base.user_admin": "res.users",
        "base.partner_root": "res.partner",
        "base.partner_admin": "res.partner",
        "base.group_user": "res.groups",
        "base.group_system": "res.groups",
        "base.group_no_one": "res.groups",
        "base.group_public": "res.groups",
        "sale.sale_menu_root": "ir.ui.menu",
        "sale.view_order_form": "ir.ui.view"
    }
}
```

Save as `src/odoo_doctor/graph/stubs/data/17.0.json`.

> **Note on stub versions:** MVP ships only 17.0.json (hand-crafted). After the
> build_stubs.py script is validated, generate 14.0, 15.0, 16.0, and 18.0 stubs
> by running the script against each Odoo source version. Until then, modules
> targeting other versions fall back to UNKNOWN resolution (safe by golden rule).

- [ ] **Step 2: Write the failing test**

```python
# tests/graph/test_resolver.py (stub loader portion)
"""Tests for stub loading."""

from __future__ import annotations

from odoo_doctor.graph.stubs.loader import StubData, load_stubs


def test_load_stubs_17():
    stubs = load_stubs("17.0")
    assert stubs is not None
    assert "res.partner" in stubs.models
    assert "name" in stubs.models["res.partner"]["fields"]
    assert "base.main_company" in stubs.xml_ids


def test_load_stubs_unknown_version():
    stubs = load_stubs("99.0")
    assert stubs is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/graph/test_resolver.py::test_load_stubs_17 -v`
Expected: FAIL

- [ ] **Step 4: Write implementation**

```python
# src/odoo_doctor/graph/stubs/loader.py
"""Load packaged stub data for common Odoo modules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


_STUBS_DIR = Path(__file__).parent / "data"


@dataclass
class StubData:
    version: str
    models: dict[str, dict]   # model_name -> {"fields": [...], "methods": [...]}
    xml_ids: dict[str, str]   # xml_id -> model


def load_stubs(odoo_version: str) -> StubData | None:
    """Load stub data for a given Odoo version. Returns None if not available."""
    # Try exact match first, then major version
    for candidate in [odoo_version, odoo_version.split(".")[0] + ".0"]:
        stub_file = _STUBS_DIR / f"{candidate}.json"
        if stub_file.exists():
            raw = json.loads(stub_file.read_text())
            return StubData(
                version=raw["version"],
                models=raw.get("models", {}),
                xml_ids=raw.get("xml_ids", {}),
            )
    return None
```

- [ ] **Step 5: Create build_stubs.py placeholder script**

```python
# src/odoo_doctor/graph/stubs/build_stubs.py
"""Offline script to generate stub data from Odoo source.

Usage: python -m odoo_doctor.graph.stubs.build_stubs /path/to/odoo 17.0

Parses all models, fields, methods, and XML IDs from the Odoo source tree
and writes a JSON stub file to data/<version>.json.

This is NOT run during normal odoo-doctor operation. It is a maintenance tool
for regenerating stubs when a new Odoo version is released.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def build_stubs(odoo_source: Path, version: str) -> dict:
    """Parse Odoo source and extract model/field/method/xmlid data."""
    models: dict[str, dict] = {}

    for py_file in odoo_source.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # Look for _name assignments
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if (isinstance(target, ast.Name) and target.id == "_name"
                                and isinstance(item.value, ast.Constant)):
                            model_name = item.value.value
                            if model_name not in models:
                                models[model_name] = {"fields": [], "methods": []}
                            _extract_members(node, models[model_name])

    return {"version": version, "models": models, "xml_ids": {}}


def _extract_members(cls: ast.ClassDef, model_data: dict) -> None:
    for item in cls.body:
        if isinstance(item, ast.Assign) and len(item.targets) == 1:
            target = item.targets[0]
            if isinstance(target, ast.Name) and isinstance(item.value, ast.Call):
                if target.id not in model_data["fields"] and not target.id.startswith("_"):
                    model_data["fields"].append(target.id)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name not in model_data["methods"]:
                model_data["methods"].append(item.name)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m odoo_doctor.graph.stubs.build_stubs /path/to/odoo 17.0")
        sys.exit(1)

    odoo_path = Path(sys.argv[1])
    ver = sys.argv[2]
    data = build_stubs(odoo_path, ver)
    out = Path(__file__).parent / "data" / f"{ver}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2))
    print(f"Wrote {len(data['models'])} models to {out}")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/graph/test_resolver.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add src/odoo_doctor/graph/stubs/ tests/graph/test_resolver.py
git commit -m "feat: stub infrastructure with 17.0 hand-crafted stubs"
```

---

### Task 13: Confidence-Aware Symbol Resolver

**Files:**
- Create: `src/odoo_doctor/graph/resolver.py`
- Modify: `tests/graph/test_resolver.py` (add resolver tests)

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_resolver.py — append these tests

from odoo_doctor.graph.resolver import ResolveResult, SymbolLookup, SymbolResolver
from odoo_doctor.parsers.python_models import FieldInfo, ModelInfo


def _make_resolver(repo_models=None, stub_version="17.0", source_path=None):
    return SymbolResolver(
        repo_models=repo_models or {},
        repo_xml_ids={},
        stub_version=stub_version,
        source_path=source_path,
    )


def test_resolve_field_from_repo():
    models = {
        "sale.custom": ModelInfo(
            name="sale.custom", file_path="f.py", line=1,
            fields={"my_field": FieldInfo(name="my_field", field_type="Char")},
        )
    }
    r = _make_resolver(repo_models=models)
    result = r.resolve_field("sale.custom", "my_field")
    assert result.status == ResolveResult.FOUND
    assert result.source == "repo"


def test_resolve_field_from_stub():
    r = _make_resolver()
    result = r.resolve_field("res.partner", "name")
    assert result.status == ResolveResult.FOUND
    assert result.source == "stub"


def test_resolve_field_not_found():
    """Field proven to not exist on a known model."""
    r = _make_resolver()
    result = r.resolve_field("res.partner", "zzz_nonexistent_field")
    assert result.status == ResolveResult.NOT_FOUND


def test_resolve_field_unknown_model():
    """Model not in repo or stubs -> UNKNOWN, not NOT_FOUND."""
    r = _make_resolver()
    result = r.resolve_field("totally.unknown.model", "any_field")
    assert result.status == ResolveResult.UNKNOWN


def test_resolve_model_found_in_stub():
    r = _make_resolver()
    result = r.resolve_model("sale.order")
    assert result.status == ResolveResult.FOUND


def test_resolve_model_unknown():
    r = _make_resolver()
    result = r.resolve_model("zzz.nonexistent")
    assert result.status == ResolveResult.UNKNOWN


def test_resolve_method_found():
    r = _make_resolver()
    result = r.resolve_method("sale.order", "action_confirm")
    assert result.status == ResolveResult.FOUND


def test_resolve_method_not_found():
    r = _make_resolver()
    result = r.resolve_method("sale.order", "zzz_method")
    assert result.status == ResolveResult.NOT_FOUND


def test_resolve_xml_id_found():
    r = _make_resolver()
    result = r.resolve_xml_id("base.main_company")
    assert result.status == ResolveResult.FOUND


def test_resolve_xml_id_unknown():
    r = _make_resolver()
    result = r.resolve_xml_id("nonexistent.xml_id")
    assert result.status == ResolveResult.UNKNOWN


def test_golden_rule_unknown_is_not_not_found():
    """The golden rule: UNKNOWN must never be treated as NOT_FOUND."""
    r = _make_resolver()
    field_result = r.resolve_field("unknown.model", "any_field")
    assert field_result.status != ResolveResult.NOT_FOUND
    assert field_result.status == ResolveResult.UNKNOWN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_resolver.py -v`
Expected: FAIL on new tests

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/graph/resolver.py
"""Confidence-aware symbol resolver: repo -> stubs -> source_path -> UNKNOWN."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from odoo_doctor.graph.stubs.loader import load_stubs

if TYPE_CHECKING:
    from odoo_doctor.parsers.python_models import ModelInfo
    from odoo_doctor.parsers.xml_records import XmlIdInfo


class ResolveResult(Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass
class SymbolLookup:
    status: ResolveResult
    source: str | None = None  # "repo" | "stub" | "source_path"


class SymbolResolver:
    """Resolve models, fields, methods, and XML IDs across the project.

    Resolution order: repo symbols -> packaged stubs -> optional source path -> UNKNOWN.
    """

    def __init__(
        self,
        repo_models: dict[str, ModelInfo],
        repo_xml_ids: dict[str, object],
        stub_version: str,
        source_path: str | None = None,
    ):
        self._repo_models = repo_models
        self._repo_xml_ids = repo_xml_ids
        self._stubs = load_stubs(stub_version)
        self._source_path = source_path
        # TODO: Phase for source_path parsing (post-MVP enhancement)

    def resolve_model(self, model_name: str) -> SymbolLookup:
        # 1. Repo
        if model_name in self._repo_models:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Stubs
        if self._stubs and model_name in self._stubs.models:
            return SymbolLookup(ResolveResult.FOUND, "stub")

        # 3. Source path (TODO: implement for post-MVP)

        # 4. Unknown — we can't say it doesn't exist
        return SymbolLookup(ResolveResult.UNKNOWN)

    def resolve_field(self, model_name: str, field_name: str) -> SymbolLookup:
        # 1. Repo
        repo_model = self._repo_models.get(model_name)
        if repo_model is not None:
            if field_name in repo_model.fields:
                return SymbolLookup(ResolveResult.FOUND, "repo")
            # Model known in repo but field not there — check stubs too
            # (model may inherit fields from core that aren't in the repo code)

        # 2. Stubs
        if self._stubs:
            stub_model = self._stubs.models.get(model_name)
            if stub_model is not None:
                if field_name in stub_model.get("fields", []):
                    return SymbolLookup(ResolveResult.FOUND, "stub")
                # Model is known (repo or stub) and field not found anywhere
                if repo_model is not None or stub_model is not None:
                    return SymbolLookup(ResolveResult.NOT_FOUND)

        # If model found in repo only (no stub for it), field not in repo
        if repo_model is not None:
            # We know the model but stubs don't cover it — could have
            # inherited fields we don't see. Be conservative.
            return SymbolLookup(ResolveResult.UNKNOWN)

        # Model not known at all
        return SymbolLookup(ResolveResult.UNKNOWN)

    def resolve_method(self, model_name: str, method_name: str) -> SymbolLookup:
        # 1. Repo
        repo_model = self._repo_models.get(model_name)
        if repo_model is not None and method_name in repo_model.methods:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Stubs
        if self._stubs:
            stub_model = self._stubs.models.get(model_name)
            if stub_model is not None:
                if method_name in stub_model.get("methods", []):
                    return SymbolLookup(ResolveResult.FOUND, "stub")
                # Model known, method not found
                if repo_model is not None or stub_model is not None:
                    return SymbolLookup(ResolveResult.NOT_FOUND)

        if repo_model is not None:
            return SymbolLookup(ResolveResult.UNKNOWN)

        return SymbolLookup(ResolveResult.UNKNOWN)

    def resolve_xml_id(self, xml_id: str) -> SymbolLookup:
        # 1. Repo
        if xml_id in self._repo_xml_ids:
            return SymbolLookup(ResolveResult.FOUND, "repo")

        # 2. Stubs
        if self._stubs and xml_id in self._stubs.xml_ids:
            return SymbolLookup(ResolveResult.FOUND, "stub")

        # XML IDs are module-scoped; we can't prove absence without full knowledge
        return SymbolLookup(ResolveResult.UNKNOWN)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_resolver.py -v`
Expected: 13 passed (2 stub + 11 resolver)

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/graph/resolver.py tests/graph/test_resolver.py
git commit -m "feat: confidence-aware symbol resolver with golden rule"
```

---

### Task 14: ModuleContext Builder

**Files:**
- Create: `src/odoo_doctor/graph/module_context.py`
- Create: `tests/graph/test_module_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_module_context.py
"""Tests for ModuleContext builder."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import ModuleContext, ProjectGraph, build_project_graph


def test_build_project_graph(sample_addon: Path):
    graph = build_project_graph(
        addon_paths=[sample_addon.parent],
        odoo_version="17.0",
        odoo_source_path=None,
    )
    assert len(graph.modules) == 1
    ctx = graph.modules["sample_addon"]
    assert ctx.name == "sample_addon"
    assert "sale" in ctx.depends
    assert ctx.resolver is graph.resolver  # shared reference


def test_module_context_has_parsed_data(sample_addon: Path):
    graph = build_project_graph(
        addon_paths=[sample_addon.parent],
        odoo_version="17.0",
    )
    ctx = graph.modules["sample_addon"]
    # Should have parsed models
    assert len(ctx.models) > 0
    # Should have parsed XML IDs
    assert len(ctx.xml_ids) > 0
    assert len(ctx.xml_records) >= len(ctx.xml_ids)
    # Should have parsed views
    assert len(ctx.views) > 0
    # Should have parsed access rules
    assert len(ctx.access_rules) > 0


def test_resolver_uses_manifest_version_for_stubs_when_project_unknown(sample_addon: Path):
    graph = build_project_graph(
        addon_paths=[sample_addon.parent],
        odoo_version="unknown",
    )
    result = graph.resolver.resolve_model("sale.order")
    from odoo_doctor.graph.resolver import ResolveResult
    assert result.status == ResolveResult.FOUND
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/graph/test_module_context.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/graph/module_context.py
"""ModuleContext and ProjectGraph — wires parsers and resolver together."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from odoo_doctor.discovery.addons import AddonInfo, discover_addons
from odoo_doctor.discovery.odoo_version import detect_odoo_version
from odoo_doctor.graph.resolver import SymbolResolver
from odoo_doctor.parsers.manifest import ManifestData, parse_manifest
from odoo_doctor.parsers.python_models import (
    ControllerInfo,
    ModelInfo,
    parse_controllers,
    parse_models,
)
from odoo_doctor.parsers.security_csv import AccessRule, parse_access_csv
from odoo_doctor.parsers.xml_records import ViewInfo, XmlIdInfo, parse_views, parse_xml_records


@dataclass
class ModuleContext:
    name: str
    path: Path
    odoo_version: str
    manifest: ManifestData
    depends: list[str]
    models: dict[str, ModelInfo]
    xml_ids: dict[str, XmlIdInfo]              # first definition per XML ID, for resolver lookup
    xml_records: list[XmlIdInfo]               # all definitions, including duplicates
    views: list[ViewInfo]
    controllers: list[ControllerInfo]
    access_rules: list[AccessRule]
    resolver: SymbolResolver = field(repr=False)


@dataclass
class ProjectGraph:
    modules: dict[str, ModuleContext]
    resolver: SymbolResolver


def build_project_graph(
    addon_paths: list[Path],
    odoo_version: str = "unknown",
    target_modules: list[str] | None = None,
    odoo_source_path: str | None = None,
) -> ProjectGraph:
    """Discover addons, parse all inputs, build shared resolver and per-module contexts."""
    addons = discover_addons(addon_paths, target_modules=target_modules)

    # First pass: collect all models and XML IDs across all modules (for resolver)
    all_models: dict[str, ModelInfo] = {}
    all_xml_ids: dict[str, XmlIdInfo] = {}
    module_data: dict[str, dict] = {}

    for addon in addons:
        manifest = parse_manifest(addon.path)
        if manifest is None:
            continue

        # Detect version per module
        mod_version = detect_odoo_version(
            manifest_version=manifest.version,
        )
        if mod_version == "unknown":
            mod_version = odoo_version

        # Parse Python files
        models: dict[str, ModelInfo] = {}
        controllers: list[ControllerInfo] = []
        for py_file in addon.path.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            for m in parse_models(py_file):
                key = m.name or (m.inherit[0] if m.inherit else None)
                if key:
                    if key in models:
                        # Merge fields/methods from multiple files
                        models[key].fields.update(m.fields)
                        models[key].methods.update(m.methods)
                        models[key].inherit = list(set(models[key].inherit + m.inherit))
                    else:
                        models[key] = m
            controllers.extend(parse_controllers(py_file))

        # Parse XML files
        xml_ids: dict[str, XmlIdInfo] = {}
        xml_records: list[XmlIdInfo] = []
        views: list[ViewInfo] = []
        for data_file in manifest.data:
            xml_path = addon.path / data_file
            if xml_path.suffix == ".xml" and xml_path.exists():
                for rec in parse_xml_records(xml_path, module_name=addon.name):
                    xml_records.append(rec)
                    xml_ids.setdefault(rec.xml_id, rec)
                views.extend(parse_views(xml_path, module_name=addon.name))

        # Parse security CSV
        access_rules: list[AccessRule] = []
        csv_path = addon.path / "security" / "ir.model.access.csv"
        if csv_path.exists():
            access_rules = parse_access_csv(csv_path, module_name=addon.name)

        all_models.update(models)
        all_xml_ids.update(xml_ids)

        module_data[addon.name] = {
            "addon": addon,
            "manifest": manifest,
            "version": mod_version,
            "models": models,
            "xml_ids": xml_ids,
            "xml_records": xml_records,
            "views": views,
            "controllers": controllers,
            "access_rules": access_rules,
        }

    # Use the detected module version for stubs when CLI/config did not provide one.
    resolver_version = odoo_version
    if resolver_version == "unknown":
        detected_versions = {
            data["version"] for data in module_data.values()
            if data["version"] != "unknown"
        }
        if len(detected_versions) == 1:
            resolver_version = next(iter(detected_versions))

    # Build shared resolver
    resolver = SymbolResolver(
        repo_models=all_models,
        repo_xml_ids=all_xml_ids,
        stub_version=resolver_version,
        source_path=odoo_source_path,
    )

    # Build per-module contexts
    modules: dict[str, ModuleContext] = {}
    for name, data in module_data.items():
        modules[name] = ModuleContext(
            name=name,
            path=data["addon"].path,
            odoo_version=data["version"],
            manifest=data["manifest"],
            depends=data["manifest"].depends,
            models=data["models"],
            xml_ids=data["xml_ids"],
            xml_records=data["xml_records"],
            views=data["views"],
            controllers=data["controllers"],
            access_rules=data["access_rules"],
            resolver=resolver,
        )

    return ProjectGraph(modules=modules, resolver=resolver)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/graph/test_module_context.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/graph/module_context.py tests/graph/test_module_context.py
git commit -m "feat: ModuleContext builder wiring parsers and shared resolver"
```

---

## Phase C — Rules

### Task 15: Rule Registry

**Files:**
- Create: `src/odoo_doctor/rules/registry.py`
- Create: `tests/rules/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules/test_registry.py
"""Tests for rule registry and @rule decorator."""

from __future__ import annotations

from odoo_doctor.rules.registry import RuleMetadata, RuleRegistry, rule


def test_rule_decorator_registers():
    registry = RuleRegistry()

    @rule(
        name="test-rule",
        category="Security",
        tier="P0",
        registry=registry,
    )
    def check_test(ctx):
        return []

    assert "test-rule" in registry
    meta, func = registry.get("test-rule")
    assert meta.category == "Security"
    assert meta.tier == "P0"
    assert meta.default_confidence == "high"
    assert meta.needs_context is False
    assert func is check_test


def test_registry_list_by_context():
    registry = RuleRegistry()

    @rule(name="r1", category="Security", tier="P0", needs_context=True, registry=registry)
    def check_r1(ctx):
        return []

    @rule(name="r2", category="Performance", tier="P1", needs_context=False, registry=registry)
    def check_r2(path, version):
        return []

    context_rules = registry.get_rules(needs_context=True)
    file_rules = registry.get_rules(needs_context=False)
    assert len(context_rules) == 1
    assert context_rules[0][0].name == "r1"
    assert len(file_rules) == 1


def test_registry_active_rules_map():
    registry = RuleRegistry()

    @rule(name="r1", category="Security", tier="P0", min_version="14.0", registry=registry)
    def check_r1(ctx):
        return []

    @rule(name="r2", category="Performance", tier="P1", registry=registry)
    def check_r2(ctx):
        return []

    active = registry.active_rules_map()
    assert active == {"r1": "14.0", "r2": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rules/test_registry.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/rules/registry.py
"""Rule registry with @rule decorator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class RuleMetadata:
    name: str
    category: str
    tier: str
    severity: str = "error"
    default_confidence: str = "high"
    needs_context: bool = False
    min_version: str | None = None


class RuleRegistry:
    """Stores registered rules and their metadata."""

    def __init__(self) -> None:
        self._rules: dict[str, tuple[RuleMetadata, Callable]] = {}

    def register(self, metadata: RuleMetadata, func: Callable) -> None:
        self._rules[metadata.name] = (metadata, func)

    def __contains__(self, name: str) -> bool:
        return name in self._rules

    def get(self, name: str) -> tuple[RuleMetadata, Callable]:
        return self._rules[name]

    def get_rules(
        self, needs_context: bool | None = None,
    ) -> list[tuple[RuleMetadata, Callable]]:
        results = list(self._rules.values())
        if needs_context is not None:
            results = [(m, f) for m, f in results if m.needs_context == needs_context]
        return results

    def active_rules_map(self) -> dict[str, str | None]:
        """Return {rule_name: min_version} for pipeline version-gating."""
        return {m.name: m.min_version for m, _ in self._rules.values()}

    def all_names(self) -> list[str]:
        return list(self._rules.keys())


# Global default registry
default_registry = RuleRegistry()


def rule(
    name: str,
    category: str,
    tier: str,
    severity: str = "error",
    default_confidence: str = "high",
    needs_context: bool = False,
    min_version: str | None = None,
    registry: RuleRegistry | None = None,
) -> Callable:
    """Decorator to register a native rule."""
    def decorator(func: Callable) -> Callable:
        meta = RuleMetadata(
            name=name,
            category=category,
            tier=tier,
            severity=severity,
            default_confidence=default_confidence,
            needs_context=needs_context,
            min_version=min_version,
        )
        target = registry or default_registry
        target.register(meta, func)
        return func
    return decorator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/rules/test_registry.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/rules/registry.py tests/rules/test_registry.py
git commit -m "feat: rule registry with @rule decorator"
```

---

### Task 16: Manifest Rules

**Files:**
- Create: `src/odoo_doctor/rules/manifest/missing_required_fields.py`
- Create: `src/odoo_doctor/rules/manifest/missing_dependency.py`
- Create: `tests/rules/test_manifest_rules.py`
- Create: `tests/fixtures/bad_addon/__manifest__.py`

- [ ] **Step 1: Create bad_addon fixture**

```python
# tests/fixtures/bad_addon/__manifest__.py
{
    "name": "Broken Addon",
    "version": "17.0.1.0.0",
    "depends": ["sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/broken_views.xml",
    ],
}
```

Note: missing `license` key and `installable`.

- [ ] **Step 2: Write the failing test**

```python
# tests/rules/test_manifest_rules.py
"""Tests for manifest rules."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.manifest.missing_required_fields import check_missing_required_fields
from odoo_doctor.rules.manifest.missing_dependency import check_missing_dependency


def test_missing_required_fields_catches_no_license(bad_addon: Path):
    graph = build_project_graph([bad_addon.parent], odoo_version="17.0")
    ctx = graph.modules["bad_addon"]
    diags = check_missing_required_fields(ctx)
    rules_found = {d.rule for d in diags}
    assert "manifest-missing-required-fields" in rules_found
    msgs = " ".join(d.message for d in diags)
    assert "license" in msgs


def test_missing_required_fields_clean(sample_addon: Path):
    graph = build_project_graph([sample_addon.parent], odoo_version="17.0")
    ctx = graph.modules["sample_addon"]
    diags = check_missing_required_fields(ctx)
    assert len(diags) == 0


def test_missing_dependency_catches_undeclared(tmp_path: Path):
    """Module uses stock.picking model but doesn't declare stock in depends."""
    mod = tmp_path / "test_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "Test", "depends": ["sale"], "data": [], "license": "LGPL-3"}')
    models_dir = mod / "models"
    models_dir.mkdir()
    (models_dir / "__init__.py").write_text("")
    (models_dir / "test.py").write_text(
        'from odoo import models\n'
        'class X(models.Model):\n'
        '    _name = "test.model"\n'
        '    def do_stuff(self):\n'
        '        self.env["stock.picking"].search([])\n'
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    diags = check_missing_dependency(ctx)
    rules_found = {d.rule for d in diags}
    assert "manifest-missing-dependency" in rules_found
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/rules/test_manifest_rules.py -v`
Expected: FAIL

- [ ] **Step 4: Write implementations**

```python
# src/odoo_doctor/rules/manifest/missing_required_fields.py
"""Rule: manifest-missing-required-fields [Module Hygiene, P2]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

_REQUIRED_KEYS = ["license", "depends"]
_RECOMMENDED_KEYS = ["installable", "data"]


@rule(
    name="manifest-missing-required-fields",
    category="Module Hygiene",
    tier="P2",
    severity="warning",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_missing_required_fields(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    raw = ctx.manifest.raw

    for key in _REQUIRED_KEYS:
        if key not in raw:
            diags.append(Diagnostic(
                module=ctx.name,
                file_path="__manifest__.py",
                line=1,
                column=0,
                rule="manifest-missing-required-fields",
                category="Module Hygiene",
                severity="warning",
                tier="P2",
                source="native",
                confidence="high",
                title=f"Missing manifest key: {key}",
                message=f"__manifest__.py is missing the '{key}' key.",
                help=f"Add '{key}' to __manifest__.py. This is expected by Odoo and many tools.",
                odoo_version=ctx.odoo_version,
            ))

    return diags
```

```python
# src/odoo_doctor/rules/manifest/missing_dependency.py
"""Rule: manifest-missing-dependency [Module Hygiene, P1]."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

# Map of model prefix -> addon that provides it
_KNOWN_MODEL_PREFIXES: dict[str, str] = {
    "sale.": "sale",
    "purchase.": "purchase",
    "stock.": "stock",
    "account.": "account",
    "product.": "product",
    "mail.": "mail",
    "hr.": "hr",
    "project.": "project",
    "crm.": "crm",
    "website.": "website",
    "mrp.": "mrp",
}

_ENV_REF_RE = re.compile(r'self\.env\[(["\'])(.+?)\1\]')


@rule(
    name="manifest-missing-dependency",
    category="Module Hygiene",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_missing_dependency(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    declared_depends = set(ctx.depends)
    # Always implicitly depends on base
    declared_depends.add("base")

    referenced_models: set[str] = set()

    # Scan Python files for self.env["model.name"] patterns
    for py_file in ctx.path.rglob("*.py"):
        if py_file.name.startswith("__"):
            continue
        try:
            source = py_file.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for match in _ENV_REF_RE.finditer(source):
            referenced_models.add(match.group(2))

    # Check each referenced model against known prefixes
    missing: dict[str, str] = {}  # addon -> example model
    for model in referenced_models:
        for prefix, addon in _KNOWN_MODEL_PREFIXES.items():
            if model.startswith(prefix) and addon not in declared_depends:
                if addon not in missing:
                    missing[addon] = model

    for addon, example_model in missing.items():
        diags.append(Diagnostic(
            module=ctx.name,
            file_path="__manifest__.py",
            line=1,
            column=0,
            rule="manifest-missing-dependency",
            category="Module Hygiene",
            severity="error",
            tier="P1",
            source="native",
            confidence="high",
            title=f"Missing dependency: {addon}",
            message=f"Code references '{example_model}' but '{addon}' is not in depends.",
            help=f"Add '{addon}' to the depends list in __manifest__.py.",
            odoo_version=ctx.odoo_version,
        ))

    return diags
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/rules/test_manifest_rules.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/odoo_doctor/rules/manifest/ tests/rules/test_manifest_rules.py tests/fixtures/bad_addon/__manifest__.py
git commit -m "feat: manifest rules (missing-required-fields, missing-dependency)"
```

---

### Task 17: Security Rules

**Files:**
- Create: `src/odoo_doctor/rules/security/missing_access_csv.py`
- Create: `src/odoo_doctor/rules/security/unknown_model_in_access_csv.py`
- Create: `src/odoo_doctor/rules/security/raw_sql_interpolation.py`
- Create: `tests/rules/test_security_rules.py`
- Create: `tests/fixtures/bad_addon/models/broken.py`
- Create: `tests/fixtures/bad_addon/security/ir.model.access.csv`

- [ ] **Step 1: Create bad_addon security fixtures**

```python
# tests/fixtures/bad_addon/models/broken.py
from odoo import api, fields, models


class BrokenModel(models.Model):
    _name = "broken.model"
    _description = "Broken Model"

    name = fields.Char()

    def unsafe_query(self, user_input):
        self.env.cr.execute(f"SELECT * FROM res_partner WHERE name = '{user_input}'")
        return self.env.cr.fetchall()

    def also_unsafe(self, table):
        query = "DELETE FROM %s" % table
        self.env.cr.execute(query)
```

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_nonexistent,nonexistent access,model_nonexistent_model,base.group_user,1,1,1,1
```

Save CSV as `tests/fixtures/bad_addon/security/ir.model.access.csv`.

- [ ] **Step 2: Write the failing test**

```python
# tests/rules/test_security_rules.py
"""Tests for security rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.security.missing_access_csv import check_missing_access_csv
from odoo_doctor.rules.security.unknown_model_in_access_csv import check_unknown_model_in_access_csv
from odoo_doctor.rules.security.raw_sql_interpolation import check_raw_sql_interpolation


def test_missing_access_csv_catches(bad_addon: Path):
    graph = build_project_graph([bad_addon.parent], odoo_version="17.0")
    ctx = graph.modules["bad_addon"]
    diags = check_missing_access_csv(ctx)
    # broken.model is declared but has no matching access rule
    assert any(d.rule == "missing-access-csv" for d in diags)


def test_missing_access_csv_clean(sample_addon: Path):
    graph = build_project_graph([sample_addon.parent], odoo_version="17.0")
    ctx = graph.modules["sample_addon"]
    diags = check_missing_access_csv(ctx)
    # sample_addon's wizard has access rule defined
    assert len(diags) == 0


def test_unknown_model_in_access_csv(bad_addon: Path):
    graph = build_project_graph([bad_addon.parent], odoo_version="17.0")
    ctx = graph.modules["bad_addon"]
    diags = check_unknown_model_in_access_csv(ctx)
    # CSV references model_nonexistent_model which doesn't exist
    assert any(d.rule == "unknown-model-in-access-csv" for d in diags)
    assert all(d.confidence == "high" for d in diags)


def test_unknown_model_in_access_csv_does_not_flag_external_unknown(tmp_path: Path):
    """External/unscanned model references are UNKNOWN and must not emit by default."""
    mod = tmp_path / "test_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "Test", "depends": [], "data": [], "license": "LGPL-3"}')
    sec = mod / "security"
    sec.mkdir()
    (sec / "ir.model.access.csv").write_text(
        "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
        "access_ext,external,other_module.model_missing,base.group_user,1,0,0,0\n"
    )
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["test_mod"]
    assert check_unknown_model_in_access_csv(ctx) == []


def test_raw_sql_catches_fstring(bad_addon: Path):
    diags = check_raw_sql_interpolation(
        bad_addon / "models" / "broken.py", "bad_addon", "17.0"
    )
    assert len(diags) >= 1
    assert all(d.rule == "raw-sql-string-interpolation" for d in diags)


def test_raw_sql_catches_variable_indirection(bad_addon: Path):
    diags = check_raw_sql_interpolation(
        bad_addon / "models" / "broken.py", "bad_addon", "17.0"
    )
    messages = " ".join(d.message for d in diags)
    assert "variable interpolation" in messages


def test_raw_sql_clean(sample_addon: Path):
    diags = check_raw_sql_interpolation(
        sample_addon / "models" / "sale_custom.py", "sample_addon", "17.0"
    )
    assert len(diags) == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/rules/test_security_rules.py -v`
Expected: FAIL

- [ ] **Step 4: Write implementations**

```python
# src/odoo_doctor/rules/security/missing_access_csv.py
"""Rule: missing-access-csv [Security, P0]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.parsers.security_csv import model_external_id_to_name
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="missing-access-csv",
    category="Security",
    tier="P0",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_missing_access_csv(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    # Collect model names that have access rules
    covered_models: set[str] = set()
    for ar in ctx.access_rules:
        model_name = model_external_id_to_name(ar.model_external_id)
        covered_models.add(model_name)

    # Check each persistent model declared in this module
    for model_name, model_info in ctx.models.items():
        if model_info.is_abstract or model_info.is_transient:
            continue
        if model_info.name is None:
            continue  # _inherit only, no new model
        if model_info.name in covered_models:
            continue

        diags.append(Diagnostic(
            module=ctx.name,
            file_path=model_info.file_path,
            line=model_info.line,
            column=0,
            rule="missing-access-csv",
            category="Security",
            severity="error",
            tier="P0",
            source="native",
            confidence="high",
            title=f"No access rules for model '{model_info.name}'",
            message=f"Model '{model_info.name}' is a persistent model with no entry in ir.model.access.csv.",
            help="Add an access rule in security/ir.model.access.csv for this model.",
            odoo_version=ctx.odoo_version,
        ))

    return diags
```

```python
# src/odoo_doctor/rules/security/unknown_model_in_access_csv.py
"""Rule: unknown-model-in-access-csv [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.parsers.security_csv import model_external_id_to_name
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="unknown-model-in-access-csv",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_unknown_model_in_access_csv(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    local_model_names = {
        m.name for m in ctx.models.values()
        if m.name is not None
    }

    for ar in ctx.access_rules:
        model_name = model_external_id_to_name(ar.model_external_id)
        if ctx.resolver.resolve_model(model_name).status == ResolveResult.FOUND:
            continue

        # High-confidence absence only for model external IDs owned by this scanned module.
        # External/unscanned module references are UNKNOWN and must not emit by default.
        if ar.model_external_id_module != ctx.name or model_name in local_model_names:
            continue

        diags.append(Diagnostic(
            module=ctx.name,
            file_path=ar.file_path,
            line=ar.line,
            column=0,
            rule="unknown-model-in-access-csv",
            category="Correctness",
            severity="error",
            tier="P1",
            source="native",
            confidence="high",
            title=f"Access CSV references unknown model '{model_name}'",
            message=f"ir.model.access.csv entry '{ar.id}' references model '{model_name}' which cannot be resolved.",
            help="Verify the model_id:id column matches an existing model external ID.",
            odoo_version=ctx.odoo_version,
        ))

    return diags
```

```python
# src/odoo_doctor/rules/security/raw_sql_interpolation.py
"""Rule: raw-sql-string-interpolation [Security, P0]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule


@rule(
    name="raw-sql-string-interpolation",
    category="Security",
    tier="P0",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_raw_sql_interpolation(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return []

    for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        unsafe_vars = _find_unsafe_sql_assignments(func)
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue

            # Match *.cr.execute(...) or *.env.cr.execute(...)
            if not _is_cr_execute(node.func):
                continue

            if not node.args:
                continue

            first_arg = node.args[0]
            pattern = _unsafe_sql_pattern(first_arg)
            if pattern:
                diags.append(_make_diag(file_path, module_name, odoo_version, node, pattern))
                continue

            if isinstance(first_arg, ast.Name) and first_arg.id in unsafe_vars:
                diags.append(_make_diag(file_path, module_name, odoo_version, node, "variable interpolation"))

    return diags


def _is_cr_execute(func: ast.expr) -> bool:
    """Check if the call is to *.cr.execute or *.execute on a cursor."""
    if isinstance(func, ast.Attribute) and func.attr == "execute":
        val = func.value
        if isinstance(val, ast.Attribute) and val.attr == "cr":
            return True
        if isinstance(val, ast.Attribute) and val.attr == "execute":
            return False
    return False


def _involves_non_literal(node: ast.BinOp) -> bool:
    """Check if a BinOp (string concat) involves non-constant parts."""
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            return True
    return False


def _unsafe_sql_pattern(node: ast.AST) -> str | None:
    if isinstance(node, ast.JoinedStr):
        return "f-string"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return "% formatting"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "format":
            return ".format()"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        if _involves_non_literal(node):
            return "string concatenation"
    return None


def _find_unsafe_sql_assignments(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    unsafe: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        if _unsafe_sql_pattern(node.value) is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                unsafe.add(target.id)
    return unsafe


def _make_diag(
    file_path: Path, module: str, version: str, node: ast.Call, pattern: str
) -> Diagnostic:
    return Diagnostic(
        module=module,
        file_path=str(file_path),
        line=node.lineno,
        column=node.col_offset,
        rule="raw-sql-string-interpolation",
        category="Security",
        severity="error",
        tier="P0",
        source="native",
        confidence="high",
        title="SQL injection via " + pattern,
        message=f"cr.execute() uses {pattern} at line {node.lineno}. This is a SQL injection risk.",
        help="Use parameterized queries: cr.execute('SELECT ... WHERE x = %s', (param,))",
        odoo_version=version,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/rules/test_security_rules.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add src/odoo_doctor/rules/security/ tests/rules/test_security_rules.py tests/fixtures/bad_addon/
git commit -m "feat: security rules (missing-access-csv, unknown-model, raw-sql)"
```

---

### Task 18: XML/View Rules

**Files:**
- Create: `src/odoo_doctor/rules/xml/duplicate_xml_id.py`
- Create: `src/odoo_doctor/rules/xml/missing_xml_ref.py`
- Create: `src/odoo_doctor/rules/xml/view_field_not_in_model.py`
- Create: `src/odoo_doctor/rules/xml/button_method_not_found.py`
- Create: `tests/rules/test_xml_rules.py`
- Create: `tests/fixtures/bad_addon/views/broken_views.xml`

- [ ] **Step 1: Create bad_addon XML fixture**

```xml
<!-- tests/fixtures/bad_addon/views/broken_views.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_broken_form" model="ir.ui.view">
        <field name="name">broken.model.form</field>
        <field name="model">broken.model</field>
        <field name="arch" type="xml">
            <form>
                <field name="name"/>
                <field name="nonexistent_field"/>
                <button name="nonexistent_method" type="object" string="Do"/>
            </form>
        </field>
    </record>

    <!-- Duplicate XML ID -->
    <record id="view_broken_form" model="ir.ui.view">
        <field name="name">broken.model.form.dup</field>
        <field name="model">broken.model</field>
        <field name="arch" type="xml">
            <form>
                <field name="name"/>
            </form>
        </field>
    </record>

    <!-- Reference to nonexistent record -->
    <menuitem id="menu_broken"
              name="Broken Menu"
              action="nonexistent_action"
              parent="sale.sale_menu_root"/>
</odoo>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/rules/test_xml_rules.py
"""Tests for XML/view rules."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.rules.xml.duplicate_xml_id import check_duplicate_xml_id
from odoo_doctor.rules.xml.missing_xml_ref import check_missing_xml_ref
from odoo_doctor.rules.xml.view_field_not_in_model import check_view_field_not_in_model
from odoo_doctor.rules.xml.button_method_not_found import check_button_method_not_found


def test_duplicate_xml_id(bad_addon: Path):
    graph = build_project_graph([bad_addon.parent], odoo_version="17.0")
    ctx = graph.modules["bad_addon"]
    diags = check_duplicate_xml_id(ctx)
    assert any(d.rule == "duplicate-xml-id" for d in diags)
    assert len([r for r in ctx.xml_records if r.xml_id == "bad_addon.view_broken_form"]) == 2


def test_duplicate_xml_id_clean(sample_addon: Path):
    graph = build_project_graph([sample_addon.parent], odoo_version="17.0")
    ctx = graph.modules["sample_addon"]
    diags = check_duplicate_xml_id(ctx)
    assert len(diags) == 0


def test_view_field_not_in_model(bad_addon: Path):
    graph = build_project_graph([bad_addon.parent], odoo_version="17.0")
    ctx = graph.modules["bad_addon"]
    diags = check_view_field_not_in_model(ctx)
    assert any("nonexistent_field" in d.message for d in diags)


def test_view_field_clean(sample_addon: Path):
    graph = build_project_graph([sample_addon.parent], odoo_version="17.0")
    ctx = graph.modules["sample_addon"]
    diags = check_view_field_not_in_model(ctx)
    assert len(diags) == 0


def test_button_method_not_found(bad_addon: Path):
    graph = build_project_graph([bad_addon.parent], odoo_version="17.0")
    ctx = graph.modules["bad_addon"]
    diags = check_button_method_not_found(ctx)
    assert any("nonexistent_method" in d.message for d in diags)


def test_button_method_clean(sample_addon: Path):
    graph = build_project_graph([sample_addon.parent], odoo_version="17.0")
    ctx = graph.modules["sample_addon"]
    diags = check_button_method_not_found(ctx)
    assert len(diags) == 0


def test_resolver_unknown_results_do_not_emit_default_errors(tmp_path: Path):
    """UNKNOWN resolver results are omitted in normal mode, not emitted as low-confidence errors."""
    mod = tmp_path / "unknown_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "Unknown", "depends": [], "data": ["views/views.xml"], "license": "LGPL-3"}')
    views_dir = mod / "views"
    views_dir.mkdir()
    (views_dir / "views.xml").write_text("""\
<odoo>
  <record id="view_unknown_form" model="ir.ui.view">
    <field name="model">external.unknown</field>
    <field name="arch" type="xml">
      <form>
        <field name="x_name"/>
        <button name="action_x" type="object"/>
      </form>
    </field>
  </record>
</odoo>
""")
    graph = build_project_graph([tmp_path], odoo_version="17.0")
    ctx = graph.modules["unknown_mod"]
    assert check_view_field_not_in_model(ctx) == []
    assert check_button_method_not_found(ctx) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/rules/test_xml_rules.py -v`
Expected: FAIL

- [ ] **Step 4: Write implementations**

```python
# src/odoo_doctor/rules/xml/duplicate_xml_id.py
"""Rule: duplicate-xml-id [Correctness, P1]."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="duplicate-xml-id",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_duplicate_xml_id(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    # Count occurrences by scanning all XML files again for raw IDs
    id_locations: dict[str, list[tuple[str, int]]] = {}
    for info in ctx.xml_records:
        id_locations.setdefault(info.xml_id, []).append((info.file_path, info.line))

    for xml_id, locations in id_locations.items():
        if len(locations) <= 1:
            continue
        for file_path, line in locations[1:]:  # flag all duplicates after the first
            diags.append(Diagnostic(
                module=ctx.name,
                file_path=file_path,
                line=line,
                column=0,
                rule="duplicate-xml-id",
                category="Correctness",
                severity="error",
                tier="P1",
                source="native",
                confidence="high",
                title=f"Duplicate XML ID: {xml_id}",
                message=f"XML ID '{xml_id}' is defined multiple times. First at {locations[0][0]}:{locations[0][1]}.",
                help="Remove or rename the duplicate XML ID.",
                odoo_version=ctx.odoo_version,
            ))

    return diags
```

```python
# src/odoo_doctor/rules/xml/missing_xml_ref.py
"""Rule: missing-xml-ref [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="missing-xml-ref",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_missing_xml_ref(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for xml_id, info in ctx.xml_ids.items():
        for ref in info.refs:
            # Qualify the ref with module name if not already qualified
            qualified = ref if "." in ref else f"{ctx.name}.{ref}"
            lookup = ctx.resolver.resolve_xml_id(qualified)

            if lookup.status == ResolveResult.NOT_FOUND:
                confidence = "high"
            elif lookup.status == ResolveResult.UNKNOWN:
                continue
            else:
                continue

            diags.append(Diagnostic(
                module=ctx.name,
                file_path=info.file_path,
                line=info.line,
                column=0,
                rule="missing-xml-ref",
                category="Correctness",
                severity="error",
                tier="P1",
                source="native",
                confidence=confidence,
                title=f"Unresolved XML reference: {ref}",
                message=f"XML record '{xml_id}' references '{ref}' which cannot be resolved.",
                help="Verify the referenced XML ID exists and the providing module is in depends.",
                odoo_version=ctx.odoo_version,
            ))

    # Also check inherit_id refs in views
    for view in ctx.views:
        if view.inherit_id:
            qualified = view.inherit_id if "." in view.inherit_id else f"{ctx.name}.{view.inherit_id}"
            lookup = ctx.resolver.resolve_xml_id(qualified)
            if lookup.status == ResolveResult.FOUND:
                continue
            if lookup.status == ResolveResult.UNKNOWN:
                continue
            confidence = "high"
            diags.append(Diagnostic(
                module=ctx.name,
                file_path=view.file_path,
                line=view.line,
                column=0,
                rule="missing-xml-ref",
                category="Correctness",
                severity="error",
                tier="P1",
                source="native",
                confidence=confidence,
                title=f"Unresolved inherit_id: {view.inherit_id}",
                message=f"View '{view.xml_id}' inherits from '{view.inherit_id}' which cannot be resolved.",
                help="Verify the parent view exists and the providing module is in depends.",
                odoo_version=ctx.odoo_version,
            ))

    return diags
```

```python
# src/odoo_doctor/rules/xml/view_field_not_in_model.py
"""Rule: view-field-not-in-model [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="view-field-not-in-model",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_view_field_not_in_model(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for view in ctx.views:
        if not view.model:
            continue

        for field_name in view.field_refs:
            lookup = ctx.resolver.resolve_field(view.model, field_name)

            if lookup.status == ResolveResult.FOUND:
                continue

            if lookup.status == ResolveResult.NOT_FOUND:
                confidence = "high"
            else:
                continue

            diags.append(Diagnostic(
                module=ctx.name,
                file_path=view.file_path,
                line=view.line,
                column=0,
                rule="view-field-not-in-model",
                category="Correctness",
                severity="error",
                tier="P1",
                source="native",
                confidence=confidence,
                title=f"View references unknown field '{field_name}'",
                message=f"View '{view.xml_id}' for model '{view.model}' references field '{field_name}' which is not found on the model.",
                help=f"Add field '{field_name}' to model '{view.model}' or remove it from the view.",
                odoo_version=ctx.odoo_version,
            ))

    return diags
```

```python
# src/odoo_doctor/rules/xml/button_method_not_found.py
"""Rule: button-method-not-found [Correctness, P1]."""

from __future__ import annotations

from typing import TYPE_CHECKING

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.graph.resolver import ResolveResult
from odoo_doctor.rules.registry import rule

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext


@rule(
    name="button-method-not-found",
    category="Correctness",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=True,
    min_version="14.0",
)
def check_button_method_not_found(ctx: ModuleContext) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for view in ctx.views:
        if not view.model:
            continue

        for method_name in view.button_methods:
            lookup = ctx.resolver.resolve_method(view.model, method_name)

            if lookup.status == ResolveResult.FOUND:
                continue

            if lookup.status == ResolveResult.NOT_FOUND:
                confidence = "high"
            else:
                continue

            diags.append(Diagnostic(
                module=ctx.name,
                file_path=view.file_path,
                line=view.line,
                column=0,
                rule="button-method-not-found",
                category="Correctness",
                severity="error",
                tier="P1",
                source="native",
                confidence=confidence,
                title=f"Button calls unknown method '{method_name}'",
                message=f"View '{view.xml_id}' has button calling '{method_name}' on model '{view.model}' which is not found.",
                help=f"Add method '{method_name}' to model '{view.model}' or fix the button name attribute.",
                odoo_version=ctx.odoo_version,
            ))

    return diags
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/rules/test_xml_rules.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add src/odoo_doctor/rules/xml/ tests/rules/test_xml_rules.py tests/fixtures/bad_addon/views/
git commit -m "feat: XML rules (duplicate-id, missing-ref, field-not-in-model, button-not-found)"
```

---

### Task 19: Performance Rules

**Files:**
- Create: `src/odoo_doctor/rules/performance/search_in_loop.py`
- Create: `tests/rules/test_performance_rules.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules/test_performance_rules.py
"""Tests for performance rules."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.performance.search_in_loop import check_search_in_loop


def test_search_in_loop_catches(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def bad_method(self):
                for rec in self:
                    partner = self.env["res.partner"].search([("name", "=", rec.name)])
    """)
    f = tmp_path / "bad.py"
    f.write_text(code)
    diags = check_search_in_loop(f, "test_mod", "17.0")
    assert len(diags) >= 1
    assert diags[0].rule == "search-in-loop"


def test_search_in_loop_clean(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def good_method(self):
                partners = self.env["res.partner"].search([("active", "=", True)])
                for p in partners:
                    print(p.name)
    """)
    f = tmp_path / "good.py"
    f.write_text(code)
    diags = check_search_in_loop(f, "test_mod", "17.0")
    assert len(diags) == 0


def test_search_in_loop_nested(tmp_path: Path):
    code = dedent("""\
        from odoo import models

        class X(models.Model):
            _name = "x"

            def nested(self):
                for order in self:
                    for line in order.order_line:
                        self.env["product.product"].browse(line.product_id.id)
    """)
    f = tmp_path / "nested.py"
    f.write_text(code)
    diags = check_search_in_loop(f, "test_mod", "17.0")
    assert len(diags) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rules/test_performance_rules.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/rules/performance/search_in_loop.py
"""Rule: search-in-loop [Performance, P1]."""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.rules.registry import rule

_ORM_METHODS = {"search", "search_count", "browse", "read", "write", "create"}


@rule(
    name="search-in-loop",
    category="Performance",
    tier="P1",
    severity="error",
    default_confidence="high",
    needs_context=False,
    min_version="14.0",
)
def check_search_in_loop(
    file_path: Path, module_name: str, odoo_version: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return []

    _walk_for_loops(tree, diags, file_path, module_name, odoo_version)
    return diags


def _walk_for_loops(
    node: ast.AST,
    diags: list[Diagnostic],
    file_path: Path,
    module: str,
    version: str,
) -> None:
    """Recursively find ORM calls inside for/while loops."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.For, ast.While)):
            _check_loop_body(child, diags, file_path, module, version)
        _walk_for_loops(child, diags, file_path, module, version)


def _check_loop_body(
    loop: ast.For | ast.While,
    diags: list[Diagnostic],
    file_path: Path,
    module: str,
    version: str,
) -> None:
    """Check if any ORM method call exists inside a loop body."""
    for node in ast.walk(loop):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in _ORM_METHODS:
            # Heuristic: check if the call target looks like an env[] expression
            # or self/recordset method
            diags.append(Diagnostic(
                module=module,
                file_path=str(file_path),
                line=node.lineno,
                column=node.col_offset,
                rule="search-in-loop",
                category="Performance",
                severity="error",
                tier="P1",
                source="native",
                confidence="high",
                title=f"ORM '{node.func.attr}' called inside loop",
                message=f"'{node.func.attr}()' at line {node.lineno} is called inside a loop. Consider batching.",
                help=f"Move the '{node.func.attr}()' call outside the loop and batch the operation.",
                odoo_version=version,
            ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/rules/test_performance_rules.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/rules/performance/ tests/rules/test_performance_rules.py
git commit -m "feat: search-in-loop performance rule"
```

---

### Task 20: Inline Suppression Scanner

**Files:**
- Create: `src/odoo_doctor/rules/suppression.py`
- Create: `tests/rules/test_suppression.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/rules/test_suppression.py
"""Tests for inline suppression scanner."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from odoo_doctor.rules.suppression import scan_python_suppressions, scan_xml_suppressions


def test_python_suppression(tmp_path: Path):
    code = dedent("""\
        x = 1
        # odoo-doctor: disable=search-in-loop
        for r in self:
            self.env["res.partner"].search([])
    """)
    f = tmp_path / "test.py"
    f.write_text(code)
    suppressions = scan_python_suppressions(f)
    # Should suppress line 3 (the next code line after the comment)
    assert ("test.py", 3, "search-in-loop") in suppressions or \
           (str(f), 3, "search-in-loop") in suppressions


def test_xml_suppression(tmp_path: Path):
    xml = dedent("""\
        <?xml version="1.0"?>
        <odoo>
            <!-- odoo-doctor: disable=view-field-not-in-model -->
            <field name="x_dynamic"/>
        </odoo>
    """)
    f = tmp_path / "views.xml"
    f.write_text(xml)
    suppressions = scan_xml_suppressions(f)
    assert any(rule == "view-field-not-in-model" for _, _, rule in suppressions)


def test_no_suppressions(tmp_path: Path):
    f = tmp_path / "clean.py"
    f.write_text("x = 1\n")
    assert scan_python_suppressions(f) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rules/test_suppression.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/rules/suppression.py
"""Scan for inline suppression comments: # odoo-doctor: disable=<rule>."""

from __future__ import annotations

import re
import tokenize
from pathlib import Path

from lxml import etree

_SUPPRESS_RE = re.compile(r"odoo-doctor:\s*disable=([a-z0-9_-]+(?:,\s*[a-z0-9_-]+)*)")

Suppressions = set[tuple[str, int, str]]  # (file_path, line, rule)


def scan_python_suppressions(file_path: Path) -> Suppressions:
    """Scan a Python file for inline suppression comments."""
    suppressions: Suppressions = set()

    try:
        with open(file_path, "rb") as f:
            tokens = list(tokenize.tokenize(f.readline))
    except (tokenize.TokenError, SyntaxError, OSError):
        return suppressions

    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        match = _SUPPRESS_RE.search(tok.string)
        if not match:
            continue

        rules = [r.strip() for r in match.group(1).split(",")]
        # Suppression applies to the next line
        suppress_line = tok.start[0] + 1
        for rule_name in rules:
            suppressions.add((str(file_path), suppress_line, rule_name))

    return suppressions


def scan_xml_suppressions(file_path: Path) -> Suppressions:
    """Scan an XML file for inline suppression comments."""
    suppressions: Suppressions = set()

    try:
        tree = etree.parse(str(file_path))
    except etree.XMLSyntaxError:
        return suppressions

    for comment in tree.iter(etree.Comment):
        match = _SUPPRESS_RE.search(comment.text or "")
        if not match:
            continue

        rules = [r.strip() for r in match.group(1).split(",")]
        # Next sibling element line
        suppress_line = (comment.sourceline or 0) + 1
        for rule_name in rules:
            suppressions.add((str(file_path), suppress_line, rule_name))

    return suppressions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/rules/test_suppression.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/rules/suppression.py tests/rules/test_suppression.py
git commit -m "feat: inline suppression scanner for Python and XML"
```

---

## Phase D — Adapters

### Task 21: Ruff Adapter

**Files:**
- Create: `src/odoo_doctor/adapters/base.py`
- Create: `src/odoo_doctor/adapters/ruff/adapter.py`
- Create: `src/odoo_doctor/adapters/ruff/rule_mapping.toml`
- Create: `tests/adapters/test_ruff.py`
- Create: `tests/fixtures/adapters/ruff_output.json`

- [ ] **Step 1: Create recorded Ruff output fixture**

```json
[
    {
        "code": "E501",
        "message": "Line too long (120 > 88)",
        "filename": "models/sale.py",
        "location": {"row": 15, "column": 1},
        "end_location": {"row": 15, "column": 120}
    },
    {
        "code": "F841",
        "message": "Local variable 'x' is assigned to but never used",
        "filename": "models/sale.py",
        "location": {"row": 42, "column": 5},
        "end_location": {"row": 42, "column": 6}
    }
]
```

Save as `tests/fixtures/adapters/ruff_output.json`.

- [ ] **Step 2: Create rule mapping**

```toml
# src/odoo_doctor/adapters/ruff/rule_mapping.toml
# Ruff rule code -> Odoo Doctor category/tier/confidence

[rules]
"S608" = { category = "Security", tier = "P1", confidence = "high" }
"S301" = { category = "Security", tier = "P0", confidence = "high" }
"E501" = { category = "Maintainability", tier = "P3", confidence = "high" }
"F841" = { category = "Correctness", tier = "P3", confidence = "high" }
"F811" = { category = "Correctness", tier = "P2", confidence = "high" }
"W605" = { category = "Correctness", tier = "P3", confidence = "high" }
```

- [ ] **Step 3: Write the failing test**

```python
# tests/adapters/test_ruff.py
"""Tests for Ruff adapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from odoo_doctor.adapters.base import BackendAdapter
from odoo_doctor.adapters.ruff.adapter import RuffAdapter


def test_ruff_adapter_is_backend_adapter():
    adapter = RuffAdapter()
    assert adapter.name == "ruff"


def test_ruff_adapter_parse_output(fixtures_dir: Path):
    adapter = RuffAdapter()
    raw = json.loads((fixtures_dir / "adapters" / "ruff_output.json").read_text())
    diags = adapter._parse_output(raw, module_name="test_mod", odoo_version="17.0")
    assert len(diags) == 2
    assert all(d.source == "ruff" for d in diags)
    assert diags[0].rule == "E501"


def test_ruff_adapter_applies_rule_mapping(fixtures_dir: Path):
    adapter = RuffAdapter()
    raw = json.loads((fixtures_dir / "adapters" / "ruff_output.json").read_text())
    diags = adapter._parse_output(raw, module_name="test_mod", odoo_version="17.0")
    e501 = next(d for d in diags if d.rule == "E501")
    assert e501.category == "Maintainability"
    assert e501.tier == "P3"


def test_ruff_adapter_unmapped_rule(fixtures_dir: Path):
    adapter = RuffAdapter()
    raw = [{"code": "UNKNOWN999", "message": "something", "filename": "f.py",
            "location": {"row": 1, "column": 1}, "end_location": {"row": 1, "column": 1}}]
    diags = adapter._parse_output(raw, module_name="m", odoo_version="17.0")
    assert diags[0].category == "Uncategorized"
    assert diags[0].tier == "P3"
    assert diags[0].confidence == "low"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/adapters/test_ruff.py -v`
Expected: FAIL

- [ ] **Step 5: Write implementations**

```python
# src/odoo_doctor/adapters/base.py
"""BackendAdapter protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from odoo_doctor.core.diagnostics import Diagnostic


class BackendAdapter(Protocol):
    name: str

    def is_available(self) -> bool:
        """Check if the external tool is installed."""
        ...

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        """Run the tool and return normalized diagnostics."""
        ...
```

```python
# src/odoo_doctor/adapters/ruff/adapter.py
"""Ruff adapter — runs ruff check and maps output to Diagnostic."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from odoo_doctor.core.diagnostics import Diagnostic


@dataclass
class _RuleMapping:
    category: str
    tier: str
    confidence: str


_UNMAPPED = _RuleMapping(category="Uncategorized", tier="P3", confidence="low")


class RuffAdapter:
    name = "ruff"

    def __init__(self) -> None:
        self._mapping = self._load_mapping()

    def is_available(self) -> bool:
        return shutil.which("ruff") is not None

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        if not self.is_available():
            return []

        try:
            result = subprocess.run(
                ["ruff", "check", "--output-format=json", str(module_path)],
                capture_output=True, text=True, timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        try:
            raw = json.loads(result.stdout) if result.stdout else []
        except json.JSONDecodeError:
            return []

        return self._parse_output(raw, module_name=module_path.name, odoo_version=odoo_version)

    def _parse_output(
        self, raw: list[dict], module_name: str, odoo_version: str
    ) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        for item in raw:
            code = item.get("code", "")
            mapping = self._mapping.get(code, _UNMAPPED)

            diags.append(Diagnostic(
                module=module_name,
                file_path=item.get("filename", ""),
                line=item.get("location", {}).get("row", 0),
                column=item.get("location", {}).get("column", 0),
                rule=code,
                category=mapping.category,
                severity="warning" if mapping.tier in ("P2", "P3") else "error",
                tier=mapping.tier,
                source="ruff",
                confidence=mapping.confidence,
                title=f"Ruff {code}",
                message=item.get("message", ""),
                help=f"See Ruff docs for rule {code}.",
                url=f"https://docs.astral.sh/ruff/rules/{code}",
                odoo_version=odoo_version,
            ))
        return diags

    def _load_mapping(self) -> dict[str, _RuleMapping]:
        mapping_file = Path(__file__).parent / "rule_mapping.toml"
        if not mapping_file.exists():
            return {}
        with open(mapping_file, "rb") as f:
            raw = tomllib.load(f)
        result: dict[str, _RuleMapping] = {}
        for code, info in raw.get("rules", {}).items():
            result[code] = _RuleMapping(
                category=info["category"],
                tier=info["tier"],
                confidence=info.get("confidence", "high"),
            )
        return result
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/adapters/test_ruff.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add src/odoo_doctor/adapters/ tests/adapters/test_ruff.py tests/fixtures/adapters/
git commit -m "feat: Ruff adapter with rule mapping"
```

---

### Task 22: Pylint-Odoo Adapter

**Files:**
- Create: `src/odoo_doctor/adapters/pylint_odoo/adapter.py`
- Create: `src/odoo_doctor/adapters/pylint_odoo/rule_mapping.toml`
- Create: `tests/adapters/test_pylint_odoo.py`
- Create: `tests/fixtures/adapters/pylint_odoo_output.txt`

- [ ] **Step 1: Create recorded Pylint-Odoo output fixture**

```text
************* Module models.sale
models/sale.py:10:0: W8120: Translation method is missing (translation-required)
models/sale.py:25:0: E8102: Use of cr.execute with string interpolation (sql-injection)
```

Save as `tests/fixtures/adapters/pylint_odoo_output.txt`.

- [ ] **Step 2: Create rule mapping**

```toml
# src/odoo_doctor/adapters/pylint_odoo/rule_mapping.toml

[rules]
"E8102" = { category = "Security", tier = "P0", confidence = "high" }
"W8120" = { category = "Maintainability", tier = "P3", confidence = "medium" }
"C8101" = { category = "Module Hygiene", tier = "P3", confidence = "high" }
"W8110" = { category = "Correctness", tier = "P2", confidence = "high" }
"E8501" = { category = "Security", tier = "P1", confidence = "high" }
```

- [ ] **Step 3: Write the failing test**

```python
# tests/adapters/test_pylint_odoo.py
"""Tests for Pylint-Odoo adapter."""

from __future__ import annotations

from pathlib import Path

from odoo_doctor.adapters.pylint_odoo.adapter import PylintOdooAdapter


def test_pylint_adapter_name():
    adapter = PylintOdooAdapter()
    assert adapter.name == "pylint-odoo"


def test_pylint_parse_output(fixtures_dir: Path):
    adapter = PylintOdooAdapter()
    raw_text = (fixtures_dir / "adapters" / "pylint_odoo_output.txt").read_text()
    diags = adapter._parse_output(raw_text, module_name="test_mod", odoo_version="17.0")
    assert len(diags) == 2
    assert all(d.source == "pylint-odoo" for d in diags)

    sql = next(d for d in diags if d.rule == "E8102")
    assert sql.category == "Security"
    assert sql.tier == "P0"

    trans = next(d for d in diags if d.rule == "W8120")
    assert trans.category == "Maintainability"


def test_pylint_unmapped_rule():
    adapter = PylintOdooAdapter()
    raw_text = "f.py:1:0: C9999: Unknown rule (unknown-rule)\n"
    diags = adapter._parse_output(raw_text, module_name="m", odoo_version="17.0")
    assert diags[0].category == "Uncategorized"
    assert diags[0].confidence == "low"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/adapters/test_pylint_odoo.py -v`
Expected: FAIL

- [ ] **Step 5: Write implementation**

```python
# src/odoo_doctor/adapters/pylint_odoo/adapter.py
"""Pylint-Odoo adapter — runs pylint with odoo plugin and maps output."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from odoo_doctor.core.diagnostics import Diagnostic

_LINE_RE = re.compile(
    r"^(.+?):(\d+):(\d+):\s+([A-Z]\d+):\s+(.+?)(?:\s+\(([^)]+)\))?\s*$"
)


@dataclass
class _RuleMapping:
    category: str
    tier: str
    confidence: str


_UNMAPPED = _RuleMapping(category="Uncategorized", tier="P3", confidence="low")


class PylintOdooAdapter:
    name = "pylint-odoo"

    def __init__(self) -> None:
        self._mapping = self._load_mapping()

    def is_available(self) -> bool:
        return shutil.which("pylint") is not None

    def run(self, module_path: Path, odoo_version: str) -> list[Diagnostic]:
        if not self.is_available():
            return []

        try:
            result = subprocess.run(
                [
                    "pylint",
                    "--load-plugins=pylint_odoo",
                    "--output-format=text",
                    str(module_path),
                ],
                capture_output=True, text=True, timeout=120,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        return self._parse_output(
            result.stdout or "", module_name=module_path.name, odoo_version=odoo_version
        )

    def _parse_output(
        self, raw_text: str, module_name: str, odoo_version: str
    ) -> list[Diagnostic]:
        diags: list[Diagnostic] = []

        for line in raw_text.strip().splitlines():
            match = _LINE_RE.match(line.strip())
            if not match:
                continue

            file_path, line_no, col, code, message, _symbol = match.groups()
            mapping = self._mapping.get(code, _UNMAPPED)

            diags.append(Diagnostic(
                module=module_name,
                file_path=file_path,
                line=int(line_no),
                column=int(col),
                rule=code,
                category=mapping.category,
                severity="warning" if mapping.tier in ("P2", "P3") else "error",
                tier=mapping.tier,
                source="pylint-odoo",
                confidence=mapping.confidence,
                title=f"Pylint-Odoo {code}",
                message=message.strip(),
                help=f"See Pylint-Odoo docs for {code}.",
                url=f"https://github.com/OCA/pylint-odoo",
                odoo_version=odoo_version,
            ))
        return diags

    def _load_mapping(self) -> dict[str, _RuleMapping]:
        mapping_file = Path(__file__).parent / "rule_mapping.toml"
        if not mapping_file.exists():
            return {}
        with open(mapping_file, "rb") as f:
            raw = tomllib.load(f)
        result: dict[str, _RuleMapping] = {}
        for code, info in raw.get("rules", {}).items():
            result[code] = _RuleMapping(
                category=info["category"],
                tier=info["tier"],
                confidence=info.get("confidence", "high"),
            )
        return result
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/adapters/test_pylint_odoo.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add src/odoo_doctor/adapters/pylint_odoo/ tests/adapters/test_pylint_odoo.py tests/fixtures/adapters/pylint_odoo_output.txt
git commit -m "feat: Pylint-Odoo adapter with rule mapping"
```

---

## Phase E — Output & CLI

### Task 23: Terminal Reporter

**Files:**
- Create: `src/odoo_doctor/reporters/terminal.py`
- Create: `tests/reporters/test_terminal.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/reporters/test_terminal.py
"""Tests for terminal reporter."""

from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import CategoryScore, ScoreResult
from odoo_doctor.reporters.terminal import render_terminal


def _diag(**overrides) -> Diagnostic:
    defaults = dict(
        module="sale_custom", file_path="models/sale.py", line=42, column=0,
        rule="raw-sql", category="Security", severity="error", tier="P0",
        source="native", confidence="high", title="SQL injection",
        message="cr.execute uses f-string", help="Use params", odoo_version="17.0",
    )
    defaults.update(overrides)
    return Diagnostic(**defaults)


def test_render_terminal_returns_string():
    diags = [_diag()]
    score = ScoreResult(
        overall=75.0, label="Good",
        categories=[CategoryScore("Security", 75, 1, 25.0)],
        in_scope_categories=["Security"],
        diagnostics_counted=1,
    )
    output = render_terminal(diags, {"sale_custom": score})
    assert "sale_custom" in output
    assert "75" in output
    assert "SQL injection" in output


def test_render_terminal_empty():
    output = render_terminal([], {})
    assert "No diagnostics" in output or "clean" in output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reporters/test_terminal.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/reporters/terminal.py
"""Terminal reporter using rich."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from odoo_doctor.core.diagnostics import Diagnostic
    from odoo_doctor.core.scoring import ScoreResult


_LABEL_COLORS = {
    "Excellent": "green",
    "Good": "blue",
    "Needs work": "yellow",
    "Critical": "red",
}


def render_terminal(
    diagnostics: list[Diagnostic],
    scores: dict[str, ScoreResult],
) -> str:
    """Render diagnostics and scores to a string for terminal output."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=120)

    if not diagnostics and not scores:
        console.print("[green]No diagnostics found. All clean![/green]")
        return buf.getvalue()

    # Score summary per module
    for module, score in scores.items():
        color = _LABEL_COLORS.get(score.label, "white")
        console.print(f"\n[bold]{module}[/bold]  Score: [{color}]{score.overall:.0f}/100 ({score.label})[/{color}]")

        if score.categories:
            table = Table(show_header=True, header_style="bold")
            table.add_column("Category")
            table.add_column("Score", justify="right")
            table.add_column("Findings", justify="right")
            for cs in score.categories:
                if cs.category not in score.in_scope_categories:
                    continue
                table.add_row(cs.category, str(cs.score), str(cs.finding_count))
            console.print(table)

    # Diagnostics grouped by module
    by_module: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        by_module.setdefault(d.module, []).append(d)

    for module, diags in by_module.items():
        console.print(f"\n[bold underline]Findings for {module}[/bold underline]")
        # Sort by tier priority then line
        sorted_diags = sorted(diags, key=lambda d: (d.tier, d.file_path, d.line))
        for d in sorted_diags:
            sev_color = "red" if d.severity == "error" else "yellow"
            conf_mark = "" if d.confidence == "high" else f" [{d.confidence}]"
            console.print(
                f"  [{sev_color}]{d.tier}[/{sev_color}] "
                f"{d.file_path}:{d.line} "
                f"[bold]{d.title}[/bold]{conf_mark}"
            )
            console.print(f"      {d.message}")
            console.print(f"      [dim]{d.help}[/dim]")

    return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reporters/test_terminal.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/reporters/terminal.py tests/reporters/test_terminal.py
git commit -m "feat: terminal reporter with rich"
```

---

### Task 24: JSON Reporter

**Files:**
- Create: `src/odoo_doctor/reporters/json_report.py`
- Create: `tests/reporters/test_json_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/reporters/test_json_report.py
"""Tests for JSON reporter."""

from __future__ import annotations

import json

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.scoring import CategoryScore, ScoreResult
from odoo_doctor.reporters.json_report import render_json


def _diag(**overrides) -> Diagnostic:
    defaults = dict(
        module="m", file_path="f.py", line=1, column=0,
        rule="r", category="Security", severity="error", tier="P0",
        source="native", confidence="high", title="t", message="msg",
        help="h", odoo_version="17.0",
    )
    defaults.update(overrides)
    return Diagnostic(**defaults)


def test_render_json_valid():
    diags = [_diag()]
    scores = {"m": ScoreResult(75.0, "Good", [CategoryScore("Security", 75, 1, 25.0)], ["Security"], 1)}
    output = render_json(diags, scores)
    parsed = json.loads(output)
    assert "modules" in parsed
    assert parsed["modules"]["m"]["score"]["overall"] == 75.0
    assert len(parsed["modules"]["m"]["diagnostics"]) == 1


def test_render_json_empty():
    output = render_json([], {})
    parsed = json.loads(output)
    assert parsed["modules"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reporters/test_json_report.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/reporters/json_report.py
"""JSON reporter — stable schema for agents and CI."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo_doctor.core.diagnostics import Diagnostic
    from odoo_doctor.core.scoring import ScoreResult


def render_json(
    diagnostics: list[Diagnostic],
    scores: dict[str, ScoreResult],
) -> str:
    """Render scan results as JSON."""
    by_module: dict[str, list[Diagnostic]] = {}
    for d in diagnostics:
        by_module.setdefault(d.module, []).append(d)

    modules: dict[str, dict] = {}
    for module_name, score in scores.items():
        module_diags = by_module.get(module_name, [])
        modules[module_name] = {
            "score": {
                "overall": score.overall,
                "label": score.label,
                "categories": [
                    {
                        "category": cs.category,
                        "score": cs.score,
                        "finding_count": cs.finding_count,
                    }
                    for cs in score.categories
                    if cs.category in score.in_scope_categories
                ],
                "diagnostics_counted": score.diagnostics_counted,
            },
            "diagnostics": [asdict(d) for d in module_diags],
        }

    return json.dumps({"version": "0.1.0", "modules": modules}, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reporters/test_json_report.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/reporters/json_report.py tests/reporters/test_json_report.py
git commit -m "feat: JSON reporter for agents and CI"
```

---

### Task 25: CLI App

**Files:**
- Create: `src/odoo_doctor/cli/app.py`
- Create: `tests/cli/test_app.py`

This is the main entry point wiring everything together.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_app.py
"""Tests for the CLI app."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def test_scan_sample_addon(sample_addon: Path):
    result = runner.invoke(app, ["scan", str(sample_addon.parent)])
    assert result.exit_code == 0
    assert "sample_addon" in result.stdout


def test_scan_json_output(sample_addon: Path):
    result = runner.invoke(app, ["scan", str(sample_addon.parent), "--json"])
    assert result.exit_code == 0
    import json
    parsed = json.loads(result.stdout)
    assert "modules" in parsed


def test_scan_nonexistent_path():
    result = runner.invoke(app, ["scan", "/nonexistent/path"])
    assert result.exit_code == 0  # no addons found, but doesn't crash


def test_scan_uses_config_addons_paths(tmp_path: Path):
    addons = tmp_path / "addons"
    addons.mkdir()
    mod = addons / "x_mod"
    mod.mkdir()
    (mod / "__manifest__.py").write_text('{"name": "X", "version": "17.0.1.0.0", "depends": [], "data": [], "license": "LGPL-3"}')
    (tmp_path / "odoo-doctor.toml").write_text('[odoo-doctor]\naddons_paths = ["addons"]\n')
    result = runner.invoke(app, ["scan", str(tmp_path), "--json"])
    assert result.exit_code == 0
    import json
    parsed = json.loads(result.stdout)
    assert "x_mod" in parsed["modules"]


def test_rules_list():
    result = runner.invoke(app, ["rules", "list"])
    assert result.exit_code == 0
    assert "missing-access-csv" in result.stdout


def test_init_creates_config(tmp_path: Path):
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "odoo-doctor.toml").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_app.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/odoo_doctor/cli/app.py
"""Odoo Doctor CLI — main entry point."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from odoo_doctor.core.config import OdooDoctorConfig, load_config
from odoo_doctor.core.diagnostics import CATEGORIES
from odoo_doctor.core.pipeline import run_pipeline
from odoo_doctor.core.scoring import score_diagnostics, Diagnostic
from odoo_doctor.discovery.addons import discover_addons
from odoo_doctor.discovery.odoo_version import detect_odoo_version
from odoo_doctor.graph.module_context import build_project_graph
from odoo_doctor.reporters.json_report import render_json
from odoo_doctor.reporters.terminal import render_terminal
from odoo_doctor.rules.suppression import scan_python_suppressions, scan_xml_suppressions

# Import all rule modules to trigger @rule registration
import odoo_doctor.rules.manifest.missing_required_fields  # noqa: F401
import odoo_doctor.rules.manifest.missing_dependency  # noqa: F401
import odoo_doctor.rules.security.missing_access_csv  # noqa: F401
import odoo_doctor.rules.security.unknown_model_in_access_csv  # noqa: F401
import odoo_doctor.rules.security.raw_sql_interpolation  # noqa: F401
import odoo_doctor.rules.xml.duplicate_xml_id  # noqa: F401
import odoo_doctor.rules.xml.missing_xml_ref  # noqa: F401
import odoo_doctor.rules.xml.view_field_not_in_model  # noqa: F401
import odoo_doctor.rules.xml.button_method_not_found  # noqa: F401
import odoo_doctor.rules.performance.search_in_loop  # noqa: F401

from odoo_doctor.rules.registry import default_registry
from odoo_doctor.adapters.ruff.adapter import RuffAdapter
from odoo_doctor.adapters.pylint_odoo.adapter import PylintOdooAdapter

app = typer.Typer(name="odoo-doctor", help="Unified health scoring for Odoo custom addons.")


@app.command()
def scan(
    path: str = typer.Argument(".", help="Path to scan for addons"),
    odoo_version: Optional[str] = typer.Option(None, "--odoo-version", help="Target Odoo version"),
    module: Optional[str] = typer.Option(None, "--module", help="Scan only this module"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    fail_on: Optional[str] = typer.Option(None, "--fail-on", help="Fail if severity found (error|warning)"),
    diff: Optional[str] = typer.Option(None, "--diff", help="Only scan files changed vs this branch"),
) -> None:
    """Scan Odoo addons and report health score."""
    scan_path = Path(path).resolve()

    # Load config
    cfg = load_config(scan_path)
    if odoo_version:
        cfg.odoo_version = odoo_version
    target = [module] if module else cfg.target_modules or None
    addons_paths = [(scan_path / p).resolve() for p in cfg.addons_paths]

    # Determine changed files for --diff
    changed_files: set[str] | None = None
    if diff:
        changed_files = _get_changed_files(scan_path, diff)

    # Build project graph
    version = cfg.odoo_version or "unknown"
    graph = build_project_graph(
        addon_paths=addons_paths,
        odoo_version=version,
        target_modules=target,
        odoo_source_path=cfg.odoo_source_path or None,
    )

    if not graph.modules:
        if json_output:
            typer.echo(render_json([], {}))
        else:
            typer.echo("No addons found.")
        return

    # Detect version from first module if still unknown
    if version == "unknown" and graph.modules:
        first_ctx = next(iter(graph.modules.values()))
        version = first_ctx.odoo_version

    # Collect all diagnostics
    all_diags: list[Diagnostic] = []

    # Run native rules
    for meta, func in default_registry.get_rules(needs_context=True):
        for ctx in graph.modules.values():
            all_diags.extend(func(ctx))

    for meta, func in default_registry.get_rules(needs_context=False):
        for ctx in graph.modules.values():
            for py_file in ctx.path.rglob("*.py"):
                if py_file.name.startswith("__"):
                    continue
                all_diags.extend(func(py_file, ctx.name, ctx.odoo_version))

    # Run adapters
    adapters = []
    if cfg.adapters.get("ruff", True):
        adapters.append(RuffAdapter())
    if cfg.adapters.get("pylint_odoo", True):
        adapters.append(PylintOdooAdapter())

    for adapter in adapters:
        if not adapter.is_available():
            continue
        for ctx in graph.modules.values():
            try:
                all_diags.extend(adapter.run(ctx.path, ctx.odoo_version))
            except Exception:
                pass  # adapter crash -> skip

    # Filter by changed files if --diff
    if changed_files is not None:
        all_diags = [d for d in all_diags if d.file_path in changed_files
                     or any(d.file_path.endswith(cf) for cf in changed_files)]

    # Collect suppressions
    suppressions: set[tuple[str, int, str]] = set()
    for ctx in graph.modules.values():
        for py_file in ctx.path.rglob("*.py"):
            suppressions |= scan_python_suppressions(py_file)
        for data_file in ctx.manifest.data:
            xml_path = ctx.path / data_file
            if xml_path.suffix == ".xml" and xml_path.exists():
                suppressions |= scan_xml_suppressions(xml_path)

    # Run pipeline
    active_rules = default_registry.active_rules_map()
    diags, eligible = run_pipeline(
        all_diags, cfg, suppressions, active_rules, version,
    )

    # Determine in-scope categories
    in_scope = _in_scope_categories(active_rules, cfg)

    # Score per module
    scores: dict[str, object] = {}
    for module_name in graph.modules:
        mod_diags = [d for d in diags if d.module == module_name]
        mod_elig = [e for d, e in zip(diags, eligible) if d.module == module_name]
        scores[module_name] = score_diagnostics(
            mod_diags, mod_elig,
            category_weights=cfg.category_weights,
            in_scope_categories=in_scope,
        )

    # Output
    if json_output:
        typer.echo(render_json(diags, scores))
    else:
        typer.echo(render_terminal(diags, scores))

    # Fail on
    if fail_on:
        if any(d.severity == fail_on for d in diags):
            raise typer.Exit(code=1)


@app.command("rules")
def rules_cmd(
    action: str = typer.Argument("list", help="list or explain"),
    rule_name: Optional[str] = typer.Argument(None, help="Rule name to explain"),
) -> None:
    """List rules or explain a specific rule."""
    if action == "list":
        for meta, _ in default_registry.get_rules():
            typer.echo(f"  {meta.name:40s} [{meta.category}, {meta.tier}]")
    elif action == "explain" and rule_name:
        if rule_name in default_registry:
            meta, _ = default_registry.get(rule_name)
            typer.echo(f"Rule: {meta.name}")
            typer.echo(f"Category: {meta.category}")
            typer.echo(f"Tier: {meta.tier}")
            typer.echo(f"Severity: {meta.severity}")
            typer.echo(f"Confidence: {meta.default_confidence}")
            typer.echo(f"Needs module context: {meta.needs_context}")
            typer.echo(f"Min Odoo version: {meta.min_version or 'any'}")
        else:
            typer.echo(f"Unknown rule: {rule_name}")


@app.command()
def init(
    path: str = typer.Option(".", "--path", help="Where to create odoo-doctor.toml"),
) -> None:
    """Create a default odoo-doctor.toml config file."""
    config_path = Path(path) / "odoo-doctor.toml"
    if config_path.exists():
        typer.echo(f"Config already exists at {config_path}")
        return

    config_path.write_text("""\
[odoo-doctor]
# odoo_version = "17.0"
# addons_paths = ["."]
# odoo_source_path = ""
# min_score = 60

[adapters]
ruff = true
pylint_odoo = true
oca = false

[severity]
# "search-in-loop" = "warning"

[ignore]
rules = []
files = ["**/migrations/**"]
modules = []

[category_weights]
# Security = 1.0
# Performance = 1.5
""")
    typer.echo(f"Created {config_path}")


@app.command()
def install() -> None:
    """Install agent skills and optional git hooks."""
    import shutil
    skills_src = Path(__file__).parent.parent.parent.parent / "skills"
    if not skills_src.exists():
        typer.echo("Skills directory not found in package. Reinstall odoo-doctor.")
        raise typer.Exit(code=1)

    # Copy skills to current working directory
    dest = Path.cwd() / ".odoo-doctor" / "skills"
    dest.mkdir(parents=True, exist_ok=True)
    for skill_dir in skills_src.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            target = dest / skill_dir.name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(skill_dir, target)
            typer.echo(f"  Installed skill: {skill_dir.name}")

    typer.echo(f"Skills installed to {dest}")
    typer.echo("Run 'odoo-doctor scan --diff --json' from your agent.")


def _get_changed_files(repo_path: Path, base_branch: str) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_branch],
            capture_output=True, text=True, cwd=repo_path, timeout=30,
        )
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()


def _in_scope_categories(
    active_rules: dict[str, str | None],
    cfg: OdooDoctorConfig,
) -> list[str]:
    """Determine which categories have at least one active rule."""
    from odoo_doctor.rules.registry import default_registry
    rule_categories: set[str] = set()
    for meta, _ in default_registry.get_rules():
        rule_categories.add(meta.category)
    return [c for c in CATEGORIES if c in rule_categories]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/cli/test_app.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/odoo_doctor/cli/app.py tests/cli/test_app.py
git commit -m "feat: CLI app with scan, rules, init, install commands"
```

---

### Task 26: Agent Skills

**Files:**
- Create: `skills/odoo-doctor/SKILL.md`
- Create: `skills/odoo-doctor-explain/SKILL.md`

- [ ] **Step 1: Write the odoo-doctor skill**

```markdown
<!-- skills/odoo-doctor/SKILL.md -->
---
name: odoo-doctor
description: Use after editing Odoo addon code or when asked to scan, fix, or check module health.
---

# Odoo Doctor Scan & Fix

## When to use
- After making changes to Odoo addon code
- When the user asks to "scan", "check", "fix diagnostics", or "check module health"
- Before committing Odoo code changes

## Workflow

1. Run scan on changed files:
   ```bash
   odoo-doctor scan . --diff main --json
   ```

2. Parse the JSON output and prioritize findings:
   - Fix P0 (critical) issues first — these are security or install-blocking
   - Then P1 (serious) — broken views, missing access, ORM misuse
   - P2 and P3 can be noted but are lower priority

3. For each finding, read the `help` field for fix guidance.

4. After fixing, re-run the scan to verify:
   ```bash
   odoo-doctor scan . --diff main --json
   ```

5. Repeat until no P0/P1 findings remain.

## Important
- Only fix findings with `confidence: "high"`. Low-confidence findings may be false positives.
- Do not suppress rules without asking the user first.
- If a finding seems wrong, run `odoo-doctor rules explain <rule-name>` before suppressing.
```

- [ ] **Step 2: Write the odoo-doctor-explain skill**

```markdown
<!-- skills/odoo-doctor-explain/SKILL.md -->
---
name: odoo-doctor-explain
description: Use when the user asks why a rule fired, wants to understand a finding, or wants to tune config.
---

# Odoo Doctor Explain & Configure

## When to use
- User asks "why did this rule fire?" or "what does this error mean?"
- User wants to disable or change severity of a rule
- User wants to understand how scoring works

## Workflow

1. Explain the rule:
   ```bash
   odoo-doctor rules explain <rule-name>
   ```

2. If the user wants to change behavior, apply the **narrowest** config change:
   - To disable for one file: use inline suppression `# odoo-doctor: disable=<rule>`
   - To change severity: add to `[severity]` in `odoo-doctor.toml`
   - To disable entirely: add to `[ignore] rules` in `odoo-doctor.toml`

3. Never disable a rule globally without discussing with the user first.

## Config location
The config file is `odoo-doctor.toml` at the repository root.
```

- [ ] **Step 3: Commit**

```bash
git add skills/
git commit -m "feat: agent skills (odoo-doctor, odoo-doctor-explain)"
```

---

## Phase F — Integration

### Task 27: End-to-End Integration Test

**Files:**
- Create: `tests/integration/test_end_to_end.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_end_to_end.py
"""End-to-end integration test — scan bad_addon and verify results."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from odoo_doctor.cli.app import app

runner = CliRunner()


def test_end_to_end_bad_addon(bad_addon: Path):
    """Scan bad_addon and verify it catches the expected issues."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent), "--json"])
    assert result.exit_code == 0

    parsed = json.loads(result.stdout)
    assert "bad_addon" in parsed["modules"]

    mod = parsed["modules"]["bad_addon"]
    rules_found = {d["rule"] for d in mod["diagnostics"]}

    # Must catch these (success criteria from spec):
    assert "missing-access-csv" in rules_found, "Should catch missing access rules"
    assert "raw-sql-string-interpolation" in rules_found, "Should catch unsafe SQL"
    assert "duplicate-xml-id" in rules_found, "Should catch duplicate XML IDs"

    # Score should be below 100 (issues found)
    assert mod["score"]["overall"] < 100


def test_end_to_end_clean_addon(sample_addon: Path):
    """Scan sample_addon — should have few or no high-confidence findings."""
    result = runner.invoke(app, ["scan", str(sample_addon.parent), "--json"])
    assert result.exit_code == 0

    parsed = json.loads(result.stdout)
    assert "sample_addon" in parsed["modules"]

    mod = parsed["modules"]["sample_addon"]
    high_confidence = [d for d in mod["diagnostics"] if d["confidence"] == "high"]

    # Clean addon should have minimal high-confidence findings
    # (may have some from adapters if installed, but native rules should be clean)
    native_high = [d for d in high_confidence if d["source"] == "native"]
    assert len(native_high) == 0, f"Clean addon should have no native high-confidence findings: {native_high}"


def test_end_to_end_terminal_output(bad_addon: Path):
    """Verify terminal output renders without crashing."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent)])
    assert result.exit_code == 0
    assert "bad_addon" in result.stdout
    assert "Score:" in result.stdout or "score" in result.stdout.lower()


def test_end_to_end_fail_on(bad_addon: Path):
    """--fail-on error should exit non-zero when errors exist."""
    result = runner.invoke(app, ["scan", str(bad_addon.parent), "--fail-on", "error"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/integration/
git commit -m "test: end-to-end integration tests for bad and clean addons"
```

- [ ] **Step 4: Final full test run**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass, covering the complete MVP pipeline from discovery through scoring.

- [ ] **Step 5: Tag MVP**

```bash
git tag -a v0.1.0 -m "MVP: 10 native rules, Ruff/Pylint-Odoo adapters, confidence-aware scoring"
```
