# src/odoo_doctor/rules/registry.py
"""Rule registry with @rule decorator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


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


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: list[tuple[RuleMeta, Callable]] = []
        self._by_name: dict[str, tuple[RuleMeta, Callable]] = {}

    def register(self, meta: RuleMeta, func: Callable) -> None:
        self._rules.append((meta, func))
        self._by_name[meta.name] = (meta, func)

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
    registry: RuleRegistry | None = None,
) -> Callable[[Callable], Callable]:
    """Decorator that registers a rule function in the registry."""

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
        )
        target = registry if registry is not None else default_registry
        target.register(meta, func)
        return func

    return decorator
