"""Structured text policy profiles and runtime decision engine."""

from __future__ import annotations

from .text_decisions import (
    GENERIC_FONT_FALLBACKS,
    DecisionReason,
    FontDecisionContext,
    TextDecision,
)
from .text_profiles import (
    QUALITY_PRESETS,
    FontEmbeddingPolicy,
    TextFallbackPolicy,
    TextLayoutPolicy,
    TextPolicyDecision,
    WordArtPolicy,
    _build_balanced_decision,
    _build_high_quality_decision,
    _build_low_quality_decision,
    explode_fallback_families,
    resolve_text_policy,
)
from .text_runtime import TextPolicy

__all__ = [
    "DecisionReason",
    "FontDecisionContext",
    "FontEmbeddingPolicy",
    "GENERIC_FONT_FALLBACKS",
    "QUALITY_PRESETS",
    "TextDecision",
    "TextFallbackPolicy",
    "TextLayoutPolicy",
    "TextPolicy",
    "TextPolicyDecision",
    "WordArtPolicy",
    "_build_balanced_decision",
    "_build_high_quality_decision",
    "_build_low_quality_decision",
    "explode_fallback_families",
    "resolve_text_policy",
]
