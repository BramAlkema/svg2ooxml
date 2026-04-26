"""Simplified usvg::Tree representation with typed nodes."""

from __future__ import annotations

import copy
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import (
    TYPE_CHECKING,
    Any,
)

from svg2ooxml.common.conversions.transforms import parse_numeric_list

from .geometry.matrix import Matrix, matrix_from_commands
from .painting.gradients import (
    GradientStop,
    LinearGradient,
    PatternPaint,
    RadialGradient,
)
from .painting.paint import (
    FillStyle,
    PaintReference,
    StrokeStyle,
    TextStyle,
    parse_color,
    resolve_fill,
    resolve_stroke,
    resolve_text_style,
)
from .parser.options import Options
from .parser.presentation import Presentation, collect_presentation, parse_transform
from .parser.tree import SvgDocument, SvgNode

if TYPE_CHECKING:  # pragma: no cover
    from .geometry.path_normalizer import NormalizedPath

SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def _strip_namespace(tag: Any) -> str:
    tag_str = str(tag)
    if tag_str.startswith("{" + SVG_NAMESPACE + "}"):
        return tag_str[len(SVG_NAMESPACE) + 2 :]
    return tag_str


def _propagate_use_source(node: BaseNode, source_elem: Any | None) -> None:
    node.use_source = source_elem
    for child in getattr(node, "children", []) or []:
        _propagate_use_source(child, source_elem)


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
    width: str | None = None
    height: str | None = None
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
        if href.startswith("#"):
            return self.paint_servers.get(href[1:])
        return None

    def resolve_paint(self, reference: PaintReference) -> PaintServer | None:
        if not reference.href:
            return None
        server_node = self.paint_server(reference.href)
        if server_node is None:
            return None
        visited: set[str] = set()
        if isinstance(server_node, LinearGradientNode) and server_node.gradient:
            return _resolve_linear_gradient_reference(server_node, self.paint_servers, visited)
        if isinstance(server_node, RadialGradientNode) and server_node.gradient:
            return _resolve_radial_gradient_reference(server_node, self.paint_servers, visited)
        if isinstance(server_node, PatternNode) and server_node.pattern:
            return _resolve_pattern_reference(server_node, self.paint_servers, visited)
        return None

    def resolve_mask(self, href: str) -> MaskNode | None:
        if not href:
            return None
        if href.startswith("#"):
            return self.masks.get(href[1:])
        return None

    def resolve_clip_path(self, href: str) -> ClipPathNode | None:
        if not href:
            return None
        if href.startswith("#"):
            return self.clip_paths.get(href[1:])
        return None

    def resolve_marker(self, href: str) -> MarkerNode | None:
        if not href:
            return None
        if href.startswith("#"):
            return self.markers.get(href[1:])
        return None

    def resolve_filter(self, href: str) -> FilterNode | None:
        if not href:
            return None
        if href.startswith("#"):
            return self.filters.get(href[1:])
        return None


def _gather_text(node: SvgNode) -> str | None:
    parts: list[str] = []

    def walk(current: SvgNode) -> None:
        if current.text:
            parts.append(current.text.strip())
        for child in current.children:
            walk(child)
            if child.tail:
                parts.append(child.tail.strip())

    walk(node)
    content = " ".join(filter(None, parts))
    return content or None


def _extract_href(attributes: dict[str, str]) -> str | None:
    for key in ("href", "{http://www.w3.org/1999/xlink}href"):
        if key in attributes:
            return attributes[key]
    return None


def _parse_number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        if value.endswith("%"):
            return float(value[:-1]) / 100.0
        return float(value)
    except ValueError:
        return default


def _parse_offset(value: str | None) -> float:
    offset = _parse_number(value, 0.0)
    if offset < 0.0:
        return 0.0
    if offset > 1.0:
        return 1.0
    return offset


def _parse_stop(node: SvgNode) -> GradientStop | None:
    offset = _parse_offset(node.attributes.get("offset"))
    color_value = node.styles.get("stop-color") or node.attributes.get("stop-color")
    opacity_value = node.styles.get("stop-opacity") or node.attributes.get("stop-opacity")
    opacity = _parse_number(opacity_value, 1.0)
    color = parse_color(color_value or "#000000", opacity)
    if color is None:
        color = parse_color("#000000", opacity)  # guaranteed fallback
    return GradientStop(offset=offset, color=color)


def _optional_number(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        if value.endswith("%"):
            return float(value[:-1]) / 100.0
        return float(value)
    except ValueError:
        return None


def _parse_points(raw: str) -> tuple[float, ...]:
    if not raw:
        return ()
    return tuple(parse_numeric_list(raw))


def _parse_view_box(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    numbers = _parse_points(raw)
    if len(numbers) != 4:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _parse_linear_gradient(node: SvgNode) -> LinearGradient:
    attributes = node.attributes
    transform_matrix = matrix_from_commands(parse_transform(attributes.get("gradientTransform")))
    stops_list: list[GradientStop] = []
    for child in node.children:
        if _strip_namespace(child.tag) != "stop":
            continue
        stop = _parse_stop(child)
        if stop:
            stops_list.append(stop)
    stops_list.sort(key=lambda s: s.offset)
    href = _extract_href(attributes)
    specified = tuple(
        key
        for key in ("x1", "y1", "x2", "y2", "gradientUnits", "spreadMethod", "gradientTransform")
        if key in attributes
    )
    return LinearGradient(
        x1=_parse_number(attributes.get("x1"), 0.0),
        y1=_parse_number(attributes.get("y1"), 0.0),
        x2=_parse_number(attributes.get("x2"), 1.0),
        y2=_parse_number(attributes.get("y2"), 0.0),
        units=attributes.get("gradientUnits") or "objectBoundingBox",
        spread_method=attributes.get("spreadMethod") or "pad",
        transform=transform_matrix,
        stops=tuple(stops_list),
        href=href,
        specified=specified,
    )


def _parse_radial_gradient(node: SvgNode) -> RadialGradient:
    attributes = node.attributes
    transform_matrix = matrix_from_commands(parse_transform(attributes.get("gradientTransform")))
    stops_list: list[GradientStop] = []
    for child in node.children:
        if _strip_namespace(child.tag) != "stop":
            continue
        stop = _parse_stop(child)
        if stop:
            stops_list.append(stop)
    stops_list.sort(key=lambda s: s.offset)
    href = _extract_href(attributes)
    specified = tuple(
        key
        for key in ("cx", "cy", "r", "fx", "fy", "gradientUnits", "spreadMethod", "gradientTransform")
        if key in attributes
    )
    default_cx = _parse_number(attributes.get("cx"), 0.5)
    default_cy = _parse_number(attributes.get("cy"), 0.5)
    return RadialGradient(
        cx=default_cx,
        cy=default_cy,
        r=_parse_number(attributes.get("r"), 0.5),
        fx=_parse_number(attributes.get("fx"), default_cx),
        fy=_parse_number(attributes.get("fy"), default_cy),
        units=attributes.get("gradientUnits") or "objectBoundingBox",
        spread_method=attributes.get("spreadMethod") or "pad",
        transform=transform_matrix,
        stops=tuple(stops_list),
        href=href,
        specified=specified,
    )


def _parse_pattern(node: SvgNode) -> PatternPaint:
    attributes = node.attributes
    transform_matrix = matrix_from_commands(parse_transform(attributes.get("patternTransform")))
    href = _extract_href(attributes)
    specified = tuple(
        key
        for key in ("x", "y", "width", "height", "patternUnits", "patternContentUnits", "patternTransform")
        if key in attributes
    )
    return PatternPaint(
        x=_parse_number(attributes.get("x"), 0.0),
        y=_parse_number(attributes.get("y"), 0.0),
        width=_parse_number(attributes.get("width"), 0.0),
        height=_parse_number(attributes.get("height"), 0.0),
        units=attributes.get("patternUnits") or "objectBoundingBox",
        content_units=attributes.get("patternContentUnits") or "userSpaceOnUse",
        transform=transform_matrix,
        href=href,
        specified=specified,
    )


def _resolve_linear_gradient_reference(
    node: LinearGradientNode,
    paint_servers: dict[str, PaintServerNode],
    visited: set[str],
) -> LinearGradient:
    gradient = node.gradient
    assert gradient is not None
    href = gradient.href
    if not href or not href.startswith("#"):
        return gradient
    ref_id = href[1:]
    if ref_id in visited:
        return gradient
    visited.add(ref_id)
    parent = paint_servers.get(ref_id)
    if not isinstance(parent, LinearGradientNode) or parent.gradient is None:
        return gradient
    parent_gradient = _resolve_linear_gradient_reference(parent, paint_servers, visited)
    stops = gradient.stops if gradient.stops else parent_gradient.stops
    return LinearGradient(
        x1=gradient.x1 if "x1" in gradient.specified else parent_gradient.x1,
        y1=gradient.y1 if "y1" in gradient.specified else parent_gradient.y1,
        x2=gradient.x2 if "x2" in gradient.specified else parent_gradient.x2,
        y2=gradient.y2 if "y2" in gradient.specified else parent_gradient.y2,
        units=gradient.units if "gradientUnits" in gradient.specified else parent_gradient.units,
        spread_method=gradient.spread_method if "spreadMethod" in gradient.specified else parent_gradient.spread_method,
        transform=gradient.transform if "gradientTransform" in gradient.specified else parent_gradient.transform,
        stops=stops,
        href=None,
        specified=tuple(sorted(set(parent_gradient.specified) | set(gradient.specified))),
    )


def _resolve_radial_gradient_reference(
    node: RadialGradientNode,
    paint_servers: dict[str, PaintServerNode],
    visited: set[str],
) -> RadialGradient:
    gradient = node.gradient
    assert gradient is not None
    href = gradient.href
    if not href or not href.startswith("#"):
        return gradient
    ref_id = href[1:]
    if ref_id in visited:
        return gradient
    visited.add(ref_id)
    parent = paint_servers.get(ref_id)
    if not isinstance(parent, RadialGradientNode) or parent.gradient is None:
        return gradient
    parent_gradient = _resolve_radial_gradient_reference(parent, paint_servers, visited)
    stops = gradient.stops if gradient.stops else parent_gradient.stops
    return RadialGradient(
        cx=gradient.cx if "cx" in gradient.specified else parent_gradient.cx,
        cy=gradient.cy if "cy" in gradient.specified else parent_gradient.cy,
        r=gradient.r if "r" in gradient.specified else parent_gradient.r,
        fx=gradient.fx if "fx" in gradient.specified else parent_gradient.fx,
        fy=gradient.fy if "fy" in gradient.specified else parent_gradient.fy,
        units=gradient.units if "gradientUnits" in gradient.specified else parent_gradient.units,
        spread_method=gradient.spread_method if "spreadMethod" in gradient.specified else parent_gradient.spread_method,
        transform=gradient.transform if "gradientTransform" in gradient.specified else parent_gradient.transform,
        stops=stops,
        href=None,
        specified=tuple(sorted(set(parent_gradient.specified) | set(gradient.specified))),
    )


def _resolve_pattern_reference(
    node: PatternNode,
    paint_servers: dict[str, PaintServerNode],
    visited: set[str],
) -> PatternPaint:
    pattern = node.pattern
    assert pattern is not None
    href = pattern.href
    if not href or not href.startswith("#"):
        return pattern
    ref_id = href[1:]
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
        content_units=pattern.content_units if "patternContentUnits" in pattern.specified else parent_pattern.content_units,
        transform=pattern.transform if "patternTransform" in pattern.specified else parent_pattern.transform,
        href=None,
        specified=tuple(sorted(set(parent_pattern.specified) | set(pattern.specified))),
    )


def _convert_node(node: SvgNode, parent: BaseNode | None = None, options: Options | None = None) -> BaseNode:
    presentation = collect_presentation(node)
    attributes = dict(node.attributes)
    styles = dict(node.styles)
    tag_local = _strip_namespace(node.tag)
    node_id = attributes.get("id")

    transform_matrix = matrix_from_commands(presentation.transform)
    raw_fill = styles.get("fill") if "fill" in styles else attributes.get("fill")
    explicit_no_fill = bool(raw_fill) and raw_fill.strip().lower() in {"none", "transparent"}
    fill_style = resolve_fill(
        presentation.fill,
        presentation.fill_opacity,
        presentation.opacity,
    )
    if fill_style.color is None and fill_style.reference is None and not explicit_no_fill:
        fill_style = None

    raw_stroke = styles.get("stroke") if "stroke" in styles else attributes.get("stroke")
    explicit_no_stroke = bool(raw_stroke) and raw_stroke.strip().lower() in {"none", "transparent"}
    stroke_style = resolve_stroke(
        presentation.stroke,
        presentation.stroke_width,
        presentation.stroke_opacity,
        presentation.opacity,
        dasharray=presentation.stroke_dasharray,
        dashoffset=presentation.stroke_dashoffset,
        linecap=presentation.stroke_linecap,
        linejoin=presentation.stroke_linejoin,
        miterlimit=presentation.stroke_miterlimit,
    )
    if (
        stroke_style.color is None
        and stroke_style.reference is None
        and stroke_style.width is None
        and not explicit_no_stroke
    ):
        stroke_style = None
    resolved_text_style = resolve_text_style(
        presentation.font_family,
        presentation.font_size,
        presentation.font_style,
        presentation.font_weight,
        text_decoration=getattr(presentation, "text_decoration", None),
        letter_spacing=getattr(presentation, "letter_spacing", None),
    )
    if (
        not resolved_text_style.font_families
        and resolved_text_style.font_size is None
        and resolved_text_style.font_style is None
        and resolved_text_style.font_weight is None
    ):
        text_style = None
    else:
        text_style = resolved_text_style

    view_box = _parse_view_box(attributes.get("viewBox"))

    base_kwargs = {
        "tag": tag_local,
        "id": node_id,
        "presentation": presentation,
        "attributes": attributes,
        "styles": styles,
        "transform": transform_matrix,
        "fill": _inherit_fill(fill_style, parent),
        "stroke": _inherit_stroke(stroke_style, parent),
        "text_style": _inherit_text(text_style, parent),
        "view_box": view_box,
        "source": getattr(node, "source", None),
    }

    if tag_local in {"g", "svg"}:
        group = GroupNode(**base_kwargs)
        group.children = [_convert_node(child, group, options) for child in node.children]
        return group
    if tag_local == "path":
        path_node = PathNode(d=attributes.get("d"), **base_kwargs)
        path_node.children = [_convert_node(child, path_node, options) for child in node.children]
        from .geometry.path_normalizer import (
            normalize_path,  # local import to avoid cycle
        )

        stroke_width = path_node.stroke.width if path_node.stroke else None
        path_node.geometry = normalize_path(path_node.d, path_node.transform, stroke_width)
        return path_node
    if tag_local == "rect":
        rect = RectNode(
            x=_parse_number(attributes.get("x"), 0.0),
            y=_parse_number(attributes.get("y"), 0.0),
            width=_parse_number(attributes.get("width"), 0.0),
            height=_parse_number(attributes.get("height"), 0.0),
            rx=_parse_number(attributes.get("rx"), 0.0),
            ry=_parse_number(attributes.get("ry"), 0.0),
            **base_kwargs,
        )
        rect.children = [_convert_node(child, rect, options) for child in node.children]
        return rect
    if tag_local == "circle":
        circle = CircleNode(
            cx=_parse_number(attributes.get("cx"), 0.0),
            cy=_parse_number(attributes.get("cy"), 0.0),
            r=_parse_number(attributes.get("r"), 0.0),
            **base_kwargs,
        )
        circle.children = [_convert_node(child, circle, options) for child in node.children]
        return circle
    if tag_local == "ellipse":
        ellipse = EllipseNode(
            cx=_parse_number(attributes.get("cx"), 0.0),
            cy=_parse_number(attributes.get("cy"), 0.0),
            rx=_parse_number(attributes.get("rx"), 0.0),
            ry=_parse_number(attributes.get("ry"), 0.0),
            **base_kwargs,
        )
        ellipse.children = [_convert_node(child, ellipse, options) for child in node.children]
        return ellipse
    if tag_local == "line":
        line = LineNode(
            x1=_parse_number(attributes.get("x1"), 0.0),
            y1=_parse_number(attributes.get("y1"), 0.0),
            x2=_parse_number(attributes.get("x2"), 0.0),
            y2=_parse_number(attributes.get("y2"), 0.0),
            **base_kwargs,
        )
        line.children = [_convert_node(child, line, options) for child in node.children]
        return line
    if tag_local in {"polyline", "polygon"}:
        points = _parse_points(attributes.get("points", ""))
        poly = PolyNode(points=points, **base_kwargs)
        poly.children = [_convert_node(child, poly, options) for child in node.children]
        return poly
    if tag_local == "linearGradient":
        gradient = _parse_linear_gradient(node)
        base_kwargs["fill"] = None
        base_kwargs["stroke"] = None
        base_kwargs["text_style"] = None
        node_obj = LinearGradientNode(gradient=gradient, **base_kwargs)
        node_obj.children = [_convert_node(child, node_obj, options) for child in node.children]
        return node_obj
    if tag_local == "radialGradient":
        gradient = _parse_radial_gradient(node)
        base_kwargs["fill"] = None
        base_kwargs["stroke"] = None
        base_kwargs["text_style"] = None
        node_obj = RadialGradientNode(gradient=gradient, **base_kwargs)
        node_obj.children = [_convert_node(child, node_obj, options) for child in node.children]
        return node_obj
    if tag_local == "pattern":
        pattern = _parse_pattern(node)
        base_kwargs["fill"] = None
        base_kwargs["stroke"] = None
        base_kwargs["text_style"] = None
        node_obj = PatternNode(pattern=pattern, **base_kwargs)
        node_obj.children = [_convert_node(child, node_obj, options) for child in node.children]
        return node_obj
    if tag_local == "image":
        href = _extract_href(attributes)
        image_data = None
        if href and options:
            image_data = options.image_href_resolver.resolve_data(href)
            if image_data is None:
                path = options.image_href_resolver.resolve_file(href)
                if path:
                    try:
                        image_data = path.read_bytes()
                    except Exception:
                        pass

        image = ImageNode(
            href=href,
            width=attributes.get("width"),
            height=attributes.get("height"),
            data=image_data,
            **base_kwargs,
        )
        image.children = [_convert_node(child, image, options) for child in node.children]
        return image
    if tag_local == "text":
        text_node = TextNode(text_content=_gather_text(node), **base_kwargs)
        text_node.children = [_convert_node(child, text_node, options) for child in node.children]
        return text_node
    if tag_local == "mask":
        mask = MaskNode(
            mask_units=attributes.get("maskUnits", "objectBoundingBox"),
            mask_content_units=attributes.get("maskContentUnits", "userSpaceOnUse"),
            **base_kwargs,
        )
        mask.children = [_convert_node(child, mask, options) for child in node.children]
        return mask
    if tag_local == "clipPath":
        clip = ClipPathNode(
            clip_path_units=attributes.get("clipPathUnits", "userSpaceOnUse"),
            **base_kwargs,
        )
        clip.children = [_convert_node(child, clip, options) for child in node.children]
        return clip
    if tag_local == "marker":
        marker = MarkerNode(
            ref_x=_parse_number(attributes.get("refX"), 0.0),
            ref_y=_parse_number(attributes.get("refY"), 0.0),
            marker_units=attributes.get("markerUnits", "strokeWidth"),
            orient=attributes.get("orient", "auto"),
            **base_kwargs,
        )
        marker.children = [_convert_node(child, marker, options) for child in node.children]
        return marker
    if tag_local == "filter":
        primitives_list = [_build_filter_primitive(child) for child in node.children]
        return FilterNode(
            primitives=tuple(primitives_list),
            filter_units=attributes.get("filterUnits", "objectBoundingBox"),
            primitive_units=attributes.get("primitiveUnits", "userSpaceOnUse"),
            **base_kwargs,
        )
    if tag_local == "use":
        use_node = UseNode(
            href=_extract_href(attributes),
            x=_parse_number(attributes.get("x"), 0.0),
            y=_parse_number(attributes.get("y"), 0.0),
            width=_optional_number(attributes.get("width")),
            height=_optional_number(attributes.get("height")),
            **base_kwargs,
        )
        use_node.children = [_convert_node(child, use_node, options) for child in node.children]
        return use_node

    generic = GenericNode(**base_kwargs)
    generic.children = [_convert_node(child, generic, options) for child in node.children]
    return generic


def _build_filter_primitive(node) -> FilterPrimitive:
    child_tag = _strip_namespace(getattr(node, "tag", "") or "")
    children = tuple(_build_filter_primitive(child) for child in getattr(node, "children", []) or [])
    return FilterPrimitive(
        tag=child_tag,
        attributes=dict(getattr(node, "attributes", {}) or {}),
        styles=dict(getattr(node, "styles", {}) or {}),
        children=children,
    )


def _collect_ids(node: BaseNode, ids: dict[str, BaseNode]) -> None:
    if node.id:
        ids[node.id] = node
    for child in node.children:
        _collect_ids(child, ids)


def _clear_ids(node: BaseNode) -> None:
    node.id = None
    for child in node.children:
        _clear_ids(child)


def _expand_use_nodes(root: BaseNode, ids: dict[str, BaseNode]) -> None:
    stack: list[tuple[BaseNode, tuple[str, ...]]] = [(root, ())]
    while stack:
        current, active_refs = stack.pop()
        for index, child in enumerate(list(current.children)):
            if isinstance(child, UseNode) and child.href:
                ref_id = child.href.lstrip("#")
                if not ref_id:
                    continue
                if ref_id in active_refs:
                    # Prevent infinite expansion for recursive <use> chains.
                    continue
                referenced = ids.get(ref_id)
                if referenced is None:
                    continue
                clone = copy.deepcopy(referenced)
                _clear_ids(clone)
                use_transform = child.transform if child.transform is not None else Matrix.identity()
                translation = Matrix(1.0, 0.0, 0.0, 1.0, child.x, child.y)
                clone.transform = use_transform.multiply(translation).multiply(clone.transform)
                _propagate_use_source(clone, getattr(child, "source", None))

                # Apply <use> element's presentation attributes to cloned content
                # Per SVG spec, <use> element attributes override referenced element

                # Update presentation attributes first
                presentation_updated = False
                if hasattr(child, 'presentation') and child.presentation and hasattr(clone, 'presentation') and clone.presentation:
                    from dataclasses import replace
                    new_presentation = clone.presentation
                    if child.presentation.stroke is not None:
                        new_presentation = replace(new_presentation, stroke=child.presentation.stroke)
                        presentation_updated = True
                    if child.presentation.stroke_width is not None:
                        new_presentation = replace(new_presentation, stroke_width=child.presentation.stroke_width)
                        presentation_updated = True
                    if child.presentation.stroke_opacity is not None:
                        new_presentation = replace(new_presentation, stroke_opacity=child.presentation.stroke_opacity)
                        presentation_updated = True
                    if presentation_updated:
                        clone.presentation = new_presentation

                # Re-resolve stroke/fill from updated presentation
                if presentation_updated and hasattr(clone, 'presentation') and clone.presentation:
                    stroke_style = resolve_stroke(
                        clone.presentation.stroke,
                        clone.presentation.stroke_width,
                        clone.presentation.stroke_opacity,
                        clone.presentation.opacity,
                        dasharray=clone.presentation.stroke_dasharray,
                        dashoffset=clone.presentation.stroke_dashoffset,
                        linecap=clone.presentation.stroke_linecap,
                        linejoin=clone.presentation.stroke_linejoin,
                        miterlimit=clone.presentation.stroke_miterlimit,
                    )
                    if not (
                        stroke_style.color is None
                        and stroke_style.reference is None
                        and stroke_style.width is None
                    ):
                        clone.stroke = stroke_style

                # Also apply direct attributes
                if child.fill is not None and clone.fill is None:
                    clone.fill = child.fill
                if child.text_style is not None and clone.text_style is None:
                    clone.text_style = child.text_style

                current.children[index] = clone
                if child.id:
                    ids[child.id] = clone
                stack.append((clone, (*active_refs, ref_id)))
            else:
                stack.append((child, active_refs))


def build_tree(document: SvgDocument, options: Options | None = None) -> Tree:
    root = _convert_node(document.root, None, options)
    ids: dict[str, BaseNode] = {}
    _collect_ids(root, ids)
    _expand_use_nodes(root, ids)
    paint_servers: dict[str, PaintServerNode] = {}
    masks: dict[str, MaskNode] = {}
    clip_paths: dict[str, ClipPathNode] = {}
    markers: dict[str, MarkerNode] = {}
    filters: dict[str, FilterNode] = {}
    text_nodes: list[TextNode] = []
    for node_id, node in ids.items():
        if isinstance(node, PaintServerNode):
            paint_servers[node_id] = node
        elif isinstance(node, MaskNode):
            masks[node_id] = node
        elif isinstance(node, ClipPathNode):
            clip_paths[node_id] = node
        elif isinstance(node, MarkerNode):
            markers[node_id] = node
        elif isinstance(node, FilterNode):
            filters[node_id] = node
        if isinstance(node, TextNode):
            text_nodes.append(node)
    tree = Tree(
        root=root,
        ids=ids,
        paint_servers=paint_servers,
        masks=masks,
        clip_paths=clip_paths,
        markers=markers,
        filters=filters,
        text_nodes=text_nodes,
    )
    from .text.layout import build_text_layout
    build_text_layout(tree)
    return tree
PaintServer = LinearGradient | RadialGradient | PatternPaint


def _inherit_fill(fill: FillStyle | None, parent: BaseNode | None) -> FillStyle | None:
    if fill is not None:
        return fill
    if parent and parent.fill is not None:
        return replace(parent.fill)
    return None


def _inherit_stroke(stroke: StrokeStyle | None, parent: BaseNode | None) -> StrokeStyle | None:
    if stroke is not None:
        return stroke
    if parent and parent.stroke is not None:
        return replace(parent.stroke)
    return None


def _inherit_text(text_style: TextStyle | None, parent: BaseNode | None) -> TextStyle | None:
    parent_style = parent.text_style if parent and parent.text_style is not None else None
    if text_style is None:
        return replace(parent_style) if parent_style is not None else None
    if parent_style is None:
        return text_style
    return TextStyle(
        font_families=text_style.font_families or parent_style.font_families,
        font_size=text_style.font_size if text_style.font_size is not None else parent_style.font_size,
        font_style=text_style.font_style or parent_style.font_style,
        font_weight=text_style.font_weight or parent_style.font_weight,
        text_decoration=text_style.text_decoration or parent_style.text_decoration,
        letter_spacing=text_style.letter_spacing if text_style.letter_spacing is not None else parent_style.letter_spacing,
    )
@dataclass(slots=True)
class TextSpan:
    text: str
    x: float
    y: float
