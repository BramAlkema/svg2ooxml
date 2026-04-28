"""resvg filter bounds and viewport planning helpers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from svg2ooxml.common.units.lengths import (
    parse_number_or_percent,
    resolve_user_length_px,
)
from svg2ooxml.filters.planner_numeric import PlannerNumericMixin
from svg2ooxml.render.rasterizer import Viewport

_MAX_RESVG_VIEWPORT_DIMENSION_PX = 4096
_MAX_RESVG_VIEWPORT_PIXELS = _MAX_RESVG_VIEWPORT_DIMENSION_PX**2


class ResvgGeometryMixin(PlannerNumericMixin):
    """Resolve resvg filter regions into finite raster viewports."""

    def resvg_bounds(
        self,
        options: Mapping[str, Any] | None,
        descriptor: Any,
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
        region = getattr(descriptor, "region", None) or {}
        units = (
            getattr(descriptor, "filter_units", None) or "objectBoundingBox"
        ).strip()

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

    @staticmethod
    def resvg_viewport(bounds: tuple[float, float, float, float]) -> Viewport:
        if len(bounds) != 4:
            raise ValueError("resvg bounds must contain four coordinates")
        min_x, min_y, max_x, max_y = bounds
        if not all(ResvgGeometryMixin._is_finite_number(value) for value in bounds):
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

    @staticmethod
    def _parse_fraction(value: Any, default: float) -> float:
        parsed = parse_number_or_percent(value, default)
        return ResvgGeometryMixin._coerce_float(parsed, default)

    @staticmethod
    def _parse_user_length(
        value: Any,
        default: float,
        viewport_length: float,
        *,
        axis: str = "x",
    ) -> float:
        safe_default = ResvgGeometryMixin._coerce_float(default, 0.0)
        safe_viewport_length = ResvgGeometryMixin._coerce_positive_float(
            viewport_length,
            1.0,
        )
        resolved = resolve_user_length_px(
            value,
            safe_default,
            safe_viewport_length,
            axis=axis,
        )
        return ResvgGeometryMixin._coerce_float(resolved, safe_default)


__all__ = [
    "ResvgGeometryMixin",
    "_MAX_RESVG_VIEWPORT_DIMENSION_PX",
    "_MAX_RESVG_VIEWPORT_PIXELS",
]
