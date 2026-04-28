"""Result types for DrawingML rasterization."""

from __future__ import annotations

from dataclasses import dataclass

from svg2ooxml.ir.geometry import Rect


@dataclass(frozen=True)
class RasterResult:
    data: bytes
    width_px: int
    height_px: int
    bounds: Rect


__all__ = ["RasterResult"]
