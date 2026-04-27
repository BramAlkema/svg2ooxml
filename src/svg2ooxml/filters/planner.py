"""Filter planning helpers for resvg and descriptor fallbacks."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from typing import Any

from svg2ooxml.common.units.lengths import (
    parse_number_or_percent,
    resolve_user_length_px,
)
from svg2ooxml.filters import planner_common as _common
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.resvg_bridge import (
    FilterPrimitiveDescriptor,
    ResolvedFilter,
    build_filter_node,
)
from svg2ooxml.filters.utils import parse_float_list
from svg2ooxml.render.filters import FilterPlan, plan_filter
from svg2ooxml.render.rasterizer import Viewport

_MAX_RESVG_VIEWPORT_DIMENSION_PX = 4096
_MAX_RESVG_VIEWPORT_PIXELS = _MAX_RESVG_VIEWPORT_DIMENSION_PX**2


class FilterPlanner:
    """Plan resvg filter execution and descriptor fallbacks."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def build_resvg_plan(
        self,
        descriptor: ResolvedFilter,
        *,
        options: Mapping[str, Any] | None = None,
    ) -> FilterPlan | None:
        try:
            filter_node = build_filter_node(descriptor)
        except Exception:  # pragma: no cover - defensive
            self._logger.debug("Failed to construct filter node", exc_info=True)
            return None
        return plan_filter(filter_node, options=options)

    def plan_summary(self, plan: FilterPlan) -> list[dict[str, Any]]:
        return [
            {
                key: value
                for key, value in {
                    "tag": primitive_plan.tag,
                    "inputs": list(primitive_plan.inputs),
                    "result": primitive_plan.result_name,
                    "metadata": (
                        self.serialise_plan_extra(primitive_plan.extra)
                        if primitive_plan.extra
                        else None
                    ),
                }.items()
                if value is not None and value != []
            }
            for primitive_plan in plan.primitives
        ]

    def descriptor_is_neutral(self, descriptor: ResolvedFilter | None) -> bool:
        if descriptor is None or not descriptor.primitives:
            return False
        return all(
            self._primitive_is_neutral(primitive) for primitive in descriptor.primitives
        )

    def resvg_bounds(
        self,
        options: Mapping[str, Any] | None,
        descriptor: ResolvedFilter,
    ) -> tuple[float, float, float, float]:
        bbox: Mapping[str, Any] = {}
        if isinstance(options, Mapping):
            candidate = options.get("ir_bbox")
            if isinstance(candidate, Mapping):
                bbox = candidate

        x = self._coerce_float(bbox.get("x"), 0.0)
        y = self._coerce_float(bbox.get("y"), 0.0)
        width = self._coerce_float(bbox.get("width"), 0.0)
        height = self._coerce_float(bbox.get("height"), 0.0)

        base_width = width if width > 0 else 128.0
        base_height = height if height > 0 else 96.0
        region = descriptor.region or {}
        units = (descriptor.filter_units or "objectBoundingBox").strip()

        viewport_width = self._coerce_float(
            options.get("viewport_width") if isinstance(options, Mapping) else None,
            base_width,
        )
        viewport_height = self._coerce_float(
            options.get("viewport_height") if isinstance(options, Mapping) else None,
            base_height,
        )

        if units == "objectBoundingBox":
            region_x = x + self._parse_fraction(region.get("x"), -0.1) * base_width
            region_y = y + self._parse_fraction(region.get("y"), -0.1) * base_height
            region_width = self._parse_fraction(region.get("width"), 1.2) * base_width
            region_height = (
                self._parse_fraction(region.get("height"), 1.2) * base_height
            )
        else:
            region_x = self._parse_user_length(
                region.get("x"),
                x - 0.1 * base_width,
                viewport_width,
                axis="x",
            )
            region_y = self._parse_user_length(
                region.get("y"),
                y - 0.1 * base_height,
                viewport_height,
                axis="y",
            )
            region_width = self._parse_user_length(
                region.get("width"),
                base_width * 1.2,
                viewport_width,
                axis="x",
            )
            region_height = self._parse_user_length(
                region.get("height"),
                base_height * 1.2,
                viewport_height,
                axis="y",
            )

        region_x = self._coerce_float(region_x, x - 0.1 * base_width)
        region_y = self._coerce_float(region_y, y - 0.1 * base_height)
        region_width = self._coerce_positive_float(region_width, base_width * 1.2)
        region_height = self._coerce_positive_float(region_height, base_height * 1.2)
        region_width = max(region_width, 1.0)
        region_height = max(region_height, 1.0)
        return (
            region_x,
            region_y,
            region_x + region_width,
            region_y + region_height,
        )

    def _primitive_is_neutral(self, primitive: FilterPrimitiveDescriptor) -> bool:
        tag = (primitive.tag or "").strip().lower()
        attrs = primitive.attributes or {}
        if tag == "fegaussianblur":
            raw = self._attribute(attrs, "stdDeviation")
            std_values = parse_float_list(raw)
            if not std_values:
                return True
            return all(abs(value) <= 1e-6 for value in std_values[:2])
        if tag == "feoffset":
            dx = self._parse_float(self._attribute(attrs, "dx")) or 0.0
            dy = self._parse_float(self._attribute(attrs, "dy")) or 0.0
            return abs(dx) <= 1e-6 and abs(dy) <= 1e-6
        if tag == "fecolormatrix":
            matrix_type = (self._attribute(attrs, "type") or "matrix").strip().lower()
            if matrix_type != "matrix":
                return False
            values = parse_float_list(self._attribute(attrs, "values"))
            if not values:
                return True
            return self._is_identity_matrix(values)
        return False

    @staticmethod
    def resvg_viewport(bounds: tuple[float, float, float, float]) -> Viewport:
        if len(bounds) != 4:
            raise ValueError("resvg bounds must contain four coordinates")
        min_x, min_y, max_x, max_y = bounds
        if not all(FilterPlanner._is_finite_number(value) for value in bounds):
            raise ValueError("resvg bounds must be finite")
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        if not math.isfinite(width) or not math.isfinite(height):
            raise ValueError("resvg viewport dimensions must be finite")
        width_px = max(1, int(math.ceil(width)))
        height_px = max(1, int(math.ceil(height)))
        if (
            width_px > _MAX_RESVG_VIEWPORT_DIMENSION_PX
            or height_px > _MAX_RESVG_VIEWPORT_DIMENSION_PX
            or width_px * height_px > _MAX_RESVG_VIEWPORT_PIXELS
        ):
            raise ValueError("resvg viewport exceeds raster safety limits")
        scale_x = width_px / width
        scale_y = height_px / height
        return Viewport(
            width=width_px,
            height=height_px,
            min_x=min_x,
            min_y=min_y,
            scale_x=scale_x,
            scale_y=scale_y,
        )

    def policy_primitive_overrides(
        self, context: FilterContext
    ) -> dict[str, dict[str, Any]]:
        options = context.options if isinstance(context.options, dict) else {}
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
            entry.update(self._policy_limit(config, "max_pixels"))
            entry.update(self._policy_limit(config, "max_arithmetic_coeff", float))
            entry.update(self._policy_limit(config, "max_offset_distance", float))
            entry.update(self._policy_limit(config, "max_merge_inputs", int))
            entry.update(self._policy_limit(config, "max_component_functions", int))
            entry.update(self._policy_limit(config, "max_component_table_values", int))
            entry.update(self._policy_limit(config, "max_convolve_kernel", int))
            entry.update(self._policy_limit(config, "max_convolve_order", int))
            if entry:
                overrides[key] = entry
        return overrides

    def resvg_policy_block(
        self,
        plan: FilterPlan,
        viewport: Viewport,
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

    def descriptor_payload(
        self,
        context: FilterContext,
        descriptor: ResolvedFilter | None,
    ) -> tuple[dict[str, Any] | None, dict[str, float | Any] | None]:
        payload: dict[str, Any] | None = None
        bounds: dict[str, float | Any] | None = None

        options = context.options if isinstance(context.options, dict) else {}
        if isinstance(options, dict):
            candidate = options.get("resvg_descriptor")
            if isinstance(candidate, dict):
                payload = dict(candidate)
            bbox_candidate = options.get("ir_bbox")
            if isinstance(bbox_candidate, dict):
                finite_bounds: dict[str, float] = {}
                for key in ("x", "y", "width", "height"):
                    if key not in bbox_candidate:
                        continue
                    value = self._finite_float(bbox_candidate[key])
                    if value is not None:
                        finite_bounds[key] = value
                bounds = finite_bounds

        if payload is None and descriptor is not None:
            payload = self.serialize_descriptor(descriptor)

        if bounds is None and payload is not None:
            numeric_bounds = self._numeric_region(payload.get("filter_region"))
            if numeric_bounds:
                bounds = numeric_bounds

        return payload, bounds

    def infer_descriptor_strategy(
        self,
        descriptor: Mapping[str, Any],
        *,
        strategy_hint: str,
    ) -> str | None:
        return _common.infer_descriptor_strategy(
            descriptor,
            strategy_hint=strategy_hint,
        )

    @staticmethod
    def serialize_descriptor(descriptor: ResolvedFilter) -> dict[str, Any]:
        return _common.serialize_descriptor(descriptor)

    @staticmethod
    def _attribute(attributes: Mapping[str, Any], name: str) -> str | None:
        if name in attributes:
            return str(attributes[name])
        lowered = name.lower()
        for key, value in attributes.items():
            if str(key).lower() == lowered:
                return str(value)
        return None

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_fraction(value: Any, default: float) -> float:
        parsed = parse_number_or_percent(value, default)
        return FilterPlanner._coerce_float(parsed, default)

    @staticmethod
    def _parse_user_length(
        value: Any,
        default: float,
        viewport_length: float,
        *,
        axis: str = "x",
    ) -> float:
        safe_default = FilterPlanner._coerce_float(default, 0.0)
        safe_viewport_length = FilterPlanner._coerce_positive_float(
            viewport_length,
            1.0,
        )
        resolved = resolve_user_length_px(
            value,
            safe_default,
            safe_viewport_length,
            axis=axis,
        )
        return FilterPlanner._coerce_float(resolved, safe_default)

    @staticmethod
    def _is_identity_matrix(values: list[float]) -> bool:
        if len(values) != 20:
            return False
        identity = [
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
        ]
        tol = 1e-6
        return all(abs(a - b) <= tol for a, b in zip(values, identity, strict=True))

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
            and FilterPlanner._is_finite_number(max_coeff)
        ):
            limit = abs(float(max_coeff))
            for key in ("k1", "k2", "k3", "k4"):
                coeff = metadata.get(key)
                if isinstance(coeff, (int, float)) and abs(coeff) > limit:
                    return {
                        "rule": "max_arithmetic_coeff",
                        "limit": limit,
                        "coefficient": key,
                        "observed": float(coeff),
                    }

        if tag == "feoffset":
            max_distance = policy_entry.get("max_offset_distance")
            if FilterPlanner._is_finite_number(max_distance):
                dx = metadata.get("dx")
                dy = metadata.get("dy")
                dx_val = float(dx) if isinstance(dx, (int, float)) else 0.0
                dy_val = float(dy) if isinstance(dy, (int, float)) else 0.0
                distance = math.hypot(dx_val, dy_val)
                if distance > float(max_distance):
                    return {
                        "rule": "max_offset_distance",
                        "limit": float(max_distance),
                        "observed": distance,
                        "dx": dx_val,
                        "dy": dy_val,
                    }

        if tag == "femerge":
            max_inputs = policy_entry.get("max_merge_inputs")
            if FilterPlanner._is_positive_finite(max_inputs):
                inputs = metadata.get("inputs")
                count = len(inputs) if isinstance(inputs, (list, tuple)) else 0
                if count > int(max_inputs):
                    return {
                        "rule": "max_merge_inputs",
                        "limit": int(max_inputs),
                        "observed": count,
                    }

        if tag == "fecomponenttransfer":
            functions = metadata.get("functions")
            if isinstance(functions, list):
                max_functions = policy_entry.get("max_component_functions")
                if FilterPlanner._is_positive_finite(max_functions) and len(
                    functions
                ) > int(max_functions):
                    return {
                        "rule": "max_component_functions",
                        "limit": int(max_functions),
                        "observed": len(functions),
                    }
                max_table_values = policy_entry.get("max_component_table_values")
                if FilterPlanner._is_positive_finite(max_table_values):
                    limit = int(max_table_values)
                    for func in functions:
                        params = (
                            func.get("params") if isinstance(func, Mapping) else None
                        )
                        values = (
                            params.get("values")
                            if isinstance(params, Mapping)
                            else None
                        )
                        if isinstance(values, list) and len(values) > limit:
                            return {
                                "rule": "max_component_table_values",
                                "limit": limit,
                                "observed": len(values),
                                "channel": func.get("channel"),
                            }

        if tag == "feconvolvematrix":
            max_kernel = policy_entry.get("max_convolve_kernel")
            if FilterPlanner._is_positive_finite(max_kernel):
                kernel = metadata.get("kernel")
                count = len(kernel) if isinstance(kernel, list) else 0
                if count > int(max_kernel):
                    return {
                        "rule": "max_convolve_kernel",
                        "limit": int(max_kernel),
                        "observed": count,
                    }
            max_order = policy_entry.get("max_convolve_order")
            if FilterPlanner._is_positive_finite(max_order):
                order = metadata.get("order")
                if isinstance(order, (list, tuple)) and order:
                    span = 1
                    numeric = True
                    for axis in order:
                        if isinstance(axis, (int, float)):
                            span *= int(axis)
                        else:
                            numeric = False
                            break
                    if numeric and span > int(max_order):
                        return {
                            "rule": "max_convolve_order",
                            "limit": int(max_order),
                            "observed": span,
                        }

        return None

    @staticmethod
    def promotion_policy_allows(
        tag: str,
        result: FilterResult,
        policy_entry: Mapping[str, Any],
    ) -> bool:
        violation = FilterPlanner.promotion_policy_violation(tag, result, policy_entry)
        return violation is None

    @staticmethod
    def serialise_plan_extra(extra: Mapping[str, Any]) -> dict[str, Any]:
        def _coerce(value: Any) -> Any:
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            if isinstance(value, Mapping):
                return {k: _coerce(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [_coerce(v) for v in value]
            return str(value)

        return {key: _coerce(val) for key, val in extra.items()}

    @staticmethod
    def plan_has_turbulence(plan: FilterPlan) -> bool:
        return any(
            primitive.tag.lower() == "feturbulence" for primitive in plan.primitives
        )

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


__all__ = ["FilterPlanner"]
