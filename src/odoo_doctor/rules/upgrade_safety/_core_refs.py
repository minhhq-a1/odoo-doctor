# src/odoo_doctor/rules/upgrade_safety/_core_refs.py
"""Shared lookup of the removed-core-* rules: was it in an older core and is it gone in ours?

``high``: the core module still exists in the target version, the thing is absent there, and
an older version had it. ``medium``: the whole module is gone from the target (it may have
moved to enterprise). Anything else is silent: a reference never seen in any core version
may be enterprise, OCA, runtime-created or a typo, and "not found" proves none of that.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from odoo_doctor.graph.core_index import CoreIndex, get_core_index, older_indexes

if TYPE_CHECKING:
    from odoo_doctor.graph.module_context import ModuleContext

_HINT_LIMIT = 3


@dataclass(frozen=True)
class Verdict:
    confidence: str  # "high" | "medium"
    target: str  # the version the module is scanned as
    seen_in: tuple[str, ...]  # older versions that still had it


def classify(
    ctx: ModuleContext,
    module: str,
    present: Callable[[CoreIndex], bool],
    *,
    target: CoreIndex | None = None,
    older: list[CoreIndex] | None = None,
) -> Verdict | None:
    """A :class:`Verdict` (``high``/``medium``) or None for a reference into core ``module``.

    ``present(index)`` says whether the referenced file or id exists in that index. ``target``
    and ``older`` default to the packaged indexes of the module's target version.
    """
    if ctx.resolver.is_scanned_module(module):
        return None
    if older is None:
        older = older_indexes(ctx.odoo_version)
    if target is None:
        target = get_core_index(ctx.odoo_version)
    if target is None or not older:
        return None
    seen = tuple(i.version for i in older if i.has_module(module) and present(i))
    if not seen:
        return None
    if not target.has_module(module):
        return Verdict("medium", target.version, seen)
    return None if present(target) else Verdict("high", target.version, seen)


def relocation_hint(target: CoreIndex | None, basename: str) -> str:
    """ " Possible new location: ..." for a removed file, when the basename is not ambiguous."""
    if target is None:
        return ""
    moved = target.static_by_basename(basename)
    if not moved or len(moved) > _HINT_LIMIT:
        return ""
    return " Same file name in this version: " + ", ".join(
        f"{m}/{rel}" for m, rel in moved
    )
