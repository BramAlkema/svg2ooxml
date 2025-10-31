"""Pixmap-like surface abstraction inspired by tiny-skia."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

import numpy as np

RGBA = Tuple[float, float, float, float]


@dataclass(slots=True)
class Surface:
    """Simple float32 RGBA surface with premultiplied alpha."""

    width: int
    height: int
    data: np.ndarray  # shape (height, width, 4), premultiplied RGBA in float32

    @classmethod
    def make(cls, width: int, height: int, color: RGBA | None = None) -> "Surface":
        array = np.zeros((height, width, 4), dtype=np.float32)
        surface = cls(width=width, height=height, data=array)
        if color is not None:
            surface.clear(color)
        return surface

    @classmethod
    def from_rgba8(cls, buffer: Iterable[int], width: int, height: int) -> "Surface":
        array = np.fromiter(buffer, dtype=np.uint8, count=width * height * 4)
        array = array.reshape((height, width, 4)).astype(np.float32) / 255.0
        return cls(width=width, height=height, data=array)

    def clone(self) -> "Surface":
        return Surface(self.width, self.height, self.data.copy())

    def clear(self, color: RGBA) -> None:
        r, g, b, a = color
        self.data[...] = np.array([r, g, b, a], dtype=np.float32)

    def to_rgba8(self) -> np.ndarray:
        clipped = np.clip(self.data, 0.0, 1.0)
        return (clipped * 255.0).astype(np.uint8)

    def to_numpy(self) -> np.ndarray:
        """Return a float32 RGBA view of the surface."""

        return self.data

    @property
    def shape(self) -> Tuple[int, int, int]:
        return self.data.shape

    def as_view(self) -> np.ndarray:
        return self.data

    def blend(self, other: "Surface") -> None:
        if other.shape != self.shape:
            raise ValueError("Surface shapes must match for blending")
        src = other.data
        dst = self.data
        src_a = src[..., 3:4]
        dst[...] = src + dst * (1.0 - src_a)


def ensure_surface(surface: Surface | None, width: int, height: int) -> Surface:
    if surface is None or surface.width != width or surface.height != height:
        return Surface.make(width, height)
    return surface


__all__ = ["Surface", "ensure_surface"]
