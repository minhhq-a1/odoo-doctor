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


@dataclass(frozen=True)
class SurfaceConfig:
    min_confidence: str | None = None
    categories: list[str] = field(default_factory=list)


@dataclass
class OdooDoctorConfig:
    """Parsed configuration from odoo-doctor.toml + CLI overrides."""

    odoo_version: str | None = None
    addons_paths: list[str] = field(default_factory=lambda: ["."])
    target_modules: list[str] = field(default_factory=list)
    odoo_source_path: str = ""
    min_score: int = 0
    capabilities: list[str] = field(default_factory=list)
    enable_plugins: bool = False

    # 'oca' is reserved: the OCA pre-commit adapter is not implemented yet, so
    # the key is accepted (tolerated-but-inert) but never instantiates an adapter.
    adapters: dict[str, bool] = field(
        default_factory=lambda: {"ruff": True, "pylint_odoo": True, "oca": False}
    )
    explicit_adapters: set[str] = field(default_factory=set)

    severity_overrides: dict[str, str] = field(default_factory=dict)
    ignore_rules: list[str] = field(default_factory=list)
    ignore_files: list[str] = field(default_factory=list)
    ignore_modules: list[str] = field(default_factory=list)
    category_weights: dict[str, float] = field(default_factory=dict)
    surfaces: dict[str, SurfaceConfig] = field(default_factory=dict)


def load_config(directory: Path) -> OdooDoctorConfig:
    """Load config by walking up from *directory*, merging parent configs.

    Closer configs override parent values. Walk stops at filesystem root or
    after 20 levels to avoid infinite loops on symlink cycles.
    """
    chain = _find_config_chain(directory)
    if not chain:
        return OdooDoctorConfig()

    # Merge from outermost (parent) to innermost (child) so child wins
    merged_raw: dict = {}
    for config_path in chain:
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
        _deep_merge(merged_raw, raw)

    return _build_config(merged_raw)


def _find_config_chain(directory: Path) -> list[Path]:
    """Walk up from directory collecting odoo-doctor.toml files. Returns outermost first."""
    chain: list[Path] = []
    current = directory.resolve()
    seen: set[str] = set()
    for _ in range(20):
        key = str(current)
        if key in seen:
            break
        seen.add(key)
        candidate = current / "odoo-doctor.toml"
        if candidate.is_file():
            chain.append(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent
    chain.reverse()
    return chain


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base. Dict values are merged recursively; others are replaced."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


def _build_config(raw: dict) -> OdooDoctorConfig:
    """Build OdooDoctorConfig from a merged raw TOML dict."""
    main = raw.get("odoo-doctor", {})
    adapters_raw = raw.get("adapters", {})
    severity_raw = raw.get("severity", {})
    ignore_raw = raw.get("ignore", {})
    weights_raw = raw.get("category_weights", {})
    surfaces_raw = raw.get("surfaces", {})
    plugins_raw = raw.get("plugins", {})

    defaults = OdooDoctorConfig()
    adapters = dict(defaults.adapters)
    for key, val in adapters_raw.items():
        adapters[key] = bool(val)

    surfaces = {
        "pr_comment": SurfaceConfig(),
        "ci_failure": SurfaceConfig(min_confidence="high"),
    }
    for surface_name, surface_data in surfaces_raw.items():
        if not isinstance(surface_data, dict):
            continue
        base = surfaces.get(surface_name, SurfaceConfig())
        surfaces[surface_name] = SurfaceConfig(
            min_confidence=surface_data.get("min_confidence", base.min_confidence),
            categories=surface_data.get("categories", base.categories),
        )

    return OdooDoctorConfig(
        odoo_version=main.get("odoo_version"),
        addons_paths=main.get("addons_paths", defaults.addons_paths),
        target_modules=main.get("target_modules", defaults.target_modules),
        odoo_source_path=main.get("odoo_source_path", defaults.odoo_source_path),
        min_score=main.get("min_score", defaults.min_score),
        capabilities=main.get("capabilities", defaults.capabilities),
        adapters=adapters,
        explicit_adapters=set(adapters_raw.keys()),
        severity_overrides=dict(severity_raw),
        ignore_rules=ignore_raw.get("rules", []),
        ignore_files=ignore_raw.get("files", []),
        ignore_modules=ignore_raw.get("modules", []),
        category_weights=dict(weights_raw),
        surfaces=surfaces,
        enable_plugins=bool(plugins_raw.get("enabled", False)),
    )
