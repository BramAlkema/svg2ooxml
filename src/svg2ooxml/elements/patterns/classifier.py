"""Pattern complexity and type detection."""

from __future__ import annotations

from typing import Any

from lxml import etree as ET

from svg2ooxml.color import summarize_palette

from ._helpers import (
    flatten_pattern_children,
    has_visible_paint,
    is_dot_like_path,
    local_name,
    style_map,
)

# Avoid circular: import at module level, used by assess_pattern_complexity.
# PatternComplexity/PatternType/PatternGeometry are defined in the coordinator;
# we accept them as arguments rather than importing from pattern_processor.


def analyze_pattern_content(
    element: ET.Element,
    PatternType: type,
) -> tuple[Any, int, dict[str, object]]:
    """Analyze pattern content to determine type and complexity.

    Returns ``(pattern_type, child_count, color_summary)``.
    """
    children = flatten_pattern_children(element)
    colors_raw: list[str] = []

    if not children:
        return PatternType.UNSUPPORTED, 0, summarize_palette(())

    # Analyze each child element
    shapes: dict[str, int] = {
        "circle": 0,
        "ellipse": 0,
        "rect": 0,
        "line": 0,
        "path": 0,
        "other": 0,
    }
    visible_children: list[ET.Element] = []

    for child in children:
        if not has_visible_paint(child):
            continue
        visible_children.append(child)
        tag = local_name(child.tag)

        if tag in shapes:
            shapes[tag] += 1
        else:
            shapes["other"] += 1

        sm = style_map(child)
        for attr in ["fill", "stroke"]:
            color = child.get(attr) or sm.get(attr)
            if color and color.lower() not in ["none", "transparent"]:
                colors_raw.append(color)

    child_count = len(visible_children)
    if child_count == 0:
        return PatternType.UNSUPPORTED, 0, summarize_palette(())

    pattern_type = classify_pattern_type(shapes, visible_children, PatternType)
    return pattern_type, child_count, summarize_palette(colors_raw)


def classify_pattern_type(
    shapes: dict[str, int],
    children: list[ET.Element],
    PatternType: type,
) -> Any:
    """Classify pattern type based on shape analysis."""
    total_shapes = sum(shapes.values())

    if total_shapes == 0 or shapes["other"] > total_shapes * 0.5:
        return PatternType.UNSUPPORTED

    if shapes["circle"] > 0 or shapes["ellipse"] > 0:
        if shapes["circle"] + shapes["ellipse"] > total_shapes * 0.7:
            return PatternType.DOTS

    if shapes["line"] > 0:
        if shapes["line"] > total_shapes * 0.7:
            return PatternType.LINES

    if shapes["rect"] > 0:
        rect_analysis = _analyze_rectangles(children)
        if rect_analysis["horizontal_lines"]:
            return PatternType.LINES
        elif rect_analysis["vertical_lines"]:
            return PatternType.LINES
        elif rect_analysis["grid"]:
            return PatternType.GRID

    if shapes["path"] > 0:
        path_analysis = _analyze_paths(children)
        if path_analysis["dots"]:
            return PatternType.DOTS
        elif path_analysis["diagonal"]:
            return PatternType.DIAGONAL
        elif path_analysis["grid"]:
            return PatternType.CROSS

    if shapes["line"] > 0 and shapes["rect"] > 0:
        return PatternType.GRID

    return PatternType.CUSTOM


def _analyze_rectangles(children: list[ET.Element]) -> dict[str, bool]:
    """Analyze rectangles to determine line patterns."""
    horizontal_lines = 0
    vertical_lines = 0
    squares = 0

    for child in children:
        if local_name(child.tag) == "rect":
            try:
                width = float(child.get("width", "1"))
                height = float(child.get("height", "1"))

                if width > height * 3:
                    horizontal_lines += 1
                elif height > width * 3:
                    vertical_lines += 1
                elif abs(width - height) < min(width, height) * 0.1:
                    squares += 1
            except (ValueError, TypeError):
                continue

    total_rects = horizontal_lines + vertical_lines + squares

    return {
        "horizontal_lines": horizontal_lines > total_rects * 0.7,
        "vertical_lines": vertical_lines > total_rects * 0.7,
        "grid": squares > 0 or (horizontal_lines > 0 and vertical_lines > 0),
    }


def _analyze_paths(children: list[ET.Element]) -> dict[str, bool]:
    """Analyze paths to determine pattern type."""
    dot_paths = 0
    diagonal_paths = 0
    grid_paths = 0

    for child in children:
        if local_name(child.tag) == "path":
            path_data = child.get("d", "")
            path_data_upper = path_data.upper()

            if is_dot_like_path(child):
                dot_paths += 1

            if "L" in path_data_upper and ("M" in path_data_upper):
                if "," in path_data:
                    diagonal_paths += 1

            if path_data_upper.count("L") > 2:
                grid_paths += 1

    total_paths = len([c for c in children if local_name(c.tag) == "path"])

    return {
        "dots": dot_paths > total_paths * 0.7,
        "diagonal": diagonal_paths > total_paths * 0.7,
        "grid": grid_paths > total_paths * 0.5,
    }


def assess_pattern_complexity(
    pattern_type: Any,
    child_count: int,
    geometry: Any,
    PatternComplexity: type,
    is_translation_only: Any,
) -> Any:
    """Assess overall pattern complexity."""
    type_complexity_map = {
        "DOTS": "SIMPLE",
        "LINES": "SIMPLE",
        "DIAGONAL": "MODERATE",
        "GRID": "MODERATE",
        "CROSS": "MODERATE",
        "CUSTOM": "COMPLEX",
        "UNSUPPORTED": "UNSUPPORTED",
    }

    complexity_name = type_complexity_map.get(pattern_type.name, "COMPLEX")
    type_complexity = getattr(PatternComplexity, complexity_name, PatternComplexity.COMPLEX)

    if child_count > 10:
        if type_complexity == PatternComplexity.SIMPLE:
            type_complexity = PatternComplexity.MODERATE
        elif type_complexity == PatternComplexity.MODERATE:
            type_complexity = PatternComplexity.COMPLEX

    if geometry.transform_matrix and not is_translation_only(
        geometry.transform_matrix
    ):
        if type_complexity == PatternComplexity.SIMPLE:
            type_complexity = PatternComplexity.MODERATE

    return type_complexity


def assess_powerpoint_compatibility(
    pattern_type: Any,
    complexity: Any,
    has_transforms: bool,
    PatternComplexity: type,
    PatternType: type,
) -> bool:
    """Assess PowerPoint compatibility."""
    if complexity in [PatternComplexity.COMPLEX, PatternComplexity.UNSUPPORTED]:
        return False

    if has_transforms:
        return pattern_type in [PatternType.DOTS, PatternType.LINES]

    return pattern_type in [
        PatternType.DOTS,
        PatternType.LINES,
        PatternType.DIAGONAL,
        PatternType.GRID,
        PatternType.CROSS,
    ]
