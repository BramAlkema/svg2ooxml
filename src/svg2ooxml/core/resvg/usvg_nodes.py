"""Typed nodes for the simplified usvg tree."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from svg2ooxml.common.svg_refs import local_url_id

from .geometry.matrix import Matrix
from .gradient_resolution import (
    resolve_linear_gradient_reference as _resolve_linear_gradient_reference,
)
from .gradient_resolution import (
    resolve_radial_gradient_reference as _resolve_radial_gradient_reference,
)
from .painting.gradients import LinearGradient, PatternPaint, RadialGradient
from .painting.paint import FillStyle, PaintReference, StrokeStyle, TextStyle
from .parser.presentation import Presentation

if TYPE_CHECKING:  # pragma: no cover
    from .geometry.path_normalizer import NormalizedPath


@dataclass(slots=True)
class TextSpan:
    text: str
    x: float
    y: float


@dataclass(slots=True)
class BaseNode:
    tag: str
    id: str | None
    presentation: Presentation
    attributes: dict[str, str]
    styles: dict[str, str]
    children: list[BaseNode] = field(default_factory=list)
    transform: Matrix = field(default_factory=Matrix.identity)
    fill: FillStyle | None = None
    stroke: StrokeStyle | None = None
    text_style: TextStyle | None = None
    view_box: tuple[float, float, float, float] | None = None
    source: Any | None = None
    use_source: Any | None = None

    def iter(self) -> Iterator[BaseNode]:
        yield self
        for child in self.children:
            yield from child.iter()


@dataclass(slots=True)
class GroupNode(BaseNode):
    pass


@dataclass(slots=True)
class PathNode(BaseNode):
    d: str | None = None
    geometry: NormalizedPath | None = None


@dataclass(slots=True)
class RectNode(BaseNode):
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    rx: float = 0.0
    ry: float = 0.0


@dataclass(slots=True)
class CircleNode(BaseNode):
    cx: float = 0.0
    cy: float = 0.0
    r: float = 0.0


@dataclass(slots=True)
class EllipseNode(BaseNode):
    cx: float = 0.0
    cy: float = 0.0
    rx: float = 0.0
    ry: float = 0.0


@dataclass(slots=True)
class LineNode(BaseNode):
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0


@dataclass(slots=True)
class PolyNode(BaseNode):
    points: tuple[float, ...] = ()


@dataclass(slots=True)
class ImageNode(BaseNode):
    href: str | None = None
    x: float = 0.0
    y: float = 0.0
    width: float | None = None
    height: float | None = None
    data: bytes | None = None


@dataclass(slots=True)
class TextNode(BaseNode):
    text_content: str | None = None
    spans: list[TextSpan] = field(default_factory=list)


@dataclass(slots=True)
class GenericNode(BaseNode):
    pass


@dataclass(slots=True)
class PaintServerNode(BaseNode):
    pass


@dataclass(slots=True)
class MaskNode(BaseNode):
    mask_units: str = "objectBoundingBox"
    mask_content_units: str = "userSpaceOnUse"


@dataclass(slots=True)
class ClipPathNode(BaseNode):
    clip_path_units: str = "userSpaceOnUse"


@dataclass(slots=True)
class MarkerNode(BaseNode):
    ref_x: float = 0.0
    ref_y: float = 0.0
    marker_units: str = "strokeWidth"
    orient: str = "auto"


@dataclass(slots=True)
class FilterPrimitive:
    tag: str
    attributes: dict[str, str]
    styles: dict[str, str]
    children: tuple[FilterPrimitive, ...] = ()


@dataclass(slots=True)
class FilterNode(BaseNode):
    primitives: tuple[FilterPrimitive, ...] = ()
    filter_units: str = "objectBoundingBox"
    primitive_units: str = "userSpaceOnUse"


@dataclass(slots=True)
class UseNode(BaseNode):
    href: str | None = None
    x: float = 0.0
    y: float = 0.0
    width: float | None = None
    height: float | None = None


@dataclass(slots=True)
class LinearGradientNode(PaintServerNode):
    gradient: LinearGradient | None = None


@dataclass(slots=True)
class RadialGradientNode(PaintServerNode):
    gradient: RadialGradient | None = None


@dataclass(slots=True)
class PatternNode(PaintServerNode):
    pattern: PatternPaint | None = None


PaintServer = LinearGradient | RadialGradient | PatternPaint


@dataclass(slots=True)
class Tree:
    root: BaseNode
    ids: dict[str, BaseNode] = field(default_factory=dict)
    paint_servers: dict[str, PaintServerNode] = field(default_factory=dict)
    masks: dict[str, MaskNode] = field(default_factory=dict)
    clip_paths: dict[str, ClipPathNode] = field(default_factory=dict)
    markers: dict[str, MarkerNode] = field(default_factory=dict)
    filters: dict[str, FilterNode] = field(default_factory=dict)
    text_nodes: list[TextNode] = field(default_factory=list)

    def node_by_id(self, node_id: str) -> BaseNode | None:
        return self.ids.get(node_id) if node_id else None

    def has_text_nodes(self) -> bool:
        return bool(self.text_nodes)

    def paint_server(self, href: str) -> PaintServerNode | None:
        ref_id = local_url_id(href)
        return self.paint_servers.get(ref_id) if ref_id else None

    def resolve_paint(self, reference: PaintReference) -> PaintServer | None:
        if not reference.href:
            return None
        server_node = self.paint_server(reference.href)
        if server_node is None:
            return None
        visited: set[str] = set()
        if isinstance(server_node, LinearGradientNode) and server_node.gradient:
            return _resolve_linear_gradient_reference(
                server_node,
                self.paint_servers,
                visited,
            )
        if isinstance(server_node, RadialGradientNode) and server_node.gradient:
            return _resolve_radial_gradient_reference(
                server_node,
                self.paint_servers,
                visited,
            )
        if isinstance(server_node, PatternNode) and server_node.pattern:
            return _resolve_pattern_reference(server_node, self.paint_servers, visited)
        return None

    def resolve_mask(self, href: str) -> MaskNode | None:
        ref_id = local_url_id(href)
        return self.masks.get(ref_id) if ref_id else None

    def resolve_clip_path(self, href: str) -> ClipPathNode | None:
        ref_id = local_url_id(href)
        return self.clip_paths.get(ref_id) if ref_id else None

    def resolve_marker(self, href: str) -> MarkerNode | None:
        ref_id = local_url_id(href)
        return self.markers.get(ref_id) if ref_id else None

    def resolve_filter(self, href: str) -> FilterNode | None:
        ref_id = local_url_id(href)
        return self.filters.get(ref_id) if ref_id else None


def propagate_use_source(node: BaseNode, source_elem: Any | None) -> None:
    node.use_source = source_elem
    for child in getattr(node, "children", []) or []:
        propagate_use_source(child, source_elem)


def _resolve_pattern_reference(
    node: PatternNode,
    paint_servers: dict[str, PaintServerNode],
    visited: set[str],
) -> PatternPaint:
    pattern = node.pattern
    assert pattern is not None
    ref_id = local_url_id(pattern.href)
    if ref_id is None:
        return pattern
    if ref_id in visited:
        return pattern
    visited.add(ref_id)
    parent = paint_servers.get(ref_id)
    if not isinstance(parent, PatternNode) or parent.pattern is None:
        return pattern
    parent_pattern = _resolve_pattern_reference(parent, paint_servers, visited)
    return PatternPaint(
        x=pattern.x if "x" in pattern.specified else parent_pattern.x,
        y=pattern.y if "y" in pattern.specified else parent_pattern.y,
        width=pattern.width if "width" in pattern.specified else parent_pattern.width,
        height=pattern.height if "height" in pattern.specified else parent_pattern.height,
        units=pattern.units if "patternUnits" in pattern.specified else parent_pattern.units,
        content_units=(
            pattern.content_units
            if "patternContentUnits" in pattern.specified
            else parent_pattern.content_units
        ),
        transform=(
            pattern.transform
            if "patternTransform" in pattern.specified
            else parent_pattern.transform
        ),
        href=None,
        specified=tuple(sorted(set(parent_pattern.specified) | set(pattern.specified))),
    )


__all__ = [
    "BaseNode",
    "CircleNode",
    "ClipPathNode",
    "EllipseNode",
    "FilterNode",
    "FilterPrimitive",
    "GenericNode",
    "GroupNode",
    "ImageNode",
    "LineNode",
    "LinearGradientNode",
    "MarkerNode",
    "MaskNode",
    "PaintServer",
    "PaintServerNode",
    "PathNode",
    "PatternNode",
    "PolyNode",
    "RadialGradientNode",
    "RectNode",
    "TextNode",
    "TextSpan",
    "Tree",
    "UseNode",
    "propagate_use_source",
]
