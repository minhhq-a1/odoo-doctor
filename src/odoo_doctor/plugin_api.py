# src/odoo_doctor/plugin_api.py
"""Public, versioned API for third-party rule plugins (GA since v0.5.0).

Plugins should import only from this module; everything else in ``odoo_doctor``
is internal and may change in any release. Names exported here follow semantic
versioning of ``PLUGIN_API_VERSION``: additions keep the version, breaking
changes bump it, and the loader refuses plugins declaring a different version.

A plugin module may declare the API version it was written against::

    ODOO_DOCTOR_PLUGIN_API = 1

See docs/custom-rules.md.
"""

from __future__ import annotations

from odoo_doctor.core.diagnostics import CATEGORIES, TIER_IMPACT, Diagnostic
from odoo_doctor.core.source import read_source
from odoo_doctor.graph.module_context import ModuleContext
from odoo_doctor.rules._ast_helpers import node_is_orm, receiver_is_orm
from odoo_doctor.rules.registry import (
    CONFIDENCES,
    SEVERITIES,
    rule,
)

PLUGIN_API_VERSION = 1

TIERS = tuple(TIER_IMPACT)

__all__ = [
    "CATEGORIES",
    "CONFIDENCES",
    "Diagnostic",
    "ModuleContext",
    "PLUGIN_API_VERSION",
    "SEVERITIES",
    "TIERS",
    "node_is_orm",
    "read_source",
    "receiver_is_orm",
    "rule",
]
