"""Rasterisation primitives built on top of :mod:`skia`."""

from __future__ import annotations

from dataclasses import dataclass

try:  # pragma: no cover
    import skia
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("svg2ooxml.render requires skia-python; install the 'render' extra.") from exc

from .geometry import TessellationResult
from .surface import Surface


@dataclass(slots=True)
class Viewport:
    width: int
    height: int

    @classmethod
    def from_normalized_tree(cls, tree) -> "Viewport":
        return cls(int(tree.viewport_width), int(tree.viewport_height))


class Rasterizer:
    """Placeholder rasterizer, to be filled with pyportresvg logic."""

    def draw_fill(self, surface: Surface, tess: TessellationResult, paint: skia.Paint) -> None:
        path = self._build_skia_path(tess)
        surface.canvas().drawPath(path, paint)

    def draw_stroke(self, surface: Surface, tess: TessellationResult, paint: skia.Paint) -> None:
        path = self._build_skia_path(tess)
        surface.canvas().drawPath(path, paint)

    @staticmethod
    def _build_skia_path(tess: TessellationResult) -> skia.Path:
        raise NotImplementedError("Path construction will be implemented during the refactor.")


__all__ = ["Rasterizer", "Viewport"]
