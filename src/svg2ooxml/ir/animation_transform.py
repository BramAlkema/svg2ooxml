"""Animation transform formatting helpers."""

from __future__ import annotations

from svg2ooxml.ir.animation_enums import TransformType


def format_transform_string(transform_type: TransformType, values: list[float]) -> str:
    """Format numeric transform arguments into an SVG transform string."""
    if transform_type == TransformType.TRANSLATE:
        if len(values) == 1:
            return f"translate({values[0]})"
        if len(values) == 2:
            return f"translate({values[0]}, {values[1]})"
        raise ValueError("translate requires 1 or 2 values")

    if transform_type == TransformType.SCALE:
        if len(values) == 1:
            return f"scale({values[0]})"
        if len(values) == 2:
            return f"scale({values[0]}, {values[1]})"
        raise ValueError("scale requires 1 or 2 values")

    if transform_type == TransformType.ROTATE:
        if len(values) == 1:
            return f"rotate({values[0]})"
        if len(values) == 3:
            return f"rotate({values[0]}, {values[1]}, {values[2]})"
        raise ValueError("rotate requires 1 or 3 values")

    if transform_type == TransformType.SKEWX:
        if len(values) == 1:
            return f"skewX({values[0]})"
        raise ValueError("skewX requires 1 value")

    if transform_type == TransformType.SKEWY:
        if len(values) == 1:
            return f"skewY({values[0]})"
        raise ValueError("skewY requires 1 value")

    if transform_type == TransformType.MATRIX:
        if len(values) == 6:
            return f"matrix({', '.join(map(str, values))})"
        raise ValueError("matrix requires 6 values")

    raise ValueError(f"Unknown transform type: {transform_type}")


__all__ = ["format_transform_string"]
