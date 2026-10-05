# src/odoo_doctor/rules/registry.py
"""Rule registry with @rule decorator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from odoo_doctor.core.diagnostics import CATEGORIES, TIER_IMPACT

SEVERITIES = ("error", "warning", "info")
CONFIDENCES = ("high", "medium", "low")


@dataclass
class RuleMeta:
    name: str
    category: str
    tier: str  # "P0" | "P1" | "P2" | "P3"
    severity: str  # "error" | "warning" | "info"
    default_confidence: str  # "high" | "medium" | "low"
    needs_context: bool  # True: func(ctx) | False: func(file, module, version)
    min_version: str | None  # minimum Odoo version, or None for all
    requires_capabilities: set[str] = field(default_factory=set)
    excludes_capabilities: set[str] = field(default_factory=set)
    fixable: bool = False


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: list[tuple[RuleMeta, Callable]] = []
        self._by_name: dict[str, tuple[RuleMeta, Callable]] = {}

    def register(self, meta: RuleMeta, func: Callable) -> None:
        if meta.name in self._by_name:
            raise ValueError(f"rule '{meta.name}' is already registered")
        self._rules.append((meta, func))
        self._by_name[meta.name] = (meta, func)

    def unregister(self, name: str) -> None:
        """Remove a rule (used to roll back a plugin that failed to load)."""
        self._by_name.pop(name, None)
        self._rules = [(m, f) for m, f in self._rules if m.name != name]

    def get_rules(
        self, needs_context: bool | None = None
    ) -> list[tuple[RuleMeta, Callable]]:
        if needs_context is None:
            return list(self._rules)
        return [(m, f) for m, f in self._rules if m.needs_context is needs_context]

    def get(self, name: str) -> tuple[RuleMeta, Callable] | None:
        return self._by_name.get(name)

    def active_rules_map(self) -> dict[str, str | None]:
        """Return {rule_name: min_version} for all registered rules."""
        return {m.name: m.min_version for m, _ in self._rules}

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def __len__(self) -> int:
        return len(self._rules)


# Module-level default registry
default_registry = RuleRegistry()


def rule(
    name: str,
    category: str,
    tier: str,
    severity: str,
    default_confidence: str,
    needs_context: bool,
    min_version: str | None = None,
    requires_capabilities: set[str] | list[str] | None = None,
    excludes_capabilities: set[str] | list[str] | None = None,
    fixable: bool = False,
    registry: RuleRegistry | None = None,
) -> Callable[[Callable], Callable]:
    """Decorator that registers a rule function in the registry.

    Raises ValueError for an unknown category/tier/severity/confidence or a
    duplicate rule name, so a malformed plugin fails loudly at load time.
    """
    _validate_choice("category", category, CATEGORIES)
    _validate_choice("tier", tier, tuple(TIER_IMPACT))
    _validate_choice("severity", severity, SEVERITIES)
    _validate_choice("default_confidence", default_confidence, CONFIDENCES)

    def decorator(func: Callable) -> Callable:
        meta = RuleMeta(
            name=name,
            category=category,
            tier=tier,
            severity=severity,
            default_confidence=default_confidence,
            needs_context=needs_context,
            min_version=min_version,
            requires_capabilities=set(requires_capabilities or []),
            excludes_capabilities=set(excludes_capabilities or []),
            fixable=fixable,
        )
        target = registry if registry is not None else default_registry
        target.register(meta, func)
        return func

    return decorator


def _validate_choice(field_name: str, value: str, allowed) -> None:
    if value not in allowed:
        raise ValueError(
            f"invalid {field_name} {value!r}; expected one of {', '.join(allowed)}"
        )
