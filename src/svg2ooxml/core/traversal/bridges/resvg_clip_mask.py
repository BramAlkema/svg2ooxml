"""Convert resvg clipPath and mask nodes into core clip/mask definitions."""

from __future__ import annotations

from typing import Any

from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.common.geometry.paths import compute_segments_bbox
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    matrix_to_matrix2d as _matrix_to_matrix2d,
)
from svg2ooxml.core.resvg.usvg_tree import Tree
from svg2ooxml.core.traversal.bridges.resvg_clip_mask_bounds import (
    compute_primitives_bbox,
    normalize_mask_mode,
    parse_region,
)
from svg2ooxml.core.traversal.bridges.resvg_clip_mask_gather import (
    gather_clip_path,
    gather_segments,
)
from svg2ooxml.core.traversal.bridges.resvg_clip_mask_meta import (
    child_ids,
    mask_policy_hints,
    raw_region,
    serialized_sources,
)
from svg2ooxml.drawingml.skia_path import skia_path_bounds, skia_path_to_segments
from svg2ooxml.ir.geometry import Rect, SegmentType


def collect_resvg_clip_definitions(tree: Tree | None) -> dict[str, ClipDefinition]:
    """Return clip definitions composed from resvg clipPath nodes."""

    if tree is None or not getattr(tree, "clip_paths", None):
        return {}

    definitions: dict[str, ClipDefinition] = {}
    for clip_id, clip_node in tree.clip_paths.items():
        segments: list[SegmentType] = []
        primitives: list[dict[str, Any]] = []
        clip_rule = (
            clip_node.attributes.get("clip-rule")
            or clip_node.styles.get("clip-rule")
            or None
        )
        skia_path = gather_clip_path(
            clip_node,
            clip_node.transform,
            tree,
            visited={clip_id},
        )
        gather_segments(
            clip_node.children,
            clip_node.transform,
            tree,
            segments_out=segments,
            primitives_out=primitives,
            visited=set(),
        )
        skia_bbox = skia_path_bounds(skia_path)
        if skia_path is not None:
            op_segments = skia_path_to_segments(skia_path)
            if op_segments:
                segments = op_segments
        if not segments and not primitives:
            if _clip_path_is_empty(clip_node):
                definitions[clip_id] = ClipDefinition(
                    clip_id=clip_id,
                    segments=(),
                    bounding_box=Rect(0.0, 0.0, 0.0, 0.0),
                    clip_rule=clip_rule,
                    transform=_matrix_to_matrix2d(clip_node.transform),
                    primitives=(),
                    skia_path=skia_path,
                    is_empty=True,
                )
            continue
        if skia_bbox is not None:
            bbox = skia_bbox
        elif segments:
            bbox = compute_segments_bbox(segments)
        else:
            bbox = compute_primitives_bbox(primitives)
        if bbox is None:
            continue
        definitions[clip_id] = ClipDefinition(
            clip_id=clip_id,
            segments=tuple(segments),
            bounding_box=bbox,
            clip_rule=clip_rule,
            transform=_matrix_to_matrix2d(clip_node.transform),
            primitives=tuple(primitives),
            skia_path=skia_path,
        )
    return definitions


def _clip_path_is_empty(clip_node: Any) -> bool:
    children = getattr(clip_node, "children", ()) or ()
    return not any(_has_visible_clip_candidate(child) for child in children)


def _has_visible_clip_candidate(node: Any) -> bool:
    if _is_non_rendered(node):
        return False
    tag = str(getattr(node, "tag", "")).lower()
    if tag in {"g", "svg", "clippath"}:
        children = getattr(node, "children", ()) or ()
        return any(_has_visible_clip_candidate(child) for child in children)
    if tag in {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line", "use", "image"}:
        return True
    return True


def _is_non_rendered(node: Any) -> bool:
    display = _presentation_value(node, "display")
    if display == "none":
        return True
    visibility = _presentation_value(node, "visibility")
    return visibility in {"hidden", "collapse"}


def _presentation_value(node: Any, name: str) -> str | None:
    attrs = getattr(node, "attributes", {}) or {}
    styles = getattr(node, "styles", {}) or {}
    value = attrs.get(name)
    if styles.get(name) is not None:
        value = styles.get(name)
    return str(value).strip().lower() if value is not None else None


def collect_resvg_mask_info(tree: Tree | None) -> dict[str, MaskInfo]:
    """Return mask info derived from resvg mask nodes."""

    if tree is None or not getattr(tree, "masks", None):
        return {}

    masks: dict[str, MaskInfo] = {}
    for mask_id, mask_node in tree.masks.items():
        segments: list[SegmentType] = []
        primitives: list[dict[str, Any]] = []
        hints: dict[str, Any] = {"has_raster": False, "unsupported_nodes": []}
        gather_segments(
            mask_node.children,
            mask_node.transform,
            tree,
            segments_out=segments,
            primitives_out=primitives,
            visited=set(),
            hints=hints,
        )
        bbox = (
            compute_segments_bbox(segments)
            if segments
            else compute_primitives_bbox(primitives)
        )
        mask_type = mask_node.attributes.get("mask-type") or mask_node.attributes.get(
            "maskType"
        )

        masks[mask_id] = MaskInfo(
            mask_id=mask_id,
            mask_type=mask_type,
            mode=normalize_mask_mode(mask_type),
            mask_units=mask_node.mask_units,
            mask_content_units=mask_node.mask_content_units,
            region=parse_region(mask_node.attributes),
            opacity=getattr(mask_node.presentation, "opacity", None),
            transform=_matrix_to_matrix2d(mask_node.transform),
            children=child_ids(mask_node.children),
            bounding_box=bbox,
            segments=tuple(segments),
            content_xml=serialized_sources(mask_node.children),
            primitives=tuple(primitives),
            raw_region=raw_region(mask_node.attributes),
            policy_hints=mask_policy_hints(hints),
        )
    return masks


__all__ = ["collect_resvg_clip_definitions", "collect_resvg_mask_info"]
