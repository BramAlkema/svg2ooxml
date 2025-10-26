"""Policy engine orchestrating conversion decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol

from .rules import DEFAULT_POLICY, Policy, load_policy
from .targets import PolicyTarget, TargetRegistry


class PolicyProvider(Protocol):
    """Interface for objects that provide policy entries for specific domains."""

    def supports(self, target: PolicyTarget) -> bool:  # pragma: no cover - tiny shim
        ...

    def evaluate(self, target: PolicyTarget, options: Mapping[str, Any]) -> Mapping[str, Any]:  # pragma: no cover
        ...


@dataclass(slots=True)
class PolicyContext:
    """Holds evaluated policy options for quick lookup."""

    selections: dict[str, Mapping[str, Any]] = field(default_factory=dict)

    def get(self, target: str, default: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
        return self.selections.get(target, default)


class PolicyEngine:
    """Evaluate policies for registered targets using pluggable providers."""

    def __init__(
        self,
        *,
        providers: Iterable[PolicyProvider] | None = None,
        default_policy: Policy | None = None,
        target_registry: TargetRegistry | None = None,
    ) -> None:
        self._providers = list(providers or [])
        self._policy = default_policy or DEFAULT_POLICY
        self._targets = target_registry or TargetRegistry.default()

    def register_provider(self, provider: PolicyProvider) -> None:
        self._providers.append(provider)

    def set_policy(self, policy_name: str) -> None:
        self._policy = load_policy(policy_name)

    def evaluate(self, *targets: PolicyTarget) -> PolicyContext:
        if not targets:
            targets = tuple(self._targets.iter_targets())

        selections: dict[str, Mapping[str, Any]] = {}
        options = self._policy.options
        for target in targets:
            result = self._evaluate_target(target, options)
            if result is not None:
                selections[target.name] = result
        return PolicyContext(selections=selections)

    def _evaluate_target(
        self,
        target: PolicyTarget,
        options: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        for provider in self._providers:
            if provider.supports(target):
                return provider.evaluate(target, options)
        return None


__all__ = ["PolicyContext", "PolicyEngine", "PolicyProvider"]
