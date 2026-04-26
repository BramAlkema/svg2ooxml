"""Mask and clip-path compositing utilities."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from svg2ooxml.common.svg_refs import unwrap_url_reference
from svg2ooxml.core.resvg.geometry.tessellation import Tessellator
from svg2ooxml.core.resvg.usvg_tree import BaseNode, ClipPathNode, MaskNode, Tree
from svg2ooxml.render.rasterizer import Rasterizer, Viewport
from svg2ooxml.render.shapes import node_geometry


@dataclass(slots=True)
class MaskContext:
    node: MaskNode


@dataclass(slots=True)
class ClipPathContext:
    node: ClipPathNode


def resolve_mask(tree: Tree, href: str | None) -> MaskContext | None:
    href = unwrap_url_reference(href)
    if not href:
        return None
    mask_node = tree.resolve_mask(href)
    if mask_node is None:
        return None
    return MaskContext(node=mask_node)


def resolve_clip_path(tree: Tree, href: str | None) -> ClipPathContext | None:
    href = unwrap_url_reference(href)
    if not href:
        return None
    clip_node = tree.resolve_clip_path(href)
    if clip_node is None:
        return None
    return ClipPathContext(node=clip_node)


def apply_mask(surface, mask_alpha: np.ndarray):
    masked = surface.clone()
    masked.data[..., 3] *= mask_alpha
    return masked


def apply_clip(surface, clip_mask: np.ndarray):
    clipped = surface.clone()
    clipped.data[~clip_mask] = 0.0
    return clipped


def rasterize_mask(
    context: MaskContext,
    tessellator: Tessellator,
    rasterizer: Rasterizer,
    viewport: Viewport,
) -> np.ndarray:
    alpha = np.zeros((viewport.height, viewport.width), dtype=np.float32)
    for child in context.node.children:
        _accumulate_mask_alpha(alpha, child, tessellator, rasterizer, viewport)
    return alpha


def rasterize_clip_path(
    context: ClipPathContext,
    tessellator: Tessellator,
    rasterizer: Rasterizer,
    viewport: Viewport,
) -> np.ndarray:
    mask = np.zeros((viewport.height, viewport.width), dtype=bool)
    for child in context.node.children:
        coverage = _coverage_for_node(child, tessellator, rasterizer, viewport, combine_children=True)
        if coverage is not None:
            mask |= coverage
    return mask


def _coverage_for_node(
    node: BaseNode,
    tessellator: Tessellator,
    rasterizer: Rasterizer,
    viewport: Viewport,
    *,
    combine_children: bool,
) -> np.ndarray | None:
    geometry = node_geometry(node)
    if geometry is not None:
        tessellation = tessellator.tessellate_fill(geometry)
        if not tessellation.contours:
            return None
        coverage = rasterizer.rasterize_fill(tessellation, viewport)
        if not np.any(coverage):
            return None
        return coverage

    if not combine_children:
        return None

    combined: np.ndarray | None = None
    for child in node.children:
        child_cov = _coverage_for_node(
            child,
            tessellator,
            rasterizer,
            viewport,
            combine_children=True,
        )
        if child_cov is None:
            continue
        if combined is None:
            combined = child_cov.copy()
        else:
            combined |= child_cov
    return combined


def _accumulate_mask_alpha(
    alpha: np.ndarray,
    node: BaseNode,
    tessellator: Tessellator,
    rasterizer: Rasterizer,
    viewport: Viewport,
) -> None:
    coverage = _coverage_for_node(node, tessellator, rasterizer, viewport, combine_children=False)
    if coverage is None:
        for child in node.children:
            _accumulate_mask_alpha(alpha, child, tessellator, rasterizer, viewport)
        return
    opacity = _node_opacity(node)
    if opacity <= 0.0:
        return
    alpha[coverage] = np.maximum(alpha[coverage], opacity)


def _node_opacity(node: BaseNode) -> float:
    if node.fill is not None:
        color = getattr(node.fill, "color", None)
        if color is not None:
            luminance = 0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b
            return max(0.0, min(1.0, luminance * node.fill.opacity))
        return node.fill.opacity
    if node.stroke is not None:
        color = getattr(node.stroke, "color", None)
        if color is not None:
            luminance = 0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b
            return max(0.0, min(1.0, luminance * node.stroke.opacity))
        return node.stroke.opacity
    return 1.0


__all__ = [
    "MaskContext",
    "ClipPathContext",
    "resolve_mask",
    "resolve_clip_path",
    "apply_mask",
    "apply_clip",
    "rasterize_mask",
    "rasterize_clip_path",
    "rasterize_clip",
]

rasterize_clip = rasterize_clip_path
