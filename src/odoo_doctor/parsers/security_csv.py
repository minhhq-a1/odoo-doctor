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


def candidate_model_names(external_id: str):
    """Yield candidate dotted model names for a 'model_xxx' access-CSV external id.

    The external id replaces every '.' in the model name with '_', but model
    name segments may themselves contain '_', so the inverse is ambiguous
    (e.g. 'model_ir_actions_act_window' -> 'ir.actions.act_window'). We yield the
    all-dots candidate first (the common case), then every other partition, so a
    caller can accept the first that the resolver actually knows.
    """
    name = external_id
    if name.startswith("model_"):
        name = name[len("model_"):]
    parts = name.split("_")
    n = len(parts)

    # all-dots first (matches the majority of Odoo model names)
    yield ".".join(parts)
    if n <= 1:
        return

    sep_count = n - 1
    if sep_count > 8:
        return  # too ambiguous to enumerate; the naive candidate is all we offer

    # bit set => keep '_', bit unset => '.'; skip mask 0 (already yielded)
    for mask in range(1, 1 << sep_count):
        out = parts[0]
        for i in range(sep_count):
            out += ("_" if (mask >> i) & 1 else ".") + parts[i + 1]
        yield out
