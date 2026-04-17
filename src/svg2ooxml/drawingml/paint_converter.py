"""Color and paint conversion helpers for raster rendering."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - skia optional during transition
    import skia  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade without skia
    skia = None

_UNSUPPORTED_SOURCE_STYLE = object()


def _float_or(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_number(value: object) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _is_point_pair(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    return _is_number(value[0]) and _is_number(value[1])


def _coerce_positive(value: object | None, fallback: float | None = None) -> float:
    if _is_number(value):
        number = float(value)  # type: ignore[arg-type]
        if number > 0:
            return number
    if fallback is not None:
        return float(fallback)
    return 0.0


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


def _stroke_paint_from_descriptor(stroke_descriptor: Any, base_opacity: float):
    if stroke_descriptor is None:
        return None
    if not isinstance(stroke_descriptor, dict):
        return _UNSUPPORTED_SOURCE_STYLE

    stroke_width = _float_or(stroke_descriptor.get("width"), 0.0)
    if stroke_width <= 0:
        return None
    dash_array = stroke_descriptor.get("dash_array")
    if isinstance(dash_array, list) and dash_array:
        return _UNSUPPORTED_SOURCE_STYLE

    stroke_color = _color4f_from_paint_descriptor(
        stroke_descriptor.get("paint"),
        base_opacity * _float_or(stroke_descriptor.get("opacity"), 1.0),
    )
    if stroke_color is _UNSUPPORTED_SOURCE_STYLE:
        return _UNSUPPORTED_SOURCE_STYLE
    if stroke_color is None:
        return None

    paint = skia.Paint(
        AntiAlias=True,
        Style=skia.Paint.kStroke_Style,
        StrokeWidth=stroke_width,
        Color4f=stroke_color,
    )
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
    return paint
