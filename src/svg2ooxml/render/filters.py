"""Filter planning/execution scaffolding."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FilterPlan:
    primitives: list
    bounding_box: tuple[float, float, float, float]


def plan_filter(node) -> FilterPlan | None:
    """Return a filter execution plan for the supplied node."""

    raise NotImplementedError("Filter planning will be ported from pyportresvg.")


def apply_filter(surface, plan: FilterPlan):
    """Apply the computed filter plan to the surface."""

    raise NotImplementedError("Filter application will be implemented later.")


__all__ = ["FilterPlan", "plan_filter", "apply_filter"]

