"""Filter planning helpers for resvg and descriptor fallbacks."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from typing import Any

from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_float_list
from svg2ooxml.filters.resvg_bridge import FilterPrimitiveDescriptor, ResolvedFilter, build_filter_node
from svg2ooxml.render.filters import FilterPlan, plan_filter
from svg2ooxml.render.rasterizer import Viewport

_VECTOR_HINT_TAGS = {
    "fecomponenttransfer",
    "fedisplacementmap",
    "feturbulence",
    "feconvolvematrix",
    "fecolormatrix",
    "fecomposite",
    "feblend",
    "femerge",
    "fetile",
    "fediffuselighting",
    "fespecularlighting",
}
_RASTER_HINT_TAGS = {
    "feimage",
}


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
                    "metadata": self.serialise_plan_extra(primitive_plan.extra)
                    if primitive_plan.extra
                    else None,
                }.items()
                if value is not None and value != []
            }
            for primitive_plan in plan.primitives
        ]

    def descriptor_is_neutral(self, descriptor: ResolvedFilter | None) -> bool:
        if descriptor is None or not descriptor.primitives:
            return False
        return all(self._primitive_is_neutral(primitive) for primitive in descriptor.primitives)

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
            region_height = self._parse_fraction(region.get("height"), 1.2) * base_height
        else:
            region_x = self._parse_user_length(
                region.get("x"),
                x - 0.1 * base_width,
                viewport_width,
            )
            region_y = self._parse_user_length(
                region.get("y"),
                y - 0.1 * base_height,
                viewport_height,
            )
            region_width = self._parse_user_length(
                region.get("width"),
                base_width * 1.2,
                viewport_width,
            )
            region_height = self._parse_user_length(
                region.get("height"),
                base_height * 1.2,
                viewport_height,
            )

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
        min_x, min_y, max_x, max_y = bounds
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        width_px = max(1, int(math.ceil(width)))
        height_px = max(1, int(math.ceil(height)))
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

    def policy_primitive_overrides(self, context: FilterContext) -> dict[str, dict[str, Any]]:
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
            if isinstance(max_pixels, (int, float)) and max_pixels > 0 and pixels > max_pixels:
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
                bounds = {
                    key: bbox_candidate[key]
                    for key in ("x", "y", "width", "height")
                    if key in bbox_candidate
                }

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
        tags = descriptor.get("primitive_tags")
        if not isinstance(tags, Iterable):
            return None
        lowered = {str(tag).strip().lower() for tag in tags if tag}
        if not lowered:
            return "vector" if strategy_hint in {"vector", "emf"} else None

        if any(tag in _RASTER_HINT_TAGS for tag in lowered):
            return "raster"
        if any(tag in _VECTOR_HINT_TAGS for tag in lowered):
            return "vector"

        if strategy_hint in {"vector", "emf"}:
            return "vector"
        if strategy_hint == "raster":
            return "raster"
        return None

    @staticmethod
    def serialize_descriptor(descriptor: ResolvedFilter) -> dict[str, Any]:
        return {
            "filter_id": descriptor.filter_id,
            "filter_units": descriptor.filter_units,
            "primitive_units": descriptor.primitive_units,
            "primitive_count": len(descriptor.primitives),
            "primitive_tags": [primitive.tag for primitive in descriptor.primitives],
            "filter_region": dict(descriptor.region or {}),
            "primitive_metadata": [dict(primitive.extras) for primitive in descriptor.primitives],
        }

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
        if value is None:
            return default
        token = str(value).strip()
        if not token:
            return default
        try:
            if token.endswith("%"):
                return float(token[:-1]) / 100.0
            return float(token)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_user_length(value: Any, default: float, viewport_length: float) -> float:
        if value is None:
            return default
        token = str(value).strip()
        if not token:
            return default
        try:
            if token.endswith("%"):
                return (float(token[:-1]) / 100.0) * viewport_length
            return float(token)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_identity_matrix(values: list[float]) -> bool:
        if len(values) != 20:
            return False
        identity = [
            1.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 1.0, 0.0,
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
            and isinstance(max_coeff, (int, float))
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
            if isinstance(max_distance, (int, float)):
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
            if isinstance(max_inputs, (int, float)):
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
                if isinstance(max_functions, (int, float)) and len(functions) > int(max_functions):
                    return {
                        "rule": "max_component_functions",
                        "limit": int(max_functions),
                        "observed": len(functions),
                    }
                max_table_values = policy_entry.get("max_component_table_values")
                if isinstance(max_table_values, (int, float)):
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

        if tag == "feconvolvematrix":
            max_kernel = policy_entry.get("max_convolve_kernel")
            if isinstance(max_kernel, (int, float)):
                kernel = metadata.get("kernel")
                count = len(kernel) if isinstance(kernel, list) else 0
                if count > int(max_kernel):
                    return {
                        "rule": "max_convolve_kernel",
                        "limit": int(max_kernel),
                        "observed": count,
                    }
            max_order = policy_entry.get("max_convolve_order")
            if isinstance(max_order, (int, float)):
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
        return any(primitive.tag.lower() == "feturbulence" for primitive in plan.primitives)

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if math.isnan(number) or math.isinf(number):
            return default
        return number

    @staticmethod
    def _numeric_region(region: Mapping[str, Any] | None) -> dict[str, float] | None:
        if not isinstance(region, Mapping):
            return None
        numeric: dict[str, float] = {}
        for key in ("x", "y", "width", "height"):
            value = region.get(key)
            if isinstance(value, (int, float)):
                numeric[key] = float(value)
                continue
            if isinstance(value, str):
                try:
                    numeric[key] = float(value)
                except ValueError:
                    continue
        return numeric or None

    @staticmethod
    def _policy_flag(config: Mapping[str, Any], name: str) -> dict[str, bool]:
        if name not in config:
            return {}
        raw = config.get(name)
        if isinstance(raw, str):
            token = raw.strip().lower()
            if token in {"true", "1", "yes", "on"}:
                return {name: True}
            if token in {"false", "0", "no", "off"}:
                return {name: False}
        elif isinstance(raw, bool):
            return {name: raw}
        elif raw is not None:
            return {name: bool(raw)}
        return {}

    @staticmethod
    def _policy_limit(
        config: Mapping[str, Any],
        name: str,
        cast_type: type = int,
    ) -> dict[str, Any]:
        if name not in config:
            return {}
        try:
            value = cast_type(config.get(name))
        except (TypeError, ValueError):
            return {}
        if isinstance(value, (int, float)) and value < 0:
            return {}
        return {name: value}


__all__ = ["FilterPlanner"]
