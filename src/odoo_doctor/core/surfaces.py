from __future__ import annotations

from odoo_doctor.core.diagnostics import Diagnostic
from odoo_doctor.core.config import SurfaceConfig


def filter_for_surface(
    diagnostics: list[Diagnostic], surface_cfg: SurfaceConfig
) -> list[Diagnostic]:
    """Filter diagnostics according to surface configuration.

    Drops diagnostics below `min_confidence` and outside `categories` (if non-empty).
    Confidence ranks: high > medium > low
    """
    conf_ranks = {"low": 1, "medium": 2, "high": 3}

    min_conf_rank = (
        conf_ranks.get(surface_cfg.min_confidence, 0)
        if surface_cfg.min_confidence
        else 0
    )

    filtered = []
    for d in diagnostics:
        # Check confidence
        if conf_ranks.get(d.confidence, 0) < min_conf_rank:
            continue

        # Check categories
        if surface_cfg.categories and d.category not in surface_cfg.categories:
            continue

        filtered.append(d)

    return filtered
