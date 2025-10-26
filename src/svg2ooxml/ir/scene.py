"""Scene graph primitives for svg2ooxml IR."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Mapping, Union

from .effects import Effect
from .geometry import Point, Rect, SegmentType
from .numpy_compat import np
from .paint import Paint, Stroke
from .shapes import Circle, Ellipse, Rectangle, Line, Polyline, Polygon
from .text import TextFrame


class ClipStrategy(Enum):
    NATIVE = "native"
    BOOLEAN = "boolean"
    EMF = "emf"


class MaskMode(Enum):
    """Enumerate supported SVG mask composition modes."""

    LUMINANCE = "luminance"
    ALPHA = "alpha"
    AUTO = "auto"


@dataclass(frozen=True)
class ClipRef:
    clip_id: str
    path_segments: tuple[SegmentType, ...] | None = None
    bounding_box: Rect | None = None
    clip_rule: str | None = None
    strategy: ClipStrategy = ClipStrategy.NATIVE
    transform: Any | None = None
    primitives: tuple[dict[str, Any], ...] = field(default_factory=tuple, compare=False)
    custom_geometry_xml: str | None = field(default=None, compare=False)
    custom_geometry_bounds: Rect | None = field(default=None, compare=False)
    custom_geometry_size: tuple[int, int] | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.clip_id:
            raise ValueError("clip_id cannot be empty")


@dataclass(frozen=True)
class MaskDefinition:
    mask_id: str
    mask_type: str | None = None
    mode: MaskMode = MaskMode.AUTO
    mask_units: str | None = None
    mask_content_units: str | None = None
    region: Rect | None = None
    opacity: float | None = None
    bounding_box: Rect | None = None
    segments: tuple[SegmentType, ...] = ()
    content_xml: tuple[str, ...] = ()
    transform: Any | None = None
    primitives: tuple[dict[str, Any], ...] = field(default_factory=tuple, compare=False)
    raw_region: Mapping[str, Any] = field(default_factory=dict, compare=False)
    policy_hints: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.mask_id:
            raise ValueError("mask_id cannot be empty")


@dataclass(frozen=True)
class MaskRef:
    mask_id: str
    definition: MaskDefinition | None = None
    target_bounds: Rect | None = None
    target_opacity: float | None = None
    policy_hints: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.mask_id:
            raise ValueError("mask_id cannot be empty")


@dataclass(frozen=True)
class MaskInstance:
    """Bundle mask reference metadata with resolved usage context."""

    mask: MaskRef
    bounds: Rect | None = None
    opacity: float | None = None
    diagnostics: tuple[str, ...] = ()
    policy_hints: Mapping[str, Any] = field(default_factory=dict, compare=False)

    @property
    def mask_id(self) -> str:
        return self.mask.mask_id

    @property
    def definition(self) -> MaskDefinition | None:
        return self.mask.definition

    @property
    def mode(self) -> MaskMode | None:
        definition = self.mask.definition
        return definition.mode if definition else None


@dataclass(frozen=True)
class Path:
    segments: list[SegmentType]
    fill: Paint = None
    stroke: Stroke | None = None
    clip: ClipRef | None = None
    mask: MaskRef | None = None
    mask_instance: MaskInstance | None = None
    opacity: float = 1.0
    transform: np.ndarray | None = None
    effects: list[Effect] = field(default_factory=list, compare=False)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("path requires at least one segment")
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("opacity must be 0.0‐1.0")

    @property
    def bbox(self) -> Rect:
        xs, ys = [], []
        for segment in self.segments:
            for attr in ("start", "end", "control1", "control2"):
                point = getattr(segment, attr, None)
                if point is not None:
                    xs.append(point.x)
                    ys.append(point.y)
        if not xs or not ys:
            return Rect(0, 0, 0, 0)
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)

    @property
    def is_closed(self) -> bool:
        if len(self.segments) < 2:
            return False
        first_point = getattr(self.segments[0], "start", None)
        last_point = getattr(self.segments[-1], "end", None)
        if not first_point or not last_point:
            return False
        dx = abs(first_point.x - last_point.x)
        dy = abs(first_point.y - last_point.y)
        return dx < 0.1 and dy < 0.1

    @property
    def complexity_score(self) -> int:
        score = len(self.segments)
        if self.stroke:
            score += self.stroke.complexity_score
        if self.clip:
            score += 3
        if self.mask:
            score += 4
        if self.effects:
            score += len(self.effects) * 2
        if self.fill and hasattr(self.fill, "stops"):
            score += len(getattr(self.fill, "stops", []))
        return score

    @property
    def has_complex_features(self) -> bool:
        return (
            self.complexity_score > 100
            or (self.stroke and self.stroke.is_dashed)
            or (self.clip and self.clip.strategy == ClipStrategy.EMF)
            or self.mask is not None
        )


@dataclass(frozen=True)
class Group:
    children: list[
        Union["Path", Circle, Ellipse, Rectangle, Line, Polyline, Polygon, TextFrame, "Group", "Image"]
    ]
    clip: ClipRef | None = None
    mask: MaskRef | None = None
    mask_instance: MaskInstance | None = None
    opacity: float = 1.0
    transform: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("group opacity must be 0.0‐1.0")

    @property
    def bbox(self) -> Rect:
        boxes = [child.bbox for child in self.children if hasattr(child, "bbox")]
        if not boxes:
            return Rect(0, 0, 0, 0)
        min_x = min(box.x for box in boxes)
        min_y = min(box.y for box in boxes)
        max_x = max(box.x + box.width for box in boxes)
        max_y = max(box.y + box.height for box in boxes)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)

    @property
    def is_leaf_group(self) -> bool:
        return all(not isinstance(child, Group) for child in self.children)

    @property
    def total_element_count(self) -> int:
        count = len(self.children)
        for child in self.children:
            if isinstance(child, Group):
                count += child.total_element_count
        return count


@dataclass(frozen=True)
class Image:
    origin: Point
    size: Rect
    data: bytes | None
    format: Literal["png", "jpg", "gif", "svg", "emf"]
    href: str | None = None
    clip: ClipRef | None = None
    mask: MaskRef | None = None
    mask_instance: MaskInstance | None = None
    opacity: float = 1.0
    transform: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("image opacity must be 0.0‐1.0")
        if not self.data and not self.href:
            raise ValueError("image requires data or href")

    @property
    def bbox(self) -> Rect:
        return Rect(self.origin.x, self.origin.y, self.size.width, self.size.height)


IRElement = Union[Path, Circle, Ellipse, Rectangle, TextFrame, Group, Image]
SceneGraph = list[IRElement]


@dataclass
class Scene:
    elements: SceneGraph = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ClipStrategy",
    "ClipRef",
    "MaskDefinition",
    "MaskRef",
    "MaskMode",
    "MaskInstance",
    "Path",
    "Group",
    "Image",
    "IRElement",
    "SceneGraph",
    "Scene",
]
