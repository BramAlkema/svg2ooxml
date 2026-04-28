"""Gradient element optimization tagging and color normalization."""

from __future__ import annotations

import logging

from lxml import etree as ET

from svg2ooxml.color import parse_color
from svg2ooxml.elements.gradients.types import GradientAnalysis, GradientOptimization


def apply_gradient_optimizations(
    element: ET.Element,
    analysis: GradientAnalysis,
    context: object,
    *,
    logger: logging.Logger | None = None,
) -> ET.Element:
    """Apply recommended optimizations to gradient element."""
    _ = context
    active_logger = logger or logging.getLogger(__name__)
    optimized_element = copy_element(element)

    for optimization in analysis.optimization_opportunities:
        try:
            if optimization == GradientOptimization.COLOR_SIMPLIFICATION:
                optimized_element = apply_color_simplification(optimized_element, analysis)
            elif optimization == GradientOptimization.STOP_REDUCTION:
                optimized_element = apply_stop_reduction(optimized_element, analysis)
            elif optimization == GradientOptimization.TRANSFORM_FLATTENING:
                optimized_element = apply_transform_flattening(optimized_element, analysis)
            elif optimization == GradientOptimization.COLOR_SPACE_OPTIMIZATION:
                optimized_element = apply_color_space_optimization(
                    optimized_element,
                    analysis,
                    logger=active_logger,
                )
        except Exception as e:
            active_logger.warning(f"Failed to apply optimization {optimization}: {e}")

    optimized_element.set("data-gradient-optimized", "true")
    return optimized_element


def copy_element(element: ET.Element) -> ET.Element:
    """Create a deep copy of an element."""
    copied = ET.Element(element.tag)
    for key, value in element.attrib.items():
        copied.set(key, value)
    if element.text:
        copied.text = element.text
    if element.tail:
        copied.tail = element.tail
    for child in element:
        copied.append(copy_element(child))
    return copied


def apply_color_simplification(
    element: ET.Element,
    analysis: GradientAnalysis,
) -> ET.Element:
    """Apply color simplification optimization."""
    _ = analysis
    element.set("data-color-simplified", "true")
    return element


def apply_stop_reduction(element: ET.Element, analysis: GradientAnalysis) -> ET.Element:
    """Apply stop reduction optimization."""
    _ = analysis
    element.set("data-stops-reduced", "true")
    return element


def apply_transform_flattening(
    element: ET.Element,
    analysis: GradientAnalysis,
) -> ET.Element:
    """Apply transform flattening optimization."""
    _ = analysis
    element.set("data-transform-flattened", "true")
    return element


def apply_color_space_optimization(
    element: ET.Element,
    analysis: GradientAnalysis,
    *,
    logger: logging.Logger | None = None,
) -> ET.Element:
    """Apply color space optimization."""
    stop_elements = element.findall(".//stop")
    if not stop_elements:
        stop_elements = element.findall(".//{http://www.w3.org/2000/svg}stop")

    recommended_space = "srgb"
    stats = getattr(analysis, "color_statistics", {})
    if isinstance(stats, dict):
        recommended_space = stats.get("recommended_space", "srgb")

    active_logger = logger or logging.getLogger(__name__)
    for stop in stop_elements:
        color_str = stop.get("stop-color", "#000000")
        try:
            normalized_color, linear_rgb = normalize_color(
                color_str,
                target_space=recommended_space,
            )
            if normalized_color:
                stop.set("stop-color", normalized_color)
            if linear_rgb is not None:
                stop.set(
                    "data-linear-rgb",
                    "{:.6f},{:.6f},{:.6f}".format(*linear_rgb),
                )
        except Exception as e:
            active_logger.warning(f"Color normalization failed for '{color_str}': {e}")

    element.set("data-color-space", recommended_space)
    element.set("data-colors-normalized", "true")
    return element


def normalize_color(
    value: str,
    *,
    target_space: str = "srgb",
) -> tuple[str | None, tuple[float, float, float] | None]:
    token = (value or "").strip()
    if not token:
        return None, None
    colour = parse_color(token)
    if colour is None:
        return None, None

    hex_value = colour.to_hex().upper()
    linear_rgb = None
    if target_space == "linear_rgb":
        linear_rgb = tuple(
            srgb_channel_to_linear(component)
            for component in (colour.r, colour.g, colour.b)
        )
    return hex_value, linear_rgb


def srgb_channel_to_linear(component: float) -> float:
    component = max(0.0, min(1.0, component))
    if component <= 0.04045:
        return component / 12.92
    return ((component + 0.055) / 1.055) ** 2.4


__all__ = [
    "apply_color_simplification",
    "apply_color_space_optimization",
    "apply_gradient_optimizations",
    "apply_stop_reduction",
    "apply_transform_flattening",
    "copy_element",
    "normalize_color",
    "srgb_channel_to_linear",
]
