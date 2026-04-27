"""Rendering fallbacks (EMF / bitmap) for the IR converter."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Sequence
from io import BytesIO
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.color.adapters import hex_to_rgb_tuple
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.bridges import EMFPathAdapter, PathStyle
from svg2ooxml.ir.geometry import Point, Rect, SegmentType
from svg2ooxml.ir.paint import SolidPaint
from svg2ooxml.ir.scene import ClipRef, Image, MaskInstance, MaskRef
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.common.units import ConversionContext
    from svg2ooxml.core.styling.style_extractor import StyleResult
    from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace

_PATH_ADAPTER = EMFPathAdapter()


def render_emf_fallback(
    *,
    element: etree._Element,
    style: StyleResult,
    segments: Sequence[SegmentType],
    coord_space: CoordinateSpace,
    clip_ref: ClipRef | None,
    mask_ref: MaskRef | None,
    mask_instance: MaskInstance | None,
    metadata: dict[str, object],
    unit_converter: UnitConverter,
    conversion_context: ConversionContext | None,
    adapter: EMFPathAdapter | None = None,
) -> Image | None:
    transformed = coord_space.apply_segments(segments)
    fill_paint = style.fill if isinstance(style.fill, SolidPaint) else None
    path_style = PathStyle(
        fill=fill_paint,
        fill_rule=_resolve_fill_rule(element, style.metadata),
        stroke=style.stroke,
    )

    effective_dpi = conversion_context.dpi if conversion_context is not None else unit_converter.dpi
    emf_adapter = adapter or _PATH_ADAPTER
    result = emf_adapter.render(
        segments=transformed,
        style=path_style,
        unit_converter=unit_converter,
        conversion_context=conversion_context,
        dpi=effective_dpi,
    )
    if result is None:
        return None

    emf_meta = metadata.setdefault("emf_asset", {})
    emf_meta.setdefault("width_emu", result.width_emu)
    emf_meta.setdefault("height_emu", result.height_emu)
    if fill_paint is not None:
        emf_meta.setdefault("fill_color", fill_paint.rgb)
        emf_meta.setdefault("fill_rule", path_style.fill_rule)
    if style.stroke and style.stroke.paint and isinstance(style.stroke.paint, SolidPaint):
        emf_meta.setdefault("stroke_color", style.stroke.paint.rgb)
        emf_meta.setdefault("stroke_width", style.stroke.width)
        emf_meta.setdefault("stroke_cap", style.stroke.cap.value)
        emf_meta.setdefault("stroke_join", style.stroke.join.value)

    policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
    policy_meta["render_mode"] = FALLBACK_EMF

    return Image(
        origin=Point(result.origin[0], result.origin[1]),
        size=Rect(0.0, 0.0, result.size[0], result.size[1]),
        data=result.emf_bytes,
        format=FALLBACK_EMF,
        clip=clip_ref,
        mask=mask_ref,
        mask_instance=mask_instance,
        opacity=style.opacity,
        metadata=metadata,
    )


def _resolve_fill_rule(element: etree._Element, style_metadata: dict[str, object] | None) -> str:
    if isinstance(style_metadata, dict):
        meta_value = style_metadata.get("fill_rule")
        if isinstance(meta_value, str) and meta_value.strip():
            return _normalise_fill_rule(meta_value)
        paint_meta = style_metadata.get("policy")
        if isinstance(paint_meta, dict):
            fill_meta = paint_meta.get("paint")
            if isinstance(fill_meta, dict):
                fill_rule_meta = fill_meta.get("fill_rule")
                if isinstance(fill_rule_meta, str) and fill_rule_meta.strip():
                    return _normalise_fill_rule(fill_rule_meta)

    attr = element.get("fill-rule")
    if attr:
        return _normalise_fill_rule(attr)

    inline = element.get("style")
    value = parse_style_declarations(inline)[0].get("fill-rule")
    if value and value.strip():
        return _normalise_fill_rule(value)

    return "nonzero"


def _normalise_fill_rule(rule: str) -> str:
    token = rule.strip().lower()
    if token in {"evenodd", "even-odd"}:
        return "evenodd"
    return "nonzero"


def render_bitmap_fallback(
    *,
    element: etree._Element,
    style: StyleResult,
    segments: Sequence[SegmentType],
    coord_space: CoordinateSpace,
    clip_ref: ClipRef | None,
    mask_ref: MaskRef | None,
    mask_instance: MaskInstance | None,
    metadata: dict[str, object],
    flatten_segments: Callable[[Iterable[SegmentType]], list[tuple[float, float]]],
    hex_to_rgba: Callable[[str, float], tuple[int, int, int, int] | None],
    max_area_px: int | None,
    max_side_px: int | None,
    logger: logging.Logger | None,
) -> Image | None:
    try:
        from PIL import Image as PILImage
        from PIL import ImageDraw
    except ImportError:  # pragma: no cover - optional dependency
        return None

    transformed = coord_space.apply_segments(segments)
    points = flatten_segments(transformed)
    if len(points) < 2:
        return None

    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(1.0, max_x - min_x)
    height = max(1.0, max_y - min_y)
    width_px = max(1, int(round(width)))
    height_px = max(1, int(round(height)))
    area_px = width_px * height_px

    geometry_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
    geometry_meta.setdefault("bitmap_target_size", f"{width_px}x{height_px}")

    if max_side_px is not None and (width_px > max_side_px or height_px > max_side_px):
        geometry_meta["bitmap_suppressed"] = "max_side"
        geometry_meta["bitmap_limit_side"] = max_side_px
        if logger:
            logger.debug(
                "Suppressed bitmap fallback for %s: size %sx%s exceeds side limit %s",
                element.tag,
                width_px,
                height_px,
                max_side_px,
            )
        return None

    if max_area_px is not None and area_px > max_area_px:
        geometry_meta["bitmap_suppressed"] = "max_area"
        geometry_meta["bitmap_limit_area"] = max_area_px
        if logger:
            logger.debug(
                "Suppressed bitmap fallback for %s: area %s exceeds limit %s",
                element.tag,
                area_px,
                max_area_px,
            )
        return None

    scale = 2
    canvas_width = max(1, int(math.ceil(width * scale)))
    canvas_height = max(1, int(math.ceil(height * scale)))

    image = PILImage.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")

    shape_opacity = style.opacity
    fill_color = None
    if style.fill and isinstance(style.fill, SolidPaint):
        fill_color = hex_to_rgba(style.fill.rgb, style.fill.opacity * shape_opacity)

    stroke_color = None
    stroke_width = 1
    if style.stroke and isinstance(style.stroke.paint, SolidPaint):
        stroke_color = hex_to_rgba(
            style.stroke.paint.rgb,
            style.stroke.paint.opacity * style.stroke.opacity * shape_opacity,
        )
        stroke_width = max(1, int(round(style.stroke.width * scale)))

    # translate points so the minimum corner sits at (0, 0)
    offset_points = [(x - min_x, y - min_y) for x, y in points]
    scaled_points = [(int(round(x * scale)), int(round(y * scale))) for x, y in offset_points]

    if fill_color is not None:
        draw.polygon(scaled_points, fill=fill_color)
    if stroke_color is not None:
        draw.line(scaled_points + [scaled_points[0]], fill=stroke_color, width=stroke_width)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    png_data = buffer.getvalue()

    policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
    policy_meta["render_mode"] = FALLBACK_BITMAP

    return Image(
        origin=Point(min_x, min_y),
        size=Rect(0.0, 0.0, width, height),
        data=png_data,
        format="png",
        clip=clip_ref,
        mask=mask_ref,
        mask_instance=mask_instance,
        opacity=style.opacity,
        metadata=metadata,
    )


def _hex_rgba_to_tuple(hex_color: str, opacity: float) -> tuple[int, int, int, int] | None:
    try:
        r, g, b = hex_to_rgb_tuple(hex_color.strip())
    except ValueError:
        return None
    a = max(0, min(255, int(round(opacity * 255))))
    return r, g, b, a


def hex_to_rgba(hex_color: str, opacity: float) -> tuple[int, int, int, int] | None:
    """Public helper retained for callers depending on old module API."""

    return _hex_rgba_to_tuple(hex_color, opacity)


__all__ = ["render_emf_fallback", "render_bitmap_fallback", "hex_to_rgba"]
