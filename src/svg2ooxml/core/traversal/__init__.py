"""Traversal helpers for svg2ooxml."""

from .coordinate_space import CoordinateSpace
from .clipping import (
    GeometryPayload,
    extract_url_id,
    generate_clip_geometry,
    resolve_clip_ref,
    resolve_mask_ref,
)
from .markers import MarkerDefinition, MarkerInstance, MarkerTransform, apply_local_transform, build_marker_transform
from .marker_runtime import apply_marker_metadata, build_marker_shapes
from .traversal import ElementTraversal, TraverseCallback, navigation_from_attributes
from .transform_parser import TransformParser
from .runtime import (
    local_name,
    process_anchor,
    process_generic,
    process_group,
    process_use,
    push_element_transform,
    resolve_active_navigation,
)
from .hooks import TraversalHooksMixin

__all__ = [
    "CoordinateSpace",
    "GeometryPayload",
    "extract_url_id",
    "generate_clip_geometry",
    "resolve_clip_ref",
    "resolve_mask_ref",
    "MarkerDefinition",
    "MarkerInstance",
    "MarkerTransform",
    "apply_local_transform",
    "build_marker_transform",
    "apply_marker_metadata",
    "build_marker_shapes",
    "ElementTraversal",
    "TraverseCallback",
    "navigation_from_attributes",
    "local_name",
    "process_anchor",
    "process_generic",
    "process_group",
    "process_use",
    "push_element_transform",
    "resolve_active_navigation",
    "TraversalHooksMixin",
    "TransformParser",
]
