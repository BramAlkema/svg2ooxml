"""Policy compatibility helpers for :mod:`svg2ooxml.services.filter_service`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.filters.base import FilterResult
from svg2ooxml.filters.planner_policy import PolicyPlanningMixin


class FilterPolicyRuntimeMixin:
    """Expose promotion policy delegates on ``FilterService``."""

    @staticmethod
    def _promotion_policy_violation(
        tag: str,
        result: FilterResult,
        policy_entry: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        return PolicyPlanningMixin.promotion_policy_violation(tag, result, policy_entry)

    @staticmethod
    def _promotion_policy_allows(
        tag: str,
        result: FilterResult,
        policy_entry: Mapping[str, Any],
    ) -> bool:
        return PolicyPlanningMixin.promotion_policy_allows(tag, result, policy_entry)


__all__ = ["FilterPolicyRuntimeMixin"]
