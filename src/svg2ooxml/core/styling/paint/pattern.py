"""Pattern paint resolution — extracted from StyleExtractor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.color import parse_color
from svg2ooxml.color.utils import rgb_object_to_hex
from svg2ooxml.common.geometry import parse_transform_list
from svg2ooxml.core.styling.paint import (
    ensure_paint_policy,
    maybe_set_geometry_fallback,
)
from svg2ooxml.core.styling.style_helpers import (
    clean_color,
    matrix2d_to_numpy,
    matrix_tuple_is_identity,
)
from svg2ooxml.drawingml.bridges.resvg_paint_bridge import PatternDescriptor
from svg2ooxml.elements.pattern_processor import PatternComplexity, PatternType
from svg2ooxml.elements.patterns._helpers import (
    local_name,
    parse_float_attr,
    pattern_opacity,
    style_map,
)
from svg2ooxml.ir.paint import PatternPaint, SolidPaint
from svg2ooxml.policy.constants import FALLBACK_EMF
from svg2ooxml.services import ConversionServices

if TYPE_CHECKING:  # pragma: no cover - hint only
    from svg2ooxml.core.tracing import ConversionTracer


def get_pattern_processor(services: ConversionServices):
    processor = services.resolve("pattern_processor")
    if processor is None and services.pattern_service is not None:
        processor = getattr(services.pattern_service, "processor", None)
    return processor


def build_pattern_paint(
    *,
    pattern_id: str,
    services: ConversionServices,
    context: Any | None = None,
) -> PatternPaint | SolidPaint | None:
    pattern_service = services.pattern_service
    if pattern_service is None:
        return None
    pattern_descriptor = pattern_service.get(pattern_id)
    if pattern_descriptor is None:
        return None
    pattern_element = pattern_service.as_element(pattern_descriptor)
    solid = _solid_tile_pattern_paint(pattern_element, pattern_descriptor)
    if solid is not None:
        return solid

    transform_attr = pattern_element.get("patternTransform")
    transform_matrix = None
    if transform_attr:
        try:
            transform_matrix = parse_transform_list(transform_attr)
        except Exception:
            transform_matrix = None

    preset = None
    foreground = None
    background = None
    background_opacity = 1.0
    tile_image = None
    tile_width_px = None
    tile_height_px = None
    processor = get_pattern_processor(services)
    if processor is not None:
        try:
            analysis = processor.analyze_pattern_element(pattern_element, context)
            preset = analysis.preset_candidate
            palette_values: list[str] = []
            if isinstance(analysis.color_statistics, dict):
                palette_values = analysis.color_statistics.get("palette") or []
            elif hasattr(analysis, "colors_used"):
                palette_values = analysis.colors_used or []
            cleaned: list[str] = []
            for value in palette_values:
                colour = clean_color(value)
                if colour:
                    cleaned.append(colour)
            if cleaned:
                foreground = cleaned[0]
            if len(cleaned) > 1:
                background = cleaned[1]
            elif len(cleaned) == 1:
                background_opacity = 0.0
            tile_payload = processor.build_tile_payload(
                pattern_element,
                analysis=analysis,
            )
            if tile_payload is not None:
                tile_image, tile_width_px, tile_height_px = tile_payload
        except Exception:  # pragma: no cover - defensive
            pass

    if foreground is None:
        foreground = "000000"
    if background is None:
        background = "FFFFFF"
    preset = preset or "pct5"

    return PatternPaint(
        pattern_id=pattern_id,
        transform=matrix2d_to_numpy(transform_matrix),
        preset=preset,
        foreground=foreground,
        background=background,
        background_opacity=background_opacity,
        tile_image=tile_image,
        tile_width_px=tile_width_px,
        tile_height_px=tile_height_px,
    )


def _solid_tile_pattern_paint(
    pattern_element: etree._Element,
    descriptor: PatternDescriptor,
) -> SolidPaint | None:
    children = [
        child
        for child in pattern_element
        if isinstance(getattr(child, "tag", None), str)
    ]
    if len(children) != 1:
        return None

    child = children[0]
    if local_name(child.tag) != "rect":
        return None
    if _has_solid_tile_modifier(child):
        return None
    if _visible_stroke(child):
        return None

    tile_width = float(descriptor.width or 0.0)
    tile_height = float(descriptor.height or 0.0)
    if tile_width <= 0.0 or tile_height <= 0.0:
        return None

    x = parse_float_attr(child, "x", axis="x", default=0.0) or 0.0
    y = parse_float_attr(child, "y", axis="y", default=0.0) or 0.0
    width = parse_float_attr(child, "width", axis="x", default=0.0) or 0.0
    height = parse_float_attr(child, "height", axis="y", default=0.0) or 0.0
    if x > 0.0 or y > 0.0:
        return None
    if x + width < tile_width or y + height < tile_height:
        return None

    styles = style_map(child)
    fill = child.get("fill") or styles.get("fill")
    color = parse_color(fill)
    if color is None or color.a <= 0.0:
        return None
    rgb = rgb_object_to_hex(color, default=None)
    if rgb is None:
        return None

    opacity = color.a
    opacity *= pattern_opacity(child.get("opacity") or styles.get("opacity"))
    opacity *= pattern_opacity(child.get("fill-opacity") or styles.get("fill-opacity"))
    return SolidPaint(rgb=rgb, opacity=max(0.0, min(1.0, opacity)))


def _has_solid_tile_modifier(element: etree._Element) -> bool:
    styles = style_map(element)
    for name in ("transform", "clip-path", "mask", "filter"):
        if _visible_modifier_value(element.get(name) or styles.get(name)):
            return True
    display = (element.get("display") or styles.get("display") or "").strip().lower()
    visibility = (
        (element.get("visibility") or styles.get("visibility") or "").strip().lower()
    )
    if display == "none" or visibility == "hidden":
        return True
    if element.get("class"):
        return True
    return False


def _visible_modifier_value(value: str | None) -> bool:
    if value is None:
        return False
    token = value.strip().lower()
    return bool(token) and token != "none"


def _visible_stroke(element: etree._Element) -> bool:
    styles = style_map(element)
    stroke = element.get("stroke") or styles.get("stroke")
    color = parse_color(stroke)
    if color is None or color.a <= 0.0:
        return False
    stroke_opacity = pattern_opacity(
        element.get("stroke-opacity") or styles.get("stroke-opacity")
    )
    return stroke_opacity > 0.0


def record_pattern_metadata(
    *,
    pattern_id: str,
    descriptor: PatternDescriptor,
    pattern_service: Any,
    services: ConversionServices,
    metadata: dict[str, Any],
    role: str,
    context: Any | None,
    tracer: ConversionTracer | None,
) -> None:
    analysis_entry: dict[str, Any] = {
        "id": pattern_id,
        "type": PatternType.CUSTOM.value,
        "complexity": PatternComplexity.SIMPLE.value,
        "child_count": len(descriptor.children),
        "powerpoint_compatible": True,
        "emf_fallback_recommended": False,
    }

    geometry_entry = {
        "tile_width": descriptor.width,
        "tile_height": descriptor.height,
        "units": descriptor.units,
        "content_units": descriptor.content_units,
    }
    if descriptor.transform and not matrix_tuple_is_identity(descriptor.transform):
        geometry_entry["transform_matrix"] = descriptor.transform
    analysis_entry["geometry"] = geometry_entry

    processor = get_pattern_processor(services)
    analysis = None
    if processor is not None and pattern_service is not None:
        try:
            pattern_element = pattern_service.as_element(descriptor)
        except Exception:  # pragma: no cover - defensive
            pattern_element = None
        if pattern_element is not None:
            try:
                analysis = processor.analyze_pattern_element(pattern_element, context)
            except Exception:  # pragma: no cover - defensive
                analysis = None

    colors = None
    color_stats = None
    preset_candidate = None
    if analysis is not None:
        pattern_type = getattr(analysis, "pattern_type", None)
        if pattern_type is not None:
            analysis_entry["type"] = getattr(pattern_type, "value", str(pattern_type))

        complexity_attr = getattr(analysis, "complexity", None)
        if complexity_attr is not None:
            analysis_entry["complexity"] = getattr(
                complexity_attr, "value", str(complexity_attr)
            )

        analysis_entry["child_count"] = getattr(
            analysis, "child_count", analysis_entry["child_count"]
        )
        analysis_entry["powerpoint_compatible"] = getattr(
            analysis, "powerpoint_compatible", True
        )
        analysis_entry["emf_fallback_recommended"] = getattr(
            analysis, "emf_fallback_recommended", False
        )

        geometry = getattr(analysis, "geometry", None)
        if geometry is not None:
            geometry_entry = {
                "tile_width": getattr(geometry, "tile_width", None),
                "tile_height": getattr(geometry, "tile_height", None),
                "aspect_ratio": getattr(geometry, "aspect_ratio", None),
                "units": getattr(geometry, "units", None),
                "content_units": getattr(geometry, "content_units", None),
                "transform_matrix": getattr(geometry, "transform_matrix", None),
            }
            analysis_entry["geometry"] = geometry_entry

        colors = getattr(analysis, "colors_used", None)
        if colors:
            analysis_entry["colors_used"] = list(colors)

        color_stats = getattr(analysis, "color_statistics", None)
        if isinstance(color_stats, dict) and color_stats:
            analysis_entry["color_statistics"] = color_stats

        preset_candidate = getattr(analysis, "preset_candidate", None)
        if preset_candidate:
            analysis_entry["preset_candidate"] = preset_candidate

    metadata.setdefault("paint_analysis", {}).setdefault(role, {})["pattern"] = (
        analysis_entry
    )

    paint_policy = ensure_paint_policy(metadata, role)
    paint_policy.setdefault("type", "pattern")
    paint_policy.setdefault("id", pattern_id)
    paint_policy.setdefault(
        "complexity",
        analysis_entry.get("complexity", PatternComplexity.SIMPLE.value),
    )

    if colors:
        paint_policy.setdefault("palette", list(colors))
    if preset_candidate:
        paint_policy.setdefault("preset_candidate", preset_candidate)
    if isinstance(color_stats, dict):
        recommended_space = color_stats.get("recommended_space")
        if recommended_space:
            paint_policy.setdefault("recommended_color_space", recommended_space)

    requires_emf = analysis_entry.get("emf_fallback_recommended", False)
    powerpoint_ok = analysis_entry.get("powerpoint_compatible", True)
    if requires_emf or not powerpoint_ok:
        paint_policy["suggest_fallback"] = FALLBACK_EMF
        maybe_set_geometry_fallback(metadata, FALLBACK_EMF, tracer)

    if tracer is not None:
        decision = (
            "emf" if paint_policy.get("suggest_fallback") == FALLBACK_EMF else "native"
        )
        tracer.record_paint_decision(
            paint_type="pattern",
            paint_id=pattern_id,
            decision=decision,
            metadata={
                "analysis": analysis_entry,
                "policy": paint_policy,
            },
        )
