"""Modernized geometry algorithms shared across svg2ooxml."""

from .curve_text_positioning import (
    CurveTextPositioner,
    PathSamplingMethod,
    PathSegment,
    PathWarpFitter,
    WarpFitResult,
    create_curve_text_positioner,
    create_path_warp_fitter,
)
from .wordart_classifier import (
    PathFeatures,
    WordArtClassificationResult,
    classify_text_path_warp,
)

__all__ = [
    "CurveTextPositioner",
    "PathSamplingMethod",
    "PathSegment",
    "PathWarpFitter",
    "WarpFitResult",
    "create_curve_text_positioner",
    "create_path_warp_fitter",
    "PathFeatures",
    "WordArtClassificationResult",
    "classify_text_path_warp",
]
