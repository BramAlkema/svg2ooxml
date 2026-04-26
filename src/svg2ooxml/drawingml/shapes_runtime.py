"""Shape rendering helpers for DrawingML writer."""

from __future__ import annotations

import logging

from svg2ooxml.drawingml.effects_runtime import effect_block as _effect_block
from svg2ooxml.drawingml.generator import DrawingMLPathGenerator, px_to_emu
from svg2ooxml.drawingml.shape_attrs import descr_attr as _descr_attr
from svg2ooxml.drawingml.text_runs_runtime import (
    build_runs_xml,
    run_fragment,
)
from svg2ooxml.drawingml.text_shapes_runtime import render_textframe, render_wordart
from svg2ooxml.drawingml.xml_builder import (
    a_elem,
    a_sub,
    to_string,
)
from svg2ooxml.ir.geometry import LineSegment, Rect
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
from svg2ooxml.policy.constants import FALLBACK_BITMAP


def render_rectangle(
    rect: Rectangle,
    shape_id: int,
    *,
    template: str,
    paint_to_fill,
    stroke_to_xml,
    hyperlink_xml: str = "",
) -> str:
    bounds = rect.bounds
    preset = "roundRect" if rect.is_rounded else "rect"
    av_list = (
        _round_rect_adjustment_block(bounds.width, bounds.height, rect.corner_radius)
        if rect.is_rounded
        else "        <a:avLst/>\n"
    )
    return template.format(
        SHAPE_ID=shape_id,
        X_EMU=px_to_emu(bounds.x),
        Y_EMU=px_to_emu(bounds.y),
        WIDTH_EMU=px_to_emu(bounds.width),
        HEIGHT_EMU=px_to_emu(bounds.height),
        PRESET=preset,
        AV_LIST=av_list,
        FILL_XML=_format_block(
            paint_to_fill(rect.fill, opacity=rect.opacity, shape_bbox=bounds), "        "
        ),
        STROKE_XML=_format_block(
            stroke_to_xml(rect.stroke, metadata=rect.metadata, opacity=rect.opacity),
            "        ",
        ),
        HYPERLINK_XML=hyperlink_xml,
        EFFECTS_XML=_effect_block(rect.effects),
        DESCR_ATTR=_descr_attr(rect.metadata),
    )


def render_circle(
    circle: Circle,
    shape_id: int,
    *,
    template: str,
    paint_to_fill,
    stroke_to_xml,
    hyperlink_xml: str = "",
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
        fill_xml=_format_block(
            paint_to_fill(circle.fill, opacity=circle.opacity, shape_bbox=bounds),
            "        ",
        ),
        stroke_xml=_format_block(
            stroke_to_xml(
                circle.stroke,
                metadata=circle.metadata,
                opacity=circle.opacity,
            ),
            "        ",
        ),
        effects_xml=_effect_block(circle.effects),
        hyperlink_xml=hyperlink_xml,
        descr_attr=_descr_attr(circle.metadata),
    )


def render_ellipse(
    ellipse: Ellipse,
    shape_id: int,
    *,
    template: str,
    paint_to_fill,
    stroke_to_xml,
    hyperlink_xml: str = "",
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
        fill_xml=_format_block(
            paint_to_fill(ellipse.fill, opacity=ellipse.opacity, shape_bbox=bounds),
            "        ",
        ),
        stroke_xml=_format_block(
            stroke_to_xml(
                ellipse.stroke,
                metadata=ellipse.metadata,
                opacity=ellipse.opacity,
            ),
            "        ",
        ),
        effects_xml=_effect_block(ellipse.effects),
        hyperlink_xml=hyperlink_xml,
        descr_attr=_descr_attr(ellipse.metadata),
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
    descr_attr: str = "",
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
        DESCR_ATTR=descr_attr,
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
) -> str:
    fill_xml = _format_block(
        paint_to_fill(path.fill, opacity=path.opacity, shape_bbox=path.bbox),
        "        ",
    )
    stroke_xml = _format_block(
        stroke_to_xml(path.stroke, metadata=path.metadata, opacity=path.opacity),
        "        ",
    )
    policy_geom = policy_for(path.metadata, "geometry")
    shape_name = f"Path {shape_id}"
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

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        X_EMU=px_to_emu(bounds.x),
        Y_EMU=px_to_emu(bounds.y),
        WIDTH_EMU=geometry.width_emu,
        HEIGHT_EMU=geometry.height_emu,
        GEOMETRY_XML=_format_block(geometry.xml, "        "),
        FILL_XML=fill_xml,
        STROKE_XML=stroke_xml,
        HYPERLINK_XML=hyperlink_xml,
        EFFECTS_XML=_effect_block(path.effects),
        DESCR_ATTR=_descr_attr(path.metadata),
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
) -> str:
    del path_generator, policy_for

    dx = float(line.end.x - line.start.x)
    dy = float(line.end.y - line.start.y)
    bounds = line.bbox
    width = max(abs(dx), 0.0)
    height = max(abs(dy), 0.0)
    xfrm_attrs = ""
    if dx * dy < 0:
        xfrm_attrs = ' flipH="1"'

    return template.format(
        SHAPE_ID=shape_id,
        X_EMU=px_to_emu(bounds.x),
        Y_EMU=px_to_emu(bounds.y),
        WIDTH_EMU=px_to_emu(width),
        HEIGHT_EMU=px_to_emu(height),
        XFRM_ATTRS=xfrm_attrs,
        GEOMETRY_XML='        <a:prstGeom prst="line"><a:avLst/></a:prstGeom>\n',
        FILL_XML=_format_block(paint_to_fill(None), "        "),
        STROKE_XML=_format_block(
            stroke_to_xml(line.stroke, metadata=line.metadata, opacity=line.opacity),
            "        ",
        ),
        EFFECTS_XML=_effect_block(line.effects),
        HYPERLINK_XML=hyperlink_xml,
        DESCR_ATTR=_descr_attr(line.metadata),
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
        closed=True,
    )


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

    opacity = getattr(shape, "opacity", 1.0)
    fill_xml = paint_to_fill(
        getattr(shape, "fill", None),
        opacity=opacity,
        shape_bbox=bounds,
    )
    stroke_xml = stroke_to_xml(
        getattr(shape, "stroke", None),
        metadata=getattr(shape, "metadata", None),
        opacity=opacity,
    )

    return template.format(
        SHAPE_ID=shape_id,
        SHAPE_NAME=shape_name,
        X_EMU=px_to_emu(bounds.x),
        Y_EMU=px_to_emu(bounds.y),
        WIDTH_EMU=geometry.width_emu,
        HEIGHT_EMU=geometry.height_emu,
        GEOMETRY_XML=_format_block(geometry.xml, "        "),
        FILL_XML=_format_block(fill_xml, "        "),
        STROKE_XML=_format_block(stroke_xml, "        "),
        EFFECTS_XML=_effect_block(getattr(shape, "effects", [])),
        HYPERLINK_XML=hyperlink_xml,
        DESCR_ATTR=_descr_attr(getattr(shape, "metadata", None)),
    )


def _format_block(xml: str, indent: str) -> str:
    if not xml:
        return ""
    lines = xml.splitlines()
    return "\n".join(indent + line for line in lines) + "\n"


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
