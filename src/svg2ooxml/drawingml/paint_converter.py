"""Color and paint conversion helpers for raster rendering."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from svg2ooxml.common.dash_patterns import normalize_dash_array
from svg2ooxml.common.gradient_units import normalize_gradient_units
from svg2ooxml.common.math_utils import (
    coerce_float,
    coerce_positive_float,
    finite_float,
)
from svg2ooxml.common.skia_helpers import tile_mode as _skia_tile_mode

try:  # pragma: no cover - skia optional during transition
    import skia  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade without skia
    skia = None

_UNSUPPORTED_SOURCE_STYLE = object()


def _float_or(value: Any, default: float) -> float:
    return coerce_float(value, default)


def _is_number(value: object) -> bool:
    return finite_float(value) is not None


def _is_point_pair(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    return _is_number(value[0]) and _is_number(value[1])


def _coerce_positive(value: object | None, fallback: float | None = None) -> float:
    return coerce_positive_float(value, fallback if fallback is not None else 0.0)


def _transform_is_identity(transform: Any) -> bool:
    if transform is None:
        return True
    if not isinstance(transform, (list, tuple)) or len(transform) != 3:
        return False
    identity = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    try:
        for row_idx, row in enumerate(transform):
            if not isinstance(row, (list, tuple)) or len(row) != 3:
                return False
            for col_idx, value in enumerate(row):
                if abs(float(value) - identity[row_idx][col_idx]) >= 1e-9:
                    return False
    except (TypeError, ValueError):
        return False
    return True


def _color4f_from_paint_descriptor(
    paint_descriptor: Any, base_opacity: float
):
    if paint_descriptor is None:
        return None
    if not isinstance(paint_descriptor, dict):
        return _UNSUPPORTED_SOURCE_STYLE

    paint_type = str(paint_descriptor.get("type") or "").strip().lower()
    if not paint_type or paint_type == "none":
        return None
    if paint_type != "solid":
        return _UNSUPPORTED_SOURCE_STYLE

    token = str(paint_descriptor.get("rgb") or "").strip().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        return _UNSUPPORTED_SOURCE_STYLE
    try:
        value = int(token, 16)
    except ValueError:
        return _UNSUPPORTED_SOURCE_STYLE

    opacity = max(
        0.0,
        min(1.0, base_opacity * _float_or(paint_descriptor.get("opacity"), 1.0)),
    )
    return skia.Color4f(
        ((value >> 16) & 0xFF) / 255.0,
        ((value >> 8) & 0xFF) / 255.0,
        (value & 0xFF) / 255.0,
        opacity,
    )


def _fill_paint_from_descriptor(
    paint_descriptor: Any,
    base_opacity: float,
    bounds: tuple[float, float, float, float],
):
    if _is_empty_paint_descriptor(paint_descriptor):
        return None
    paint = skia.Paint(AntiAlias=True, Style=skia.Paint.kFill_Style)
    if _apply_paint_descriptor(paint, paint_descriptor, base_opacity, bounds):
        return paint
    return _UNSUPPORTED_SOURCE_STYLE


def _stroke_paint_from_descriptor(
    stroke_descriptor: Any,
    base_opacity: float,
    bounds: tuple[float, float, float, float] | None = None,
):
    if stroke_descriptor is None:
        return None
    if not isinstance(stroke_descriptor, dict):
        return _UNSUPPORTED_SOURCE_STYLE

    stroke_width = _float_or(stroke_descriptor.get("width"), 0.0)
    if stroke_width <= 0:
        return None

    paint = skia.Paint(
        AntiAlias=True,
        Style=skia.Paint.kStroke_Style,
        StrokeWidth=stroke_width,
    )
    paint_bounds = bounds or (0.0, 0.0, 1.0, 1.0)
    stroke_opacity = base_opacity * _float_or(stroke_descriptor.get("opacity"), 1.0)
    if _is_empty_paint_descriptor(stroke_descriptor.get("paint")):
        return None
    if not _apply_paint_descriptor(
        paint,
        stroke_descriptor.get("paint"),
        stroke_opacity,
        paint_bounds,
    ):
        return _UNSUPPORTED_SOURCE_STYLE

    cap = str(stroke_descriptor.get("cap") or "").strip().lower()
    if cap == "round":
        paint.setStrokeCap(skia.Paint.kRound_Cap)
    elif cap == "square":
        paint.setStrokeCap(skia.Paint.kSquare_Cap)
    else:
        paint.setStrokeCap(skia.Paint.kButt_Cap)

    join = str(stroke_descriptor.get("join") or "").strip().lower()
    if join == "round":
        paint.setStrokeJoin(skia.Paint.kRound_Join)
    elif join == "bevel":
        paint.setStrokeJoin(skia.Paint.kBevel_Join)
    else:
        paint.setStrokeJoin(skia.Paint.kMiter_Join)
    paint.setStrokeMiter(_float_or(stroke_descriptor.get("miter_limit"), 4.0))
    dash_array = stroke_descriptor.get("dash_array")
    if isinstance(dash_array, list) and dash_array:
        intervals = [max(0.1, value) for value in normalize_dash_array(dash_array)]
        if intervals:
            effect = skia.DashPathEffect.Make(
                intervals,
                _float_or(stroke_descriptor.get("dash_offset"), 0.0),
            )
            if effect:
                paint.setPathEffect(effect)
    return paint


def _apply_paint_descriptor(
    paint: Any,
    paint_descriptor: Any,
    base_opacity: float,
    bounds: tuple[float, float, float, float],
) -> bool:
    if paint_descriptor is None:
        return False
    color = _color4f_from_paint_descriptor(paint_descriptor, base_opacity)
    if color is not _UNSUPPORTED_SOURCE_STYLE:
        if color is None:
            return False
        paint.setColor4f(color)
        return True
    shader = _shader_from_paint_descriptor(paint_descriptor, base_opacity, bounds)
    if shader is None:
        return False
    paint.setShader(shader)
    return True


def _is_empty_paint_descriptor(paint_descriptor: Any) -> bool:
    if paint_descriptor is None:
        return True
    if not isinstance(paint_descriptor, dict):
        return False
    paint_type = str(paint_descriptor.get("type") or "").strip().lower()
    return not paint_type or paint_type == "none"


def _shader_from_paint_descriptor(
    paint_descriptor: Any,
    base_opacity: float,
    bounds: tuple[float, float, float, float],
):
    if not isinstance(paint_descriptor, dict):
        return None
    paint_type = str(paint_descriptor.get("type") or "").strip().lower()
    if paint_type == "lineargradient":
        return _linear_gradient_shader_from_descriptor(
            paint_descriptor,
            base_opacity,
            bounds,
        )
    if paint_type == "radialgradient":
        return _radial_gradient_shader_from_descriptor(
            paint_descriptor,
            base_opacity,
            bounds,
        )
    return None


def _linear_gradient_shader_from_descriptor(
    paint_descriptor: dict[str, Any],
    base_opacity: float,
    bounds: tuple[float, float, float, float],
):
    prepared = _prepare_gradient_stops(paint_descriptor.get("stops"), base_opacity)
    if prepared is None:
        return None
    positions, colors = prepared
    start = _point_pair_or_none(paint_descriptor.get("start"))
    end = _point_pair_or_none(paint_descriptor.get("end"))
    if start is None or end is None:
        return None
    x1, y1 = start
    x2, y2 = end
    if (
        normalize_gradient_units(paint_descriptor.get("gradient_units"))
        == "objectBoundingBox"
    ):
        bx, by, bw, bh = bounds
        x1 = bx + x1 * bw
        y1 = by + y1 * bh
        x2 = bx + x2 * bw
        y2 = by + y2 * bh
    if x1 == x2 and y1 == y2:
        return None
    matrix = _skia_matrix_or_none(paint_descriptor.get("transform"))
    tile_mode = _skia_tile_mode(skia, paint_descriptor.get("spread_method"))
    try:
        return skia.GradientShader.MakeLinear(
            [skia.Point(x1, y1), skia.Point(x2, y2)],
            colors,
            positions,
            tile_mode,
            0,
            matrix,
        )
    except TypeError:  # pragma: no cover - older skia signature
        return skia.GradientShader.MakeLinear(
            [skia.Point(x1, y1), skia.Point(x2, y2)],
            colors,
            positions,
            tile_mode,
        )


def _radial_gradient_shader_from_descriptor(
    paint_descriptor: dict[str, Any],
    base_opacity: float,
    bounds: tuple[float, float, float, float],
):
    prepared = _prepare_gradient_stops(paint_descriptor.get("stops"), base_opacity)
    if prepared is None:
        return None
    positions, colors = prepared
    center = _point_pair_or_none(paint_descriptor.get("center"))
    if center is None:
        return None
    cx, cy = center
    radius = _float_or(paint_descriptor.get("radius"), 0.0)
    focal_point = _point_pair_or_none(paint_descriptor.get("focal_point"))
    fx, fy = focal_point if focal_point is not None else (cx, cy)
    focal_radius = _float_or(paint_descriptor.get("focal_radius"), 0.0)
    if (
        normalize_gradient_units(paint_descriptor.get("gradient_units"))
        == "objectBoundingBox"
    ):
        bx, by, bw, bh = bounds
        cx = bx + cx * bw
        cy = by + cy * bh
        fx = bx + fx * bw
        fy = by + fy * bh
        scale = (bw + bh) * 0.5
        radius *= scale
        focal_radius *= scale
    if radius <= 0:
        return None
    matrix = _skia_matrix_or_none(paint_descriptor.get("transform"))
    tile_mode = _skia_tile_mode(skia, paint_descriptor.get("spread_method"))
    if fx != cx or fy != cy or focal_radius > 0:
        try:
            return skia.GradientShader.MakeTwoPointConical(
                skia.Point(fx, fy),
                focal_radius,
                skia.Point(cx, cy),
                radius,
                colors,
                positions,
                tile_mode,
                0,
                matrix,
            )
        except TypeError:  # pragma: no cover - older skia signature
            return skia.GradientShader.MakeTwoPointConical(
                skia.Point(fx, fy),
                focal_radius,
                skia.Point(cx, cy),
                radius,
                colors,
                positions,
                tile_mode,
            )
    try:
        return skia.GradientShader.MakeRadial(
            skia.Point(cx, cy),
            radius,
            colors,
            positions,
            tile_mode,
            0,
            matrix,
        )
    except TypeError:  # pragma: no cover - older skia signature
        return skia.GradientShader.MakeRadial(
            skia.Point(cx, cy),
            radius,
            colors,
            positions,
            tile_mode,
        )


def _prepare_gradient_stops(
    stops: Any,
    base_opacity: float,
) -> tuple[list[float], list[Any]] | None:
    if not isinstance(stops, Iterable) or isinstance(stops, (str, bytes)):
        return None
    positions: list[float] = []
    colors: list[Any] = []
    last_offset = 0.0
    for stop in stops:
        if not isinstance(stop, dict):
            continue
        offset = max(0.0, min(1.0, _float_or(stop.get("offset"), 0.0)))
        offset = max(offset, last_offset)
        last_offset = offset
        color = _color4f_from_hex(
            stop.get("rgb"),
            base_opacity * _float_or(stop.get("opacity"), 1.0),
        )
        if color is None:
            continue
        positions.append(offset)
        colors.append(color)
    if len(colors) < 2:
        return None
    return positions, colors


def _color4f_from_hex(value: Any, opacity: float):
    if not isinstance(value, str):
        return None
    token = value.strip().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        return None
    try:
        raw = int(token, 16)
    except ValueError:
        return None
    alpha = max(0.0, min(1.0, opacity))
    return skia.Color4f(
        ((raw >> 16) & 0xFF) / 255.0,
        ((raw >> 8) & 0xFF) / 255.0,
        (raw & 0xFF) / 255.0,
        alpha,
    )


def _point_pair_or_none(value: Any) -> tuple[float, float] | None:
    if not _is_point_pair(value):
        return None
    return float(value[0]), float(value[1])


def _skia_matrix_or_none(matrix: Any):
    if matrix is None:
        return None
    if not isinstance(matrix, (list, tuple)) or len(matrix) != 3:
        return None
    try:
        return skia.Matrix.MakeAll(
            float(matrix[0][0]),
            float(matrix[0][1]),
            float(matrix[0][2]),
            float(matrix[1][0]),
            float(matrix[1][1]),
            float(matrix[1][2]),
            0.0,
            0.0,
            1.0,
        )
    except (TypeError, ValueError, IndexError):
        return None
