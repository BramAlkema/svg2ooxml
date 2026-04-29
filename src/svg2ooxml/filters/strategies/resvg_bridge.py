"""Resvg filter pipeline compatibility façade."""

from __future__ import annotations

from svg2ooxml.filters.strategies.resvg_promotion import (
    inject_promotion_metadata,
    is_identity_matrix,
    is_neutral_promotion,
    match_plan_elements,
    promote_resvg_plan,
    promotion_filter,
)
from svg2ooxml.filters.strategies.resvg_surface import (
    seed_source_surface,
    surface_to_bmp,
    turbulence_emf_effect,
)

__all__ = [
    "inject_promotion_metadata",
    "is_identity_matrix",
    "is_neutral_promotion",
    "match_plan_elements",
    "promote_resvg_plan",
    "promotion_filter",
    "seed_source_surface",
    "surface_to_bmp",
    "turbulence_emf_effect",
]
