
"""Rendering helpers for svg2ooxml."""

from .filters import FilterPlan, apply_filter, plan_filter
from .geometry import Tessellator, TessellationResult
from .mask_clip import rasterize_clip, rasterize_mask, rasterize_clip_path, resolve_clip_path, resolve_mask
from .normalize import NormalizedNode, NormalizedSvgTree, normalize_svg
from .paint import (
    GradientStop,
    LinearGradient,
    PatternPaint,
    RadialGradient,
    SolidPaint,
    StrokePaint,
    compute_paints,
)
from .pipeline import RenderContext, render
from .rasterizer import Rasterizer, Viewport
from .surface import Surface

__all__ = [
    "FilterPlan",
    "apply_filter",
    "plan_filter",
    "Tessellator",
    "TessellationResult",
    "rasterize_clip",
    "rasterize_clip_path",
    "rasterize_mask",
    "resolve_clip_path",
    "resolve_mask",
    "NormalizedNode",
    "NormalizedSvgTree",
    "normalize_svg",
    "SolidPaint",
    "GradientStop",
    "LinearGradient",
    "RadialGradient",
    "PatternPaint",
    "StrokePaint",
    "compute_paints",
    "RenderContext",
    "render",
    "Rasterizer",
    "Viewport",
    "Surface",
]
