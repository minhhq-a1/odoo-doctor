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
