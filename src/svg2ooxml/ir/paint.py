"""Paint and stroke representations used by the IR."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .numpy_compat import np


@dataclass(frozen=True)
class SolidPaint:
    rgb: str  # RRGGBB
    opacity: float = 1.0
    theme_color: str | None = None

    def __post_init__(self) -> None:
        if len(self.rgb) != 6:
            raise ValueError("rgb must be 6 hex characters")
        if not (0.0 <= self.opacity <= 1.0):
            object.__setattr__(self, "opacity", max(0.0, min(1.0, self.opacity)))
        if self.theme_color is not None and not self.theme_color.strip():
            raise ValueError("theme_color cannot be blank")


@dataclass(frozen=True)
class GradientStop:
    offset: float
    rgb: str
    opacity: float = 1.0
    theme_color: str | None = None


@dataclass(frozen=True)
class LinearGradientPaint:
    stops: list[GradientStop]
    start: tuple[float, float]
    end: tuple[float, float]
    transform: np.ndarray | None = None
    gradient_id: str | None = None
    # Phase 4: Units & Spread tracking
    gradient_units: str | None = None  # "userSpaceOnUse" or "objectBoundingBox"
    spread_method: str | None = None  # "pad", "reflect", or "repeat"

    def __post_init__(self) -> None:
        if len(self.stops) < 2:
            raise ValueError("gradient requires at least two stops")


@dataclass(frozen=True)
class RadialGradientPaint:
    stops: list[GradientStop]
    center: tuple[float, float]
    radius: float
    focal_point: tuple[float, float] | None = None
    transform: np.ndarray | None = None
    gradient_id: str | None = None
    # Phase 1: Transform detection & telemetry fields
    gradient_transform: Any | None = None  # Original gradient transform (before baking)
    original_transform: Any | None = None  # Shape transform (for telemetry)
    had_transform_flag: bool = False  # Was any transform applied?
    transform_class: Any | None = (
        None  # SVD classification (TransformClass from adapter)
    )
    policy_decision: str | None = (
        None  # "vector_ok" / "vector_warn_mild_anisotropy" / "rasterize_nonuniform"
    )
    # Phase 4: Units & Spread tracking
    gradient_units: str | None = None  # "userSpaceOnUse" or "objectBoundingBox"
    spread_method: str | None = None  # "pad", "reflect", or "repeat"


@dataclass(frozen=True)
class PatternPaint:
    pattern_id: str
    transform: np.ndarray | None = None
    preset: str | None = None
    foreground: str | None = None
    background: str | None = None
    background_opacity: float = 1.0
    foreground_theme_color: str | None = None
    background_theme_color: str | None = None
    # Rasterized tile image for non-preset patterns
    tile_image: bytes | None = None
    tile_width_px: int | None = None
    tile_height_px: int | None = None
    # Populated by shape_renderer after media registration
    tile_relationship_id: str | None = None


@dataclass(frozen=True)
class GradientPaintRef:
    gradient_id: str
    gradient_type: str = "auto"
    transform: np.ndarray | None = None


Paint = (
    SolidPaint
    | LinearGradientPaint
    | RadialGradientPaint
    | PatternPaint
    | GradientPaintRef
    | None
)


class StrokeJoin(Enum):
    MITER = "miter"
    ROUND = "round"
    BEVEL = "bevel"


class StrokeCap(Enum):
    BUTT = "butt"
    ROUND = "round"
    SQUARE = "square"


@dataclass(frozen=True)
class Stroke:
    paint: Paint
    width: float
    join: StrokeJoin = StrokeJoin.MITER
    cap: StrokeCap = StrokeCap.BUTT
    miter_limit: float = 4.0
    dash_array: list[float] | None = None
    dash_offset: float = 0.0
    opacity: float = 1.0

    def __post_init__(self) -> None:
        if self.width < 0:
            raise ValueError("stroke width must be non-negative")
        if not (0.0 <= self.opacity <= 1.0):
            object.__setattr__(self, "opacity", max(0.0, min(1.0, self.opacity)))

    @property
    def is_dashed(self) -> bool:
        return bool(self.dash_array)

    @property
    def complexity_score(self) -> int:
        score = 0
        if self.is_dashed:
            score += 2
        if self.join == StrokeJoin.MITER and self.miter_limit > 10:
            score += 1
        if isinstance(self.paint, (LinearGradientPaint, RadialGradientPaint)):
            score += 1
        return score


__all__ = [
    "SolidPaint",
    "GradientStop",
    "LinearGradientPaint",
    "RadialGradientPaint",
    "PatternPaint",
    "GradientPaintRef",
    "Paint",
    "Stroke",
    "StrokeJoin",
    "StrokeCap",
]
