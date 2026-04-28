"""Filter policy planning and promotion limit checks."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from svg2ooxml.filters.base import FilterResult
from svg2ooxml.filters.planner_numeric import PlannerNumericMixin

_POLICY_LIMITS: tuple[tuple[str, type], ...] = (
    ("max_pixels", int),
    ("max_arithmetic_coeff", float),
    ("max_offset_distance", float),
    ("max_merge_inputs", int),
    ("max_component_functions", int),
    ("max_component_table_values", int),
    ("max_convolve_kernel", int),
    ("max_convolve_order", int),
)


class PolicyPlanningMixin(PlannerNumericMixin):
    """Read filter policy options and enforce render promotion limits."""

    def policy_primitive_overrides(self, context: Any) -> dict[str, dict[str, Any]]:
        options = (
            context.options
            if isinstance(getattr(context, "options", None), dict)
            else {}
        )
        policy = options.get("policy")
        if not isinstance(policy, Mapping):
            return {}
        primitives = policy.get("primitives")
        if not isinstance(primitives, Mapping):
            return {}
        overrides: dict[str, dict[str, Any]] = {}
        for name, config in primitives.items():
            key = str(name).strip().lower()
            if not key or not isinstance(config, Mapping):
                continue
            entry: dict[str, Any] = {}
            entry.update(self._policy_flag(config, "allow_resvg"))
            entry.update(self._policy_flag(config, "allow_promotion"))
            for limit_name, cast_type in _POLICY_LIMITS:
                entry.update(self._policy_limit(config, limit_name, cast_type))
            if entry:
                overrides[key] = entry
        return overrides

    def resvg_policy_block(
        self,
        plan: Any,
        viewport: Any,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> str | None:
        if not overrides:
            return None
        pixels = viewport.width * viewport.height
        for primitive_plan in plan.primitives:
            tag = primitive_plan.tag.lower()
            policy_entry = overrides.get(tag)
            if not policy_entry:
                continue
            if policy_entry.get("allow_resvg") is False:
                return f"{tag}:disabled"
            max_pixels = policy_entry.get("max_pixels")
            if self._is_positive_finite(max_pixels) and pixels > float(max_pixels):
                return f"{tag}:max_pixels_exceeded"
        return None

    @staticmethod
    def promotion_policy_violation(
        tag: str,
        result: FilterResult,
        policy_entry: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(policy_entry, Mapping):
            return None
        metadata = result.metadata if isinstance(result.metadata, dict) else {}

        max_coeff = policy_entry.get("max_arithmetic_coeff")
        if (
            tag == "fecomposite"
            and metadata.get("operator") == "arithmetic"
            and PolicyPlanningMixin._is_finite_number(max_coeff)
        ):
            violation = _arithmetic_coeff_violation(metadata, float(max_coeff))
            if violation:
                return violation

        if tag == "feoffset":
            violation = _offset_distance_violation(metadata, policy_entry)
            if violation:
                return violation

        if tag == "femerge":
            violation = _merge_input_violation(metadata, policy_entry)
            if violation:
                return violation

        if tag == "fecomponenttransfer":
            violation = _component_transfer_violation(metadata, policy_entry)
            if violation:
                return violation

        if tag == "feconvolvematrix":
            violation = _convolve_violation(metadata, policy_entry)
            if violation:
                return violation

        return None

    @staticmethod
    def promotion_policy_allows(
        tag: str,
        result: FilterResult,
        policy_entry: Mapping[str, Any],
    ) -> bool:
        violation = PolicyPlanningMixin.promotion_policy_violation(
            tag, result, policy_entry
        )
        return violation is None


def _arithmetic_coeff_violation(
    metadata: Mapping[str, Any], max_coeff: float
) -> dict[str, Any] | None:
    limit = abs(max_coeff)
    for key in ("k1", "k2", "k3", "k4"):
        coeff = metadata.get(key)
        if isinstance(coeff, (int, float)) and abs(coeff) > limit:
            return {
                "rule": "max_arithmetic_coeff",
                "limit": limit,
                "coefficient": key,
                "observed": float(coeff),
            }
    return None


def _offset_distance_violation(
    metadata: Mapping[str, Any], policy_entry: Mapping[str, Any]
) -> dict[str, Any] | None:
    max_distance = policy_entry.get("max_offset_distance")
    if not PolicyPlanningMixin._is_finite_number(max_distance):
        return None
    dx = metadata.get("dx")
    dy = metadata.get("dy")
    dx_val = float(dx) if isinstance(dx, (int, float)) else 0.0
    dy_val = float(dy) if isinstance(dy, (int, float)) else 0.0
    distance = math.hypot(dx_val, dy_val)
    if distance <= float(max_distance):
        return None
    return {
        "rule": "max_offset_distance",
        "limit": float(max_distance),
        "observed": distance,
        "dx": dx_val,
        "dy": dy_val,
    }


def _merge_input_violation(
    metadata: Mapping[str, Any], policy_entry: Mapping[str, Any]
) -> dict[str, Any] | None:
    max_inputs = policy_entry.get("max_merge_inputs")
    if not PolicyPlanningMixin._is_positive_finite(max_inputs):
        return None
    inputs = metadata.get("inputs")
    count = len(inputs) if isinstance(inputs, (list, tuple)) else 0
    if count <= int(max_inputs):
        return None
    return {
        "rule": "max_merge_inputs",
        "limit": int(max_inputs),
        "observed": count,
    }


def _component_transfer_violation(
    metadata: Mapping[str, Any], policy_entry: Mapping[str, Any]
) -> dict[str, Any] | None:
    functions = metadata.get("functions")
    if not isinstance(functions, list):
        return None
    max_functions = policy_entry.get("max_component_functions")
    if PolicyPlanningMixin._is_positive_finite(max_functions) and len(functions) > int(
        max_functions
    ):
        return {
            "rule": "max_component_functions",
            "limit": int(max_functions),
            "observed": len(functions),
        }
    max_table_values = policy_entry.get("max_component_table_values")
    if not PolicyPlanningMixin._is_positive_finite(max_table_values):
        return None
    limit = int(max_table_values)
    for func in functions:
        params = func.get("params") if isinstance(func, Mapping) else None
        values = params.get("values") if isinstance(params, Mapping) else None
        if isinstance(values, list) and len(values) > limit:
            return {
                "rule": "max_component_table_values",
                "limit": limit,
                "observed": len(values),
                "channel": func.get("channel"),
            }
    return None


def _convolve_violation(
    metadata: Mapping[str, Any], policy_entry: Mapping[str, Any]
) -> dict[str, Any] | None:
    max_kernel = policy_entry.get("max_convolve_kernel")
    if PolicyPlanningMixin._is_positive_finite(max_kernel):
        kernel = metadata.get("kernel")
        count = len(kernel) if isinstance(kernel, list) else 0
        if count > int(max_kernel):
            return {
                "rule": "max_convolve_kernel",
                "limit": int(max_kernel),
                "observed": count,
            }
    max_order = policy_entry.get("max_convolve_order")
    if not PolicyPlanningMixin._is_positive_finite(max_order):
        return None
    order = metadata.get("order")
    if not isinstance(order, (list, tuple)) or not order:
        return None
    span = 1
    for axis in order:
        if not isinstance(axis, (int, float)):
            return None
        span *= int(axis)
    if span <= int(max_order):
        return None
    return {
        "rule": "max_convolve_order",
        "limit": int(max_order),
        "observed": span,
    }


__all__ = ["PolicyPlanningMixin"]
