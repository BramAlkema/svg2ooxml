"""Compatibility wrapper for <use> expansion helpers."""

from __future__ import annotations

from svg2ooxml.core.styling.use_expander import *  # noqa: F401,F403

__all__ = [
    "_apply_computed_presentation",
    "apply_use_attributes",
    "apply_use_transform",
    "compute_use_transform",
    "instantiate_use_target",
    "propagate_symbol_use_attributes",
    "resolve_use_offsets",
]
