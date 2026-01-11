"""Policy target definitions and registry utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Iterator


@dataclass(frozen=True)
class PolicyTarget:
    """Represents a configurable policy domain."""

    name: str
    description: str | None = None


class TargetRegistry:
    """Registry that keeps track of known policy targets."""

    def __init__(self) -> None:
        self._targets: Dict[str, PolicyTarget] = {}

    def register(self, target: PolicyTarget) -> None:
        self._targets[target.name] = target

    def iter_targets(self) -> Iterator[PolicyTarget]:
        return iter(self._targets.values())

    def get(self, name: str) -> PolicyTarget | None:
        return self._targets.get(name)

    @classmethod
    def default(cls) -> "TargetRegistry":
        registry = cls()
        registry.register(PolicyTarget("image", "Image optimisation and conversion"))
        registry.register(PolicyTarget("text", "Text shaping and font embedding"))
        registry.register(PolicyTarget("geometry", "Geometry simplification policies"))
        registry.register(PolicyTarget("marker", "Marker decoration policies"))
        registry.register(PolicyTarget("gradient", "Gradient rendering policies"))
        registry.register(PolicyTarget("clip", "Clip path evaluation policies"))
        registry.register(PolicyTarget("group", "Group flattening policies"))
        registry.register(PolicyTarget("animation", "Animation sampling and fallback policies"))
        registry.register(PolicyTarget("filter", "Filter rendering policies"))
        registry.register(PolicyTarget("mask", "Mask rendering and fallback policies"))
        registry.register(PolicyTarget("multipage", "Multi-page detection policies"))
        return registry


__all__ = ["PolicyTarget", "TargetRegistry"]
