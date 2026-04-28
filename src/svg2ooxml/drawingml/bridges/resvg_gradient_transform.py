"""Transform classification and raster sizing for gradient conversion."""

from __future__ import annotations

import math

from svg2ooxml.common.geometry.transforms.decompose import (
    LinearTransformClass as TransformClass,
)
from svg2ooxml.common.geometry.transforms.decompose import classify_linear_transform


def classify_linear(
    a: float,
    b: float,
    c: float,
    d: float,
    eps: float = 1e-6,
) -> TransformClass:
    """Classify a 2D linear transform from matrix elements ``[[a, c], [b, d]]``."""

    return classify_linear_transform(a, b, c, d, eps=eps)


def decide_radial_policy(
    a: float,
    b: float,
    c: float,
    d: float,
    mild_ratio: float = 1.02,
) -> tuple[str, TransformClass]:
    """Choose vector or raster fallback handling for a radial gradient transform."""

    classification = classify_linear(a, b, c, d)
    if not classification.non_uniform:
        return "vector_ok", classification
    if classification.ratio <= mild_ratio and not classification.has_shear:
        return "vector_warn_mild_anisotropy", classification
    return "rasterize_nonuniform", classification


def _calculate_raster_size(
    s1: float,
    s2: float,
    oversample: float = 2.0,
    min_size: int = 64,
    max_size: int = 4096,
) -> int:
    """Calculate a bounded texture size for rasterized gradient fallback."""

    size = math.ceil(max(s1, s2) * oversample)
    return max(min_size, min(size, max_size))


__all__ = [
    "TransformClass",
    "_calculate_raster_size",
    "classify_linear",
    "decide_radial_policy",
]
