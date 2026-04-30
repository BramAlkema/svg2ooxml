"""Text positioning, baseline, anchor, and bounding-box helpers.

Extracted from ``core.ir.text_converter`` — pure move, no behavior changes.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.common.geometry.algorithms import CurveTextPositioner
from svg2ooxml.common.units.lengths import (
    resolve_length_list_px,
    resolve_length_px,
)
from svg2ooxml.core.ir.font_metrics import (
    estimate_run_width as _estimate_run_width,
)
from svg2ooxml.core.ir.font_metrics import (
    resolve_font_metrics as _resolve_font_metrics,
)
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.text import Run, TextAnchor

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.ir.context import IRConverterContext
    from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace

# ---------------------------------------------------------------
# Coordinate-space text scale
# ---------------------------------------------------------------


def text_scale_for_coord_space(
    coord_space: CoordinateSpace,
    *,
    tolerance: float = 1e-6,
) -> float:
    matrix = getattr(coord_space, "current", None)
    if matrix is None:
        return 1.0

    scale_x = math.hypot(float(matrix.a), float(matrix.b))
    scale_y = math.hypot(float(matrix.c), float(matrix.d))

    if scale_x <= tolerance and scale_y <= tolerance:
        return 1.0
    if scale_x <= tolerance:
        return max(scale_y, 1.0)
    if scale_y <= tolerance:
        return max(scale_x, 1.0)

    dot_product = abs(
        float(matrix.a) * float(matrix.c) + float(matrix.b) * float(matrix.d)
    )
    max_scale = max(scale_x, scale_y)
    if (
        dot_product <= tolerance * max(1.0, max_scale * max_scale)
        and abs(scale_x - scale_y) <= max_scale * 0.01
    ):
        return (scale_x + scale_y) / 2.0

    determinant = abs(
        float(matrix.a) * float(matrix.d) - float(matrix.b) * float(matrix.c)
    )
    if determinant > tolerance:
        return math.sqrt(determinant)

    return (scale_x + scale_y) / 2.0


# ---------------------------------------------------------------
# Resvg origin / anchor / direction
# ---------------------------------------------------------------


def parse_number_list(value: str | None) -> list[float]:
    if not value:
        return []
    return parse_numeric_list(value)


def resvg_text_origin(
    resvg_node: Any,
    coord_space: CoordinateSpace,
) -> tuple[float, float]:
    spans = getattr(resvg_node, "spans", None)
    if spans:
        first = spans[0]
        x = getattr(first, "x", 0.0)
        y = getattr(first, "y", 0.0)
        return coord_space.apply_point(float(x), float(y))

    attrs = getattr(resvg_node, "attributes", {}) or {}
    x_vals = parse_number_list(attrs.get("x"))
    y_vals = parse_number_list(attrs.get("y"))
    dx_vals = parse_number_list(attrs.get("dx"))
    dy_vals = parse_number_list(attrs.get("dy"))
    base_x = x_vals[0] if x_vals else 0.0
    base_y = y_vals[0] if y_vals else 0.0
    base_x += dx_vals[0] if dx_vals else 0.0
    base_y += dy_vals[0] if dy_vals else 0.0
    return coord_space.apply_point(base_x, base_y)


def resvg_text_anchor(resvg_node: Any) -> TextAnchor:
    attrs = getattr(resvg_node, "attributes", {}) or {}
    anchor_token = attrs.get("text-anchor") or attrs.get("textAnchor") or "start"
    return {
        "middle": TextAnchor.MIDDLE,
        "end": TextAnchor.END,
    }.get(str(anchor_token).strip().lower(), TextAnchor.START)


def resvg_text_direction(resvg_node: Any) -> str | None:
    attrs = getattr(resvg_node, "attributes", {}) or {}
    direction = attrs.get("direction")
    if isinstance(direction, str):
        token = direction.strip().lower()
        if token in ("rtl", "ltr"):
            return token
    return None


# ---------------------------------------------------------------
# Text-length / unit resolution
# ---------------------------------------------------------------


def resolve_text_length(
    value: str | None,
    *,
    axis: str,
    font_size_pt: float,
    context: IRConverterContext | None = None,
) -> float:
    if value in (None, "", "0"):
        return 0.0
    if context is None:
        return resolve_length_px(value, None, axis=axis)
    unit_converter = getattr(context, "unit_converter", None)
    conversion_context = getattr(context, "conversion_context", None)
    if unit_converter is None or conversion_context is None:
        return resolve_length_px(value, None, axis=axis)
    font_px = font_size_pt * (96.0 / 72.0)
    derived = conversion_context.derive(font_size=font_px)
    return resolve_length_px(
        value,
        derived,
        axis=axis,
        unit_converter=unit_converter,
    )


def parse_text_length_list(
    value: str | None,
    font_size_pt: float,
    *,
    axis: str,
    context: IRConverterContext | None = None,
) -> list[float]:
    if not value:
        return []
    if context is None:
        return resolve_length_list_px(value, None, axis=axis)
    unit_converter = getattr(context, "unit_converter", None)
    conversion_context = getattr(context, "conversion_context", None)
    if unit_converter is None or conversion_context is None:
        return resolve_length_list_px(value, None, axis=axis)
    font_px = font_size_pt * (96.0 / 72.0)
    derived = conversion_context.derive(font_size=font_px)
    return resolve_length_list_px(
        value,
        derived,
        axis=axis,
        unit_converter=unit_converter,
    )


# ---------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------


def normalize_text_segment(text: str | None, *, preserve_space: bool = False) -> str:
    if not text:
        return ""
    token = text.replace("\r\n", "\n").replace("\r", "\n")
    if preserve_space:
        if token.strip() == "":
            return "\n" if "\n" in token else " "
        return token
    if "\n" in token:
        collapsed = re.sub(r"\s+", " ", token)
        return collapsed.strip()
    if token.strip() == "":
        return " "
    leading_space = token[:1].isspace()
    trailing_space = token[-1:].isspace()
    core = re.sub(r"\s+", " ", token.strip())
    if leading_space:
        core = f" {core}"
    if trailing_space:
        core = f"{core} "
    return core


def normalize_positioned_text(text: str | None, preserve_space: bool) -> str:
    return normalize_text_segment(text, preserve_space=preserve_space)


# ---------------------------------------------------------------
# Bounding-box estimation
# ---------------------------------------------------------------


def estimate_text_bbox(
    runs: list[Run],
    origin_x: float,
    origin_y: float,
    *,
    font_service: Any | None = None,
) -> Rect:
    """Estimate text bounding box from runs.

    Note: font_size_pt is in points. Need to convert to pixels (96 DPI standard).
    Proper text box height requires:
    - Font size in pixels
    - Line height (typically 1.2-1.5x font size)
    - Font ascent/descent

    Current approach uses conservative estimates to ensure text fits.
    When a FontService is available, per-glyph advances are used to
    improve width estimation.
    """
    if not runs:
        return Rect(origin_x, origin_y, 0.0, 0.0)

    max_font_pt = max(run.font_size_pt for run in runs)

    # Convert points to pixels (96 DPI standard: 1pt = 96/72 pixels = 1.333px)
    max_font_px = max_font_pt * (96.0 / 72.0)

    max_width = 0.0
    current_width = 0.0
    line_count = 1
    max_ascent_px = 0.0
    max_descent_px = 0.0
    max_gap_px = 0.0
    for run in runs:
        text = (run.text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not text:
            continue
        parts = text.split("\n")
        for index, part in enumerate(parts):
            if index > 0:
                max_width = max(max_width, current_width)
                current_width = 0.0
                line_count += 1
            if part:
                current_width += _estimate_run_width(part, run, font_service)
        metrics = _resolve_font_metrics(font_service, run)
        if metrics is not None:
            font_px = run.font_size_pt * (96.0 / 72.0)
            scale = font_px / metrics.units_per_em
            ascender_px = max(0.0, metrics.ascender * scale)
            descender_px = max(0.0, -metrics.descender * scale)
            gap_px = max(0.0, metrics.line_gap * scale)
            max_ascent_px = max(max_ascent_px, ascender_px)
            max_descent_px = max(max_descent_px, descender_px)
            max_gap_px = max(max_gap_px, gap_px)
    max_width = max(max_width, current_width)

    metrics_found = max_ascent_px > 0.0 or max_descent_px > 0.0
    if metrics_found:
        raw_line_height = max_ascent_px + max_descent_px + max_gap_px
        min_line_height = max_font_px * 1.2
        line_height = max(raw_line_height, min_line_height)
        baseline_span = max_ascent_px + max_descent_px
        if baseline_span > 0.0:
            baseline_ratio = max_ascent_px / baseline_span
            y_offset = line_height * baseline_ratio
        else:
            y_offset = max_font_px * 0.8
    else:
        # Line height = font size + leading (extra space between lines)
        # Use 1.5x to avoid clipping when metrics are unavailable.
        line_height = max_font_px * 1.5
        y_offset = max_font_px * 0.8

    height = line_height * max(1, line_count)

    return Rect(origin_x, origin_y - y_offset, max_width, height)


def apply_text_anchor(
    bbox: Rect,
    anchor: TextAnchor,
    *,
    direction: str | None = None,
) -> Rect:
    resolved_anchor = _inline_anchor_for_direction(anchor, direction=direction)
    if resolved_anchor == TextAnchor.MIDDLE:
        return Rect(bbox.x - bbox.width / 2.0, bbox.y, bbox.width, bbox.height)
    if resolved_anchor == TextAnchor.END:
        return Rect(bbox.x - bbox.width, bbox.y, bbox.width, bbox.height)
    return bbox


def _inline_anchor_for_direction(
    anchor: TextAnchor,
    *,
    direction: str | None,
) -> TextAnchor:
    if direction != "rtl":
        return anchor
    if anchor == TextAnchor.START:
        return TextAnchor.END
    if anchor == TextAnchor.END:
        return TextAnchor.START
    return anchor


# ---------------------------------------------------------------
# Text-path helpers
# ---------------------------------------------------------------


def attach_text_path_metadata(
    element: Any,
    metadata: dict[str, Any],
    *,
    resvg_node: Any | None = None,
    context: IRConverterContext | None = None,
    text_path_positioner: CurveTextPositioner | None = None,
) -> None:
    if metadata.get("text_path_id"):
        return

    if context is None:
        return

    for node in element.iter():
        local = context.local_name(getattr(node, "tag", "")).lower()
        if local != "textpath":
            continue
        href = node.get("{http://www.w3.org/1999/xlink}href") or node.get("href")
        record_text_path_reference(
            href,
            metadata,
            context=context,
            text_path_positioner=text_path_positioner,
        )
        if metadata.get("text_path_id"):
            return

    attrs = getattr(resvg_node, "attributes", {}) or {}
    href = attrs.get("textPath")
    if isinstance(href, str):
        record_text_path_reference(
            href,
            metadata,
            context=context,
            text_path_positioner=text_path_positioner,
        )


def record_text_path_reference(
    href: str | None,
    metadata: dict[str, Any],
    *,
    context: IRConverterContext | None = None,
    text_path_positioner: CurveTextPositioner | None = None,
) -> None:
    if context is None:
        return
    path_id = context.normalize_href_reference(href)
    if not path_id:
        return
    metadata.setdefault("text_path_id", path_id)
    sampled = sample_text_path(
        path_id,
        context=context,
        text_path_positioner=text_path_positioner,
    )
    if sampled is not None:
        metadata["text_path_data"] = sampled["path_data"]
        metadata["text_path_points"] = sampled["points"]


def sample_text_path(
    path_id: str,
    *,
    context: IRConverterContext | None = None,
    text_path_positioner: CurveTextPositioner | None = None,
) -> dict[str, object] | None:
    if context is None or text_path_positioner is None:
        return None
    element = context.element_index.get(path_id)
    if element is None:
        return None
    path_data = element.get("d")
    if not path_data:
        return None
    try:
        points = text_path_positioner.sample_path_for_text(path_data, num_samples=96)
        return {"points": points, "path_data": path_data}
    except Exception:  # pragma: no cover - defensive fallback
        return None
