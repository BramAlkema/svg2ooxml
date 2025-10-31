
"""Public transform helpers backed by the modern geometry stack."""

from __future__ import annotations

from importlib import import_module
import sys

from svg2ooxml.common.geometry.transforms import (
    CoordinateSpace,
    DecomposedTransform,
    IDENTITY,
    Matrix,
    Matrix2D,
    compose_matrix,
    decompose_matrix,
    matrix,
    parse_transform,
    parse_transform_list,
    rotate,
    scale,
    skew_x,
    skew_y,
    translate,
)

__all__ = [
    "Matrix2D",
    "Matrix",
    "IDENTITY",
    "matrix",
    "translate",
    "scale",
    "rotate",
    "skew_x",
    "skew_y",
    "parse_transform",
    "parse_transform_list",
    "CoordinateSpace",
    "DecomposedTransform",
    "decompose_matrix",
    "compose_matrix",
]

_MODULE_ALIASES = {
    "svg2ooxml.transforms.matrix": "svg2ooxml.common.geometry.transforms.matrix",
    "svg2ooxml.transforms.parser": "svg2ooxml.common.geometry.transforms.parser",
    "svg2ooxml.transforms.coordinate_space": "svg2ooxml.common.geometry.transforms.space",
    "svg2ooxml.transforms.decomposition": "svg2ooxml.common.geometry.transforms.decompose",
}

for alias, target in _MODULE_ALIASES.items():
    if alias not in sys.modules:
        sys.modules[alias] = import_module(target)
