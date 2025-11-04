"""Shape rendering helpers for DrawingML writer."""

from __future__ import annotations

import html
import logging
from typing import Iterable, Mapping

from svg2ooxml.drawingml.generator import DrawingMLPathGenerator, px_to_emu
from svg2ooxml.drawingml.paint_runtime import clip_rect_to_xml
from svg2ooxml.ir.geometry import LineSegment, Rect
from svg2ooxml.ir.scene import Image, Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle, Line, Polyline, Polygon
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame, WordArtCandidate
from svg2ooxml.policy.constants import FALLBACK_BITMAP

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import (
    a_elem,
    a_sub,
    to_string,
    blur,
    soft_edge,
    glow,
    outer_shadow,
    reflection,
    effect_list,
    srgb_color,
)
from svg2ooxml.ir.effects import (
    BlurEffect,
    CustomEffect,
    Effect,
    GlowEffect,
    ReflectionEffect,
    ShadowEffect,
    SoftEdgeEffect,
)


def render_rectangle(
    rect: Rectangle,
    shape_id: int,
    *,
    template: str,
    paint_to_fill,
    stroke_to_xml,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
) -> str:
    bounds = rect.bounds
    preset = "roundRect" if rect.is_rounded else "rect"
    av_list = _round_rect_adjustment_block(bounds.width, bounds.height, rect.corner_radius) if rect.is_rounded else "        <a:avLst/>\n"
    return template.format(
        SHAPE_ID=shape_id,
        X_EMU=px_to_emu(bounds.x),
        Y_EMU=px_to_emu(bounds.y),
        WIDTH_EMU=px_to_emu(bounds.width),
        HEIGHT_EMU=px_to_emu(bounds.height),
        PRESET=preset,
        AV_LIST=av_list,
        FILL_XML=_format_block(paint_to_fill(rect.fill), "        "),
        STROKE_XML=_format_block(stroke_to_xml(rect.stroke, metadata=rect.metadata), "        "),
        HYPERLINK_XML=hyperlink_xml,
        CLIP_PATH_XML=_format_block(clip_path_xml, "        ") if clip_path_xml else "",
        MASK_XML=_format_block(mask_xml, "        ") if mask_xml else "",
        EFFECTS_XML=_effect_block(rect.effects),
    )


def render_circle(
    circle: Circle,
    shape_id: int,
    *,
    template: str,
    paint_to_fill,
    stroke_to_xml,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
) -> str:
    size = circle.radius * 2.0
    bounds = Rect(
        x=circle.center.x - circle.radius,
        y=circle.center.y - circle.radius,
        width=size,
        height=size,
    )
    return render_preset_shape(
        bounds=bounds,
        shape_id=shape_id,
        preset="ellipse",
        template=template,
        fill_xml=_format_block(paint_to_fill(circle.fill), "        "),
        stroke_xml=_format_block(stroke_to_xml(circle.stroke, metadata=circle.metadata), "        "),
        effects_xml=_effect_block(circle.effects),
        hyperlink_xml=hyperlink_xml,
        clip_path_xml=clip_path_xml,
        mask_xml=mask_xml,
    )


def render_ellipse(
    ellipse: Ellipse,
    shape_id: int,
    *,
    template: str,
    paint_to_fill,
    stroke_to_xml,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
) -> str:
    bounds = Rect(
        x=ellipse.center.x - ellipse.radius_x,
        y=ellipse.center.y - ellipse.radius_y,
        width=ellipse.radius_x * 2.0,
        height=ellipse.radius_y * 2.0,
    )
    return render_preset_shape(
        bounds=bounds,
        shape_id=shape_id,
        preset="ellipse",
        template=template,
        fill_xml=_format_block(paint_to_fill(ellipse.fill), "        "),
        stroke_xml=_format_block(stroke_to_xml(ellipse.stroke, metadata=ellipse.metadata), "        "),
        effects_xml=_effect_block(ellipse.effects),
        hyperlink_xml=hyperlink_xml,
        clip_path_xml=clip_path_xml,
        mask_xml=mask_xml,
    )


def render_preset_shape(
    *,
    bounds: Rect,
    shape_id: int,
    preset: str,
    template: str,
    fill_xml: str,
    stroke_xml: str,
    effects_xml: str,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
) -> str:
    return template.format(
        SHAPE_ID=shape_id,
        PRESET=preset,
        X_EMU=px_to_emu(bounds.x),
        Y_EMU=px_to_emu(bounds.y),
        WIDTH_EMU=px_to_emu(bounds.width),
        HEIGHT_EMU=px_to_emu(bounds.height),
        FILL_XML=fill_xml,
        STROKE_XML=stroke_xml,
        EFFECTS_XML=effects_xml,
        HYPERLINK_XML=hyperlink_xml,
        CLIP_PATH_XML=_format_block(clip_path_xml, "        ") if clip_path_xml else "",
        MASK_XML=_format_block(mask_xml, "        ") if mask_xml else "",
    )


def render_path(
    path: IRPath,
    shape_id: int,
    *,
    template: str,
    paint_to_fill,
    stroke_to_xml,
    path_generator: DrawingMLPathGenerator,
    policy_for,
    logger: logging.Logger,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
) -> str:
    fill_xml = _format_block(paint_to_fill(path.fill), "        ")
    stroke_xml = _format_block(stroke_to_xml(path.stroke, metadata=path.metadata), "        ")
    policy_geom = policy_for(path.metadata, "geometry")
    shape_name = f"Path {shape_id}"
    if policy_geom:
        suffix = ", ".join(f"{key}={value}" for key, value in sorted(policy_geom.items()))
        shape_name += f" ({suffix})"
    if policy_geom.get("suggest_fallback") == FALLBACK_BITMAP:
        logger.warning(
            "Path %s marked for bitmap fallback by policy; emitting native geometry until bitmap exporter is available.",
            shape_id,
        )
    fill_mode = "norm" if path.fill else "none"
    stroke_mode = "true" if path.stroke else "false"
    geometry = path_generator.generate_custom_geometry(
        path.segments,
        fill_mode=fill_mode,
        stroke_mode=stroke_mode,
        closed=path.is_closed,
    )
    bounds = geometry.bounds

    clip_fragments: list[str] = []
    if isinstance(path.metadata, dict):
        clip_meta = path.metadata.get("marker_clip")
        overflow = path.metadata.get("marker_overflow")
        if clip_meta and overflow == "hidden":
            clip_fragments.append(_format_block(clip_rect_to_xml(clip_meta), "        "))
    if clip_path_xml:
        clip_fragments.append(_format_block(clip_path_xml, "        "))
    clip_block = "".join(clip_fragments)

    mask_block = _format_block(mask_xml, "        ") if mask_xml else ""

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        X_EMU=px_to_emu(bounds.x),
        Y_EMU=px_to_emu(bounds.y),
        WIDTH_EMU=geometry.width_emu,
        HEIGHT_EMU=geometry.height_emu,
        GEOMETRY_XML=_format_block(geometry.xml, "        "),
        CLIP_PATH_XML=clip_block,
        MASK_XML=mask_block,
        FILL_XML=fill_xml,
        STROKE_XML=stroke_xml,
        HYPERLINK_XML=hyperlink_xml,
        EFFECTS_XML=_effect_block(path.effects),
    )


def render_line(
    line: Line,
    shape_id: int,
    *,
    template: str,
    path_generator: DrawingMLPathGenerator,
    stroke_to_xml,
    paint_to_fill,
    policy_for,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
) -> str:
    shape_name = f"Line {shape_id}"
    policy_geom = policy_for(line.metadata, "geometry")
    if policy_geom:
        suffix = ", ".join(f"{key}={value}" for key, value in sorted(policy_geom.items()))
        shape_name += f" ({suffix})"

    segments = [LineSegment(line.start, line.end)]
    geometry = path_generator.generate_custom_geometry(
        segments,
        fill_mode="none",
        stroke_mode="true" if line.stroke else "false",
        closed=False,
    )
    bounds = geometry.bounds

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        X_EMU=px_to_emu(bounds.x),
        Y_EMU=px_to_emu(bounds.y),
        WIDTH_EMU=geometry.width_emu,
        HEIGHT_EMU=geometry.height_emu,
        GEOMETRY_XML=_format_block(geometry.xml, "        "),
        CLIP_PATH_XML=_format_block(clip_path_xml, "        ") if clip_path_xml else "",
        MASK_XML=_format_block(mask_xml, "        ") if mask_xml else "",
        FILL_XML=_format_block(paint_to_fill(None), "        "),
        STROKE_XML=_format_block(stroke_to_xml(line.stroke, metadata=line.metadata), "        "),
        EFFECTS_XML=_effect_block(line.effects),
        HYPERLINK_XML=hyperlink_xml,
    )


def render_polyline(
    polyline: Polyline,
    shape_id: int,
    *,
    template: str,
    path_generator: DrawingMLPathGenerator,
    paint_to_fill,
    stroke_to_xml,
    policy_for,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
) -> str:
    return _render_polygonal_shape(
        polyline,
        shape_id,
        template=template,
        path_generator=path_generator,
        paint_to_fill=paint_to_fill,
        stroke_to_xml=stroke_to_xml,
        policy_for=policy_for,
        hyperlink_xml=hyperlink_xml,
        clip_path_xml=clip_path_xml,
        mask_xml=mask_xml,
        closed=False,
    )


def render_polygon(
    polygon: Polygon,
    shape_id: int,
    *,
    template: str,
    path_generator: DrawingMLPathGenerator,
    paint_to_fill,
    stroke_to_xml,
    policy_for,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
) -> str:
    return _render_polygonal_shape(
        polygon,
        shape_id,
        template=template,
        path_generator=path_generator,
        paint_to_fill=paint_to_fill,
        stroke_to_xml=stroke_to_xml,
        policy_for=policy_for,
        hyperlink_xml=hyperlink_xml,
        clip_path_xml=clip_path_xml,
        mask_xml=mask_xml,
        closed=True,
    )


def render_textframe(
    frame: TextFrame,
    shape_id: int,
    *,
    template: str,
    policy_for,
    logger: logging.Logger,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
    register_run_navigation=None,
) -> str:
    bbox = frame.bbox
    align = {
        TextAnchor.START: "l",
        TextAnchor.MIDDLE: "ctr",
        TextAnchor.END: "r",
    }.get(frame.anchor, "l")

    policy_text = policy_for(getattr(frame, "metadata", None), "text")
    note_parts: list[str] = []
    behavior = policy_text.get("rendering_behavior")
    if isinstance(behavior, str) and behavior:
        note_parts.append(f"rendering_behavior={behavior}")
        logger.warning(
            "Text frame %s requests %s rendering; emitting live text until fallback support lands.",
            shape_id,
            behavior,
        )
    fallback_font = policy_text.get("font_fallback")
    if isinstance(fallback_font, str) and fallback_font:
        note_parts.append(f"font_fallback={fallback_font}")

    shape_name = f"Text {shape_id}"
    if note_parts:
        logger.debug("Text frame %s policy notes: %s", shape_id, "; ".join(note_parts))

    runs_xml = build_runs_xml(frame.runs or [], register_navigation=register_run_navigation)
    if not runs_xml:
        runs_xml = build_runs_xml([Run(text="", font_family="Arial", font_size_pt=12.0)], register_navigation=register_run_navigation)

    body_extra = ""

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        X_EMU=px_to_emu(bbox.x),
        Y_EMU=px_to_emu(bbox.y),
        WIDTH_EMU=px_to_emu(bbox.width),
        HEIGHT_EMU=px_to_emu(bbox.height),
        TEXT_ALIGN=align,
        BODY_EXTRA=body_extra,
        RUNS_XML=runs_xml,
        HYPERLINK_XML=hyperlink_xml,
        CLIP_PATH_XML=_format_block(clip_path_xml, "        ") if clip_path_xml else "",
        MASK_XML=_format_block(mask_xml, "        ") if mask_xml else "",
    )


def render_wordart(
    frame: TextFrame,
    candidate: WordArtCandidate,
    shape_id: int,
    *,
    template: str,
    policy_for,
    logger: logging.Logger,
    hyperlink_xml: str = "",
    clip_path_xml: str = "",
    mask_xml: str = "",
    register_run_navigation=None,
) -> str:
    bbox = frame.bbox
    align = {
        TextAnchor.START: "l",
        TextAnchor.MIDDLE: "ctr",
        TextAnchor.END: "r",
    }.get(frame.anchor, "l")

    policy_text = policy_for(getattr(frame, "metadata", None), "text")
    note_parts: list[str] = []
    if policy_text:
        for key, value in sorted(policy_text.items()):
            note_parts.append(f"{key}={value}")

    if candidate.fallback_strategy:
        note_parts.append(f"fallback={candidate.fallback_strategy}")
    note_parts.append(f"confidence={candidate.confidence:.2f}")

    shape_name = f"WordArt {shape_id}"
    if note_parts:
        logger.debug("WordArt %s policy notes: %s", shape_id, "; ".join(note_parts))

    runs_xml = build_runs_xml(frame.runs or [], register_navigation=register_run_navigation)
    if not runs_xml:
        runs_xml = build_runs_xml([Run(text="", font_family="Arial", font_size_pt=12.0)], register_navigation=register_run_navigation)

    body_extra = "        <a:normAutofit/>\n"

    if candidate.fallback_strategy and candidate.fallback_strategy != "vector_outline":
        logger.info(
            "WordArt %s prefers native preset '%s' with fallback %s",
            shape_id,
            candidate.preset,
            candidate.fallback_strategy,
        )

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        X_EMU=px_to_emu(bbox.x),
        Y_EMU=px_to_emu(bbox.y),
        WIDTH_EMU=px_to_emu(bbox.width),
        HEIGHT_EMU=px_to_emu(bbox.height),
        TEXT_ALIGN=align,
        WARP_PRESET=candidate.preset,
        BODY_EXTRA=body_extra,
        RUNS_XML=runs_xml,
        HYPERLINK_XML=hyperlink_xml,
        CLIP_PATH_XML=_format_block(clip_path_xml, "        ") if clip_path_xml else "",
        MASK_XML=_format_block(mask_xml, "        ") if mask_xml else "",
    )


def build_runs_xml(runs: Iterable[Run], register_navigation=None) -> str:
    fragments: list[str] = []
    for run in runs:
        text = (run.text or "").replace("\r\n", "\n").replace("\r", "\n")
        parts = text.split("\n") if text else [""]
        navigation_handler = None
        if register_navigation is not None and getattr(run, "navigation", None) is not None:
            navigation_registered = False

            def _navigation_factory(segment_text: str) -> str:
                nonlocal navigation_registered
                if navigation_registered:
                    return ""
                navigation_registered = True
                return register_navigation(run.navigation, segment_text)

            navigation_handler = _navigation_factory
        for index, segment in enumerate(parts):
            if index > 0:
                fragments.append("<a:br/>")
            fragments.append(run_fragment(run, segment, navigation_handler))
    return "".join(fragments)


def run_fragment(run: Run, text_segment: str, navigation_factory) -> str:
    size = max(100, int(round(run.font_size_pt * 100)))
    attributes = [f'sz="{size}"']
    if run.bold:
        attributes.append('b="1"')
    if run.italic:
        attributes.append('i="1"')
    if run.underline:
        attributes.append('u="sng"')
    if run.strike:
        attributes.append('strike="sng"')
    if getattr(run, "kerning", None) is not None:
        kern_value = int(round(float(run.kerning) * 1000))
        attributes.append(f'kern="{kern_value}"')
    if getattr(run, "letter_spacing", None) is not None:
        spacing_value = int(round(float(run.letter_spacing) * 1000))
        attributes.append(f'spc="{spacing_value}"')
    language = getattr(run, "language", None)
    if language:
        attributes.append(f'lang="{html.escape(language, quote=True)}"')

    rgb = (run.rgb or "000000").upper()
    font_family = html.escape(run.font_family or "Arial", quote=True)
    east_asian = html.escape(getattr(run, "east_asian_font", "") or run.font_family or "Arial", quote=True)
    complex_script = html.escape(getattr(run, "complex_script_font", "") or run.font_family or "Arial", quote=True)

    # Build a:r element with lxml
    r = a_elem("r")

    # Build a:rPr with attributes
    rPr = a_elem("rPr")
    for attr_str in attributes:
        # Parse attribute strings like 'sz="1200"'
        if "=" in attr_str:
            key, val = attr_str.split("=", 1)
            rPr.set(key, val.strip('"'))

    # Add solidFill
    solidFill = a_sub(rPr, "solidFill")
    a_sub(solidFill, "srgbClr", val=rgb)

    # Add font typefaces
    a_sub(rPr, "latin", typeface=font_family)
    a_sub(rPr, "ea", typeface=east_asian)
    a_sub(rPr, "cs", typeface=complex_script)

    # Add navigation if present
    if navigation_factory is not None:
        nav_xml = navigation_factory(text_segment)
        if nav_xml:
            from lxml import etree
            wrapped = f'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">{nav_xml}</root>'
            temp = etree.fromstring(wrapped.encode('utf-8'))
            for child in temp:
                rPr.append(child)

    r.append(rPr)

    # Build a:t element
    text_value = text_segment
    preserve = False
    if text_value == "":
        text_value = " "
        preserve = True
    elif text_value.startswith(" ") or text_value.endswith(" "):
        preserve = True

    t = a_elem("t")
    t.text = text_value  # lxml handles escaping
    if preserve:
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    r.append(t)

    return to_string(r)


def _round_rect_adjustment_block(width: float, height: float, radius: float) -> str:
    avLst = a_elem("avLst")

    if width > 0 and height > 0 and radius > 0:
        min_dim = min(width, height)
        max_corner = min_dim / 2.0
        effective_radius = min(radius, max_corner)
        ratio_x = (effective_radius / width) * 100 if width > 0 else 0.0
        ratio_y = (effective_radius / height) * 100 if height > 0 else 0.0
        ratio = min(50.0, max(ratio_x, ratio_y))
        adj = int(round(ratio * 1000))
        a_sub(avLst, "gd", name="adj", fmla=f"val {adj}")

    xml = to_string(avLst)
    # Add indentation for formatting
    return "        " + xml.replace("\n", "\n        ") + "\n"


def _render_polygonal_shape(
    shape: Polyline | Polygon,
    shape_id: int,
    *,
    template: str,
    path_generator: DrawingMLPathGenerator,
    paint_to_fill,
    stroke_to_xml,
    policy_for,
    hyperlink_xml: str,
    clip_path_xml: str,
    mask_xml: str,
    closed: bool,
) -> str:
    points = getattr(shape, "points", [])
    if len(points) < (3 if closed else 2):
        raise ValueError("Polygonal shape requires sufficient points")

    segments = [LineSegment(points[i], points[i + 1]) for i in range(len(points) - 1)]
    if closed:
        segments.append(LineSegment(points[-1], points[0]))

    geometry = path_generator.generate_custom_geometry(
        segments,
        fill_mode="norm" if closed and getattr(shape, "fill", None) else "none",
        stroke_mode="true" if getattr(shape, "stroke", None) else "false",
        closed=closed,
    )
    bounds = geometry.bounds

    shape_name = f"{'Polygon' if closed else 'Polyline'} {shape_id}"
    policy_geom = policy_for(getattr(shape, "metadata", None), "geometry")
    if policy_geom:
        suffix = ", ".join(f"{key}={value}" for key, value in sorted(policy_geom.items()))
        shape_name += f" ({suffix})"

    fill_xml = paint_to_fill(getattr(shape, "fill", None))
    stroke_xml = stroke_to_xml(getattr(shape, "stroke", None), metadata=getattr(shape, "metadata", None))

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        X_EMU=px_to_emu(bounds.x),
        Y_EMU=px_to_emu(bounds.y),
        WIDTH_EMU=geometry.width_emu,
        HEIGHT_EMU=geometry.height_emu,
        GEOMETRY_XML=_format_block(geometry.xml, "        "),
        CLIP_PATH_XML=_format_block(clip_path_xml, "        ") if clip_path_xml else "",
        MASK_XML=_format_block(mask_xml, "        ") if mask_xml else "",
        FILL_XML=_format_block(fill_xml, "        "),
        STROKE_XML=_format_block(stroke_xml, "        "),
        EFFECTS_XML=_effect_block(getattr(shape, "effects", [])),
        HYPERLINK_XML=hyperlink_xml,
    )


def _format_block(xml: str, indent: str) -> str:
    if not xml:
        return ""
    lines = xml.splitlines()
    return "\n".join(indent + line for line in lines) + "\n"


def _effect_block(effects: Iterable[Effect]) -> str:
    effect_strings: list[str] = []
    for effect in effects or []:
        xml = _effect_to_drawingml(effect)
        if xml:
            effect_strings.append(xml.strip())

    if not effect_strings:
        return ""

    if len(effect_strings) == 1:
        return _format_block(effect_strings[0], "        ")

    combined_parts: list[str] = []
    for xml in effect_strings:
        combined_parts.append(_strip_effect_list(xml))
    combined = "".join(combined_parts)
    return _format_block(f"<a:effectLst>{combined}</a:effectLst>", "        ")


def _strip_effect_list(xml: str) -> str:
    start = xml.find("<a:effectLst")
    if start == -1:
        return xml
    open_end = xml.find(">", start)
    close = xml.rfind("</a:effectLst>")
    if open_end == -1 or close == -1:
        return xml
    return xml[open_end + 1 : close]


def _effect_to_drawingml(effect: Effect) -> str:
    """Convert effect to DrawingML XML using safe lxml builders.

    Args:
        effect: Effect object (Blur, SoftEdge, Glow, Shadow, Reflection, or Custom)

    Returns:
        DrawingML XML string with <a:effectLst> wrapper
    """
    if isinstance(effect, CustomEffect):
        return (effect.drawingml or "").strip()

    if isinstance(effect, BlurEffect):
        return to_string(effect_list(blur(effect.to_emu())))

    if isinstance(effect, SoftEdgeEffect):
        return to_string(effect_list(soft_edge(effect.to_emu())))

    if isinstance(effect, GlowEffect):
        color = (effect.color or "FFFFFF").upper()
        color_elem = srgb_color(color)
        return to_string(effect_list(glow(effect.to_emu(), color_elem)))

    if isinstance(effect, ShadowEffect):
        blur_rad, dist = effect.to_emu()
        direction = effect.to_direction_emu()
        alpha = effect.to_alpha_val()
        color = (effect.color or "000000").upper()
        color_elem = srgb_color(color, alpha=alpha)
        shadow = outer_shadow(blur_rad, dist, direction, color_elem, algn="ctr", rotWithShape="0")
        return to_string(effect_list(shadow))

    if isinstance(effect, ReflectionEffect):
        blur_rad, dist = effect.to_emu()
        start_alpha, end_alpha = effect.to_alpha_vals()
        return to_string(effect_list(reflection(blur_rad, dist, start_alpha, end_alpha)))

    return ""


__all__ = [
    "build_runs_xml",
    "render_line",
    "render_polyline",
    "render_polygon",
    "render_circle",
    "render_ellipse",
    "render_path",
    "render_rectangle",
    "render_textframe",
    "render_preset_shape",
    "render_wordart",
    "run_fragment",
]
