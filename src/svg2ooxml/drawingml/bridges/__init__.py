"""Bridge helpers connecting resvg traversal to DrawingML surfaces."""

from __future__ import annotations

from .emf_path_adapter import EMFPathAdapter, EMFPathResult, PathStyle
from .resvg_paint_bridge import (
    GradientDescriptor,
    GradientStopDescriptor,
    LinearGradientDescriptor,
    MeshGradientDescriptor,
    PatternDescriptor,
    RadialGradientDescriptor,
    build_linear_gradient_element,
    build_mesh_gradient_element,
    build_pattern_element,
    build_radial_gradient_element,
    describe_gradient_element,
    describe_linear_gradient,
    describe_pattern,
    describe_pattern_element,
    describe_radial_gradient,
)

__all__ = [
    "EMFPathAdapter",
    "EMFPathResult",
    "PathStyle",
    "GradientDescriptor",
    "GradientStopDescriptor",
    "LinearGradientDescriptor",
    "RadialGradientDescriptor",
    "MeshGradientDescriptor",
    "PatternDescriptor",
    "build_linear_gradient_element",
    "build_radial_gradient_element",
    "build_mesh_gradient_element",
    "build_pattern_element",
    "describe_linear_gradient",
    "describe_radial_gradient",
    "describe_pattern",
    "describe_gradient_element",
    "describe_pattern_element",
]
