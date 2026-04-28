"""Shared numeric and policy coercion helpers for filter planners."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from svg2ooxml.filters import planner_common as _common


class PlannerNumericMixin:
    """Compatibility wrappers around dependency-free planner helpers."""

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        return _common.coerce_float(value, default)

    @staticmethod
    def _finite_float(value: Any) -> float | None:
        return _common.finite_float(value)

    @staticmethod
    def _coerce_positive_float(value: Any, default: float) -> float:
        return _common.coerce_positive_float(value, default)

    @staticmethod
    def _is_finite_number(value: Any) -> bool:
        return _common.is_finite_number(value)

    @staticmethod
    def _is_positive_finite(value: Any) -> bool:
        return _common.is_positive_finite(value)

    @staticmethod
    def _numeric_region(region: Mapping[str, Any] | None) -> dict[str, float] | None:
        return _common.numeric_region(region)

    @staticmethod
    def _policy_flag(config: Mapping[str, Any], name: str) -> dict[str, bool]:
        return _common.policy_flag(config, name)

    @staticmethod
    def _policy_limit(
        config: Mapping[str, Any],
        name: str,
        cast_type: type = int,
    ) -> dict[str, Any]:
        return _common.policy_limit(config, name, cast_type)


__all__ = ["PlannerNumericMixin"]
