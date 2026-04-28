
"""Public transform helpers backed by the modern geometry stack."""

from __future__ import annotations

import sys
from importlib import import_module

from svg2ooxml.common.geometry.transforms.decompose import (
    DecomposedTransform,
    LinearTransformClass,
    classify_linear_transform,
    compose_matrix,
    decompose_matrix,
)
from svg2ooxml.common.geometry.transforms.matrix import (
    IDENTITY,
    Matrix,
    Matrix2D,
    matrix,
    parse_transform_list,
    rotate,
    scale,
    skew_x,
    skew_y,
    translate,
)
from svg2ooxml.common.geometry.transforms.parser import parse_transform
from svg2ooxml.common.geometry.transforms.space import CoordinateSpace

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
    "LinearTransformClass",
    "decompose_matrix",
    "classify_linear_transform",
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
