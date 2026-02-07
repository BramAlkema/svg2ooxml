"""DrawingML effect representations for the IR."""

from __future__ import annotations

from dataclasses import dataclass

from svg2ooxml.common.conversions.angles import degrees_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt

EMU_PER_POINT = 12700  # 1pt == 12700 EMU


@dataclass(frozen=True)
class Effect:
    """Base effect type."""


@dataclass(frozen=True)
class BlurEffect(Effect):
    radius: float  # points

    def to_emu(self) -> int:
        return int(self.radius * EMU_PER_POINT)


@dataclass(frozen=True)
class ShadowEffect(Effect):
    blur_radius: float
    distance: float
    angle: float
    color: str = "000000"
    alpha: float = 0.5

    def to_emu(self) -> tuple[int, int]:
        return (
            int(self.blur_radius * EMU_PER_POINT),
            int(self.distance * EMU_PER_POINT),
        )

    def to_direction_emu(self) -> int:
        return degrees_to_ppt(self.angle % 360)

    def to_alpha_val(self) -> int:
        return opacity_to_ppt(self.alpha)


@dataclass(frozen=True)
class GlowEffect(Effect):
    radius: float
    color: str = "FFFFFF"

    def to_emu(self) -> int:
        return int(self.radius * EMU_PER_POINT)


@dataclass(frozen=True)
class SoftEdgeEffect(Effect):
    radius: float

    def to_emu(self) -> int:
        return int(self.radius * EMU_PER_POINT)


@dataclass(frozen=True)
class ReflectionEffect(Effect):
    blur_radius: float = 3.0
    start_alpha: float = 0.5
    end_alpha: float = 0.0
    distance: float = 0.0

    def to_emu(self) -> tuple[int, int]:
        return (
            int(self.blur_radius * EMU_PER_POINT),
            int(self.distance * EMU_PER_POINT),
        )

    def to_alpha_vals(self) -> tuple[int, int]:
        return (
            opacity_to_ppt(self.start_alpha),
            opacity_to_ppt(self.end_alpha),
        )


@dataclass(frozen=True)
class CustomEffect(Effect):
    drawingml: str


__all__ = [
    "Effect",
    "BlurEffect",
    "ShadowEffect",
    "GlowEffect",
    "SoftEdgeEffect",
    "ReflectionEffect",
    "CustomEffect",
]
