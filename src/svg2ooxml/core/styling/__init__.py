"""Styling helpers for svg2ooxml core pipeline."""

from .style_extractor import StyleExtractor, StyleResult
from .style_runtime import extract_style
from .use_expander import (
    apply_use_attributes,
    apply_use_transform,
    compute_use_transform,
    instantiate_use_target,
    propagate_symbol_use_attributes,
    resolve_use_offsets,
)

__all__ = [
    "StyleExtractor",
    "StyleResult",
    "extract_style",
    "apply_use_attributes",
    "apply_use_transform",
    "compute_use_transform",
    "instantiate_use_target",
    "propagate_symbol_use_attributes",
    "resolve_use_offsets",
]
