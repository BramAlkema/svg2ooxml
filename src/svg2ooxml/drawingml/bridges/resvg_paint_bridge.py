"""Compatibility facade for resvg paint bridge descriptors and XML helpers."""

from __future__ import annotations

from svg2ooxml.drawingml.bridges.resvg_paint_describe import (
    describe_gradient_element,
    describe_linear_gradient,
    describe_pattern,
    describe_pattern_element,
    describe_radial_gradient,
)
from svg2ooxml.drawingml.bridges.resvg_paint_descriptors import (
    GradientDescriptor,
    GradientStopDescriptor,
    LinearGradientDescriptor,
    MeshGradientDescriptor,
    PatternDescriptor,
    RadialGradientDescriptor,
)
from svg2ooxml.drawingml.bridges.resvg_paint_elements import (
    build_linear_gradient_element,
    build_mesh_gradient_element,
    build_pattern_element,
    build_radial_gradient_element,
)

__all__ = [
    "GradientDescriptor",
    "GradientStopDescriptor",
    "LinearGradientDescriptor",
    "RadialGradientDescriptor",
    "MeshGradientDescriptor",
    "PatternDescriptor",
    "describe_linear_gradient",
    "describe_radial_gradient",
    "describe_pattern",
    "describe_gradient_element",
    "describe_pattern_element",
    "build_linear_gradient_element",
    "build_radial_gradient_element",
    "build_mesh_gradient_element",
    "build_pattern_element",
]
