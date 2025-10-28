"""High-level render pipeline scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .geometry import Tessellator
from .rasterizer import Rasterizer, Viewport
from .surface import Surface


@dataclass(slots=True)
class RenderContext:
    tessellator: Tessellator
    rasterizer: Rasterizer


def render(tree, context: Optional[RenderContext] = None) -> Surface:
    """Render a normalized SVG tree into an RGBA surface.

    This is intentionally unimplemented until the refactor wires through the
    full normalisation/tessellation pipeline.
    """

    viewport = Viewport.from_normalized_tree(tree)
    surface = Surface.make(viewport.width, viewport.height)
    context = context or RenderContext(tessellator=Tessellator(), rasterizer=Rasterizer())
    raise NotImplementedError("Rendering will be implemented during the render refactor.")


__all__ = ["RenderContext", "render"]

