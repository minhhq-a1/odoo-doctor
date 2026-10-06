# src/odoo_doctor/rules/xml/_view_refs.py
"""Shared check for the view rules: does a ref belong to the view's own model?"""

from __future__ import annotations

from odoo_doctor.graph.resolver import ResolveResult, SymbolResolver


def sits_in_subview(resolver: SymbolResolver, model: str, anchor: str | None) -> bool:
    """A ref inserted next to a node that is not a field of *model* is not *model*'s.

    An inherited view's ``<xpath expr="//field[@name='X']">`` locates ``X`` in the parent
    arch. If ``X`` is not a field of the view's model, the node it found is a column or
    field of an inline subview, so what the xpath inserts belongs to that subview's model.
    """
    if anchor is None:
        return False
    return resolver.resolve_field(model, anchor).status != ResolveResult.FOUND
