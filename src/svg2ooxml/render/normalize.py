"""SVG normalisation pass producing a canonical node tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
from lxml import etree

from svg2ooxml.parser.geometry.matrix import Matrix2D, parse_transform_list
from svg2ooxml.parser.units import UnitConverter
from svg2ooxml.geometry.paths.parser import parse_path_data, PathParseError
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle

from .paint import compute_paints

_DEFINITION_TAGS = {
    "defs",
    "symbol",
    "clipPath",
    "mask",
    "linearGradient",
    "radialGradient",
    "pattern",
    "filter",
    "marker",
}


@dataclass(slots=True)
class NormalizedNode:
    """Representation of an SVG node after normalisation."""

    tag: str
    source: etree._Element
    local_transform: Matrix2D
    world_transform: Matrix2D
    geometry: Any | None = None
    fill: Any | None = None
    stroke: Any | None = None
    style: dict[str, str] = field(default_factory=dict)
    clip_href: str | None = None
    mask_href: str | None = None
    filter_href: str | None = None
    children: list["NormalizedNode"] = field(default_factory=list)

    def world_matrix_np(self) -> np.ndarray:
        """Return world transform as a NumPy 3x3 matrix."""

        m = self.world_transform
        return np.array(
            [
                [m.a, m.c, m.e],
                [m.b, m.d, m.f],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        )


@dataclass(slots=True)
class NormalizedSvgTree:
    """Normalized SVG tree with lookup tables for fast access."""

    root: NormalizedNode
    viewport_width: float
    viewport_height: float
    definitions: dict[str, NormalizedNode] = field(default_factory=dict)
    node_index: dict[int, NormalizedNode] = field(default_factory=dict)


def normalize_svg(svg_root: etree._Element) -> NormalizedSvgTree:
    """Convert an lxml SVG element into a NormalizedSvgTree."""

    if svg_root is None:
        raise ValueError("normalize_svg requires an SVG root element")

    width, height = _resolve_viewport(svg_root)
    node_index: dict[int, NormalizedNode] = {}
    definitions: dict[str, NormalizedNode] = {}
    root_node = _build_node(
        svg_root,
        Matrix2D.identity(),
        node_index,
        definitions,
        inherited_style={},
    )
    _apply_paints(root_node, definitions)
    return NormalizedSvgTree(
        root=root_node,
        viewport_width=width,
        viewport_height=height,
        definitions=definitions,
        node_index=node_index,
    )


def _build_node(
    element: etree._Element,
    parent_world: Matrix2D,
    node_index: dict[int, NormalizedNode],
    definitions: dict[str, NormalizedNode],
    inherited_style: Mapping[str, str],
) -> NormalizedNode:
    tag = _local_name(getattr(element, "tag", None))
    local = parse_transform_list(element.get("transform"))
    world = parent_world.multiply(local)
    style = _compute_style(element, inherited_style)
    geometry = _resolve_geometry(element, style)

    node = NormalizedNode(
        tag=tag,
        source=element,
        local_transform=local,
        world_transform=world,
        geometry=geometry,
        style=dict(style),
        clip_href=_strip_url(element.get("clip-path")),
        mask_href=_strip_url(element.get("mask")),
        filter_href=_strip_url(element.get("filter")),
    )
    node_index[id(element)] = node

    element_id = element.get("id")
    if element_id and tag in _DEFINITION_TAGS:
        definitions[element_id] = node

    for child in element:
        if not isinstance(child.tag, str):
            continue
        child_node = _build_node(child, world, node_index, definitions, style)
        node.children.append(child_node)

    return node


def _strip_url(token: str | None) -> str | None:
    if not token:
        return None
    token = token.strip()
    if token.startswith("url(") and token.endswith(")"):
        inner = token[4:-1].strip().strip("\"'")
    else:
        inner = token
    if inner.startswith("#"):
        return inner[1:]
    return inner or None


def _resolve_viewport(svg_root: etree._Element) -> tuple[float, float]:
    converter = UnitConverter()

    width = _to_px(svg_root.get("width"), converter)
    height = _to_px(svg_root.get("height"), converter)

    if (width <= 0 or height <= 0) and svg_root.get("viewBox"):
        view_box = _parse_viewbox(svg_root.get("viewBox"))
        if view_box is not None:
            _, _, vw, vh = view_box
            width = width or vw
            height = height or vh

    if width <= 0:
        width = 1.0
    if height <= 0:
        height = 1.0
    return width, height


def _to_px(value: str | None, converter: UnitConverter) -> float:
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return converter.to_px(value, context=None)
    except Exception:
        return 0.0


def _parse_viewbox(value: str) -> tuple[float, float, float, float] | None:
    parts = value.replace(",", " ").split()
    if len(parts) != 4:
        return None
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _local_name(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _apply_paints(node: NormalizedNode, definitions: Mapping[str, NormalizedNode]) -> None:
    if node.tag not in {"linearGradient", "radialGradient", "pattern"}:
        fill, stroke = compute_paints(node.style, node.source, definitions)
        node.fill = fill
        node.stroke = stroke

    for child in node.children:
        _apply_paints(child, definitions)


def _compute_style(element: etree._Element, inherited: Mapping[str, str]) -> dict[str, str]:
    style: dict[str, str] = dict(inherited)
    style_attr = element.get("style")
    if style_attr:
        style.update(_parse_style_attribute(style_attr))

    for attr in (
        "fill",
        "stroke",
        "opacity",
        "fill-opacity",
        "stroke-opacity",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
    ):
        value = element.get(attr)
        if value is not None:
            style[attr] = value

    return style


def _parse_style_attribute(style: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for chunk in style.split(";"):
        if not chunk.strip():
            continue
        if ":" not in chunk:
            continue
        name, value = chunk.split(":", 1)
        result[name.strip()] = value.strip()
    return result


def _resolve_geometry(element: etree._Element, style: Mapping[str, str]) -> Any | None:
    tag = _local_name(getattr(element, "tag", None))
    if tag == "rect":
        return _rect_geometry(element)
    if tag == "circle":
        return _circle_geometry(element)
    if tag == "ellipse":
        return _ellipse_geometry(element)
    if tag == "line":
        return _line_geometry(element)
    if tag == "polyline":
        return _poly_geometry(element, closed=False)
    if tag == "polygon":
        return _poly_geometry(element, closed=True)
    if tag == "path":
        return _path_geometry(element)
    return None


def _rect_geometry(element: etree._Element) -> Rectangle | None:
    try:
        x = float(element.get("x") or 0.0)
        y = float(element.get("y") or 0.0)
        width = float(element.get("width") or 0.0)
        height = float(element.get("height") or 0.0)
        rx = float(element.get("rx") or 0.0) or float(element.get("ry") or 0.0)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    from svg2ooxml.ir.geometry import Rect

    return Rectangle(bounds=Rect(x, y, width, height), corner_radius=rx)


def _circle_geometry(element: etree._Element) -> Circle | None:
    try:
        cx = float(element.get("cx") or 0.0)
        cy = float(element.get("cy") or 0.0)
        r = float(element.get("r") or 0.0)
    except ValueError:
        return None
    if r <= 0:
        return None
    return Circle(center=Point(cx, cy), radius=r)


def _ellipse_geometry(element: etree._Element) -> Ellipse | None:
    try:
        cx = float(element.get("cx") or 0.0)
        cy = float(element.get("cy") or 0.0)
        rx = float(element.get("rx") or 0.0)
        ry = float(element.get("ry") or 0.0)
    except ValueError:
        return None
    if rx <= 0 or ry <= 0:
        return None
    return Ellipse(center=Point(cx, cy), radius_x=rx, radius_y=ry)


def _line_geometry(element: etree._Element) -> dict[str, float] | None:
    try:
        x1 = float(element.get("x1") or 0.0)
        y1 = float(element.get("y1") or 0.0)
        x2 = float(element.get("x2") or 0.0)
        y2 = float(element.get("y2") or 0.0)
    except ValueError:
        return None
    return {"type": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _poly_geometry(element: etree._Element, *, closed: bool) -> dict[str, Any] | None:
    points_attr = element.get("points")
    if not points_attr:
        return None
    coords: list[float] = []
    for part in points_attr.replace(",", " ").split():
        try:
            coords.append(float(part))
        except ValueError:
            continue
    if len(coords) < 4:
        return None
    pts = [(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]
    return {"type": "polyline", "points": pts, "closed": closed}


def _path_geometry(element: etree._Element) -> IRPath | None:
    data = element.get("d")
    if not data:
        return None
    try:
        segments = list(parse_path_data(data))
    except PathParseError:
        return None
    if not segments:
        return None
    return IRPath(segments=segments)


__all__ = ["NormalizedNode", "NormalizedSvgTree", "normalize_svg"]
