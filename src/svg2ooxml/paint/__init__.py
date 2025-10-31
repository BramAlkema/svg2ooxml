"""Paint bridging utilities built during the render migration."""

from svg2ooxml.paint.resvg_bridge import (
    NormalizedPaints,
    resolve_fill_paint,
    resolve_paints_for_node,
    resolve_stroke_style,
)

__all__ = [
    "NormalizedPaints",
    "resolve_fill_paint",
    "resolve_paints_for_node",
    "resolve_stroke_style",
]
