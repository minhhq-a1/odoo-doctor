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
