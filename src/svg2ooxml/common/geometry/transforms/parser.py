"""Parse SVG transform attribute strings into affine matrices."""

from __future__ import annotations

import re
from typing import Iterable

from .matrix import (
    IDENTITY,
    Matrix2D,
    matrix,
    rotate,
    scale,
    skew_x,
    skew_y,
    translate,
)

_TRANSFORM_RE = re.compile(r"(?P<name>[A-Za-z]+)\((?P<args>[^)]*)\)")
_SEPARATOR_RE = re.compile(r"[,\s]+")


def parse_transform(transform: str | None) -> Matrix2D:
    if not transform:
        return IDENTITY

    current = IDENTITY
    for match in _TRANSFORM_RE.finditer(transform):
        name = match.group("name").lower()
        raw_args = match.group("args")
        values = _parse_arguments(raw_args)
        current = current.multiply(_matrix_for(name, values))
    return current


def _parse_arguments(arguments: str) -> list[float]:
    if not arguments.strip():
        return []
    parts = _SEPARATOR_RE.split(arguments.strip())
    return [float(part) for part in parts if part]


def _matrix_for(name: str, values: Iterable[float]) -> Matrix2D:
    vals = list(values)
    if name == "matrix":
        if len(vals) != 6:
            raise ValueError("matrix() expects 6 parameters")
        return matrix(*vals)
    if name == "translate":
        if len(vals) == 1:
            vals.append(0.0)
        if len(vals) != 2:
            raise ValueError("translate() expects 1 or 2 parameters")
        return translate(vals[0], vals[1])
    if name == "scale":
        if len(vals) == 1:
            vals.append(None)
        if len(vals) != 2:
            raise ValueError("scale() expects 1 or 2 parameters")
        return scale(vals[0], vals[1])
    if name == "rotate":
        if len(vals) not in {1, 3}:
            raise ValueError("rotate() expects 1 or 3 parameters")
        angle = vals[0]
        if len(vals) == 3:
            cx, cy = vals[1], vals[2]
            return translate(cx, cy).multiply(rotate(angle)).multiply(translate(-cx, -cy))
        return rotate(angle)
    if name == "skewx":
        if len(vals) != 1:
            raise ValueError("skewX() expects 1 parameter")
        return skew_x(vals[0])
    if name == "skewy":
        if len(vals) != 1:
            raise ValueError("skewY() expects 1 parameter")
        return skew_y(vals[0])
    raise ValueError(f"Unsupported transform {name}")


__all__ = ["parse_transform"]
