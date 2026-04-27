"""Text policy quality profiles and override handling."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class FontEmbeddingPolicy:
    """Embedding and subsetting configuration for discovered fonts."""

    embed_when_available: bool
    subset_strategy: str
    preserve_hinting: bool
    package_font_parts: bool
    allow_svg_font_conversion: bool


@dataclass(frozen=True)
class TextFallbackPolicy:
    """Fallback behaviour when requested fonts are unavailable."""

    missing_font_behavior: str
    glyph_fallback: str
    fallback_order: tuple[str, ...]
    max_vectorized_glyphs: int
    prefer_vector_fallback: bool


@dataclass(frozen=True)
class WordArtPolicy:
    """Configuration guiding WordArt detection and usage."""

    enable_detection: bool
    prefer_native_wordart: bool
    confidence_threshold: float
    allow_outline_fallback: bool


@dataclass(frozen=True)
class TextLayoutPolicy:
    """Controls kerning, leading, and language metadata emission."""

    kerning_mode: str
    leading_mode: str
    language_tagging: bool
    track_letter_spacing: bool


@dataclass(frozen=True)
class TextPolicyDecision:
    """Aggregated text policy values consumed during conversion."""

    quality: str
    embedding: FontEmbeddingPolicy
    fallback: TextFallbackPolicy
    wordart: WordArtPolicy
    layout: TextLayoutPolicy
    allow_effects: bool
    max_runs: int
    max_complexity: int
    diagnostics_level: str
    font_directories: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, object]:
        """Expose decision payloads as a serialisable mapping."""

        return {
            "quality": self.quality,
            "embedding": asdict(self.embedding),
            "fallback": asdict(self.fallback),
            "wordart": asdict(self.wordart),
            "layout": asdict(self.layout),
            "allow_effects": self.allow_effects,
            "max_runs": self.max_runs,
            "max_complexity": self.max_complexity,
            "diagnostics_level": self.diagnostics_level,
            "font_directories": list(self.font_directories),
        }


def _build_high_quality_decision() -> TextPolicyDecision:
    return TextPolicyDecision(
        quality="high",
        embedding=FontEmbeddingPolicy(
            embed_when_available=True,
            subset_strategy="glyph",
            preserve_hinting=True,
            package_font_parts=True,
            allow_svg_font_conversion=True,
        ),
        fallback=TextFallbackPolicy(
            missing_font_behavior="embedded",
            glyph_fallback="vector_outline",
            fallback_order=("Segoe UI", "Arial", "sans-serif"),
            max_vectorized_glyphs=4096,
            prefer_vector_fallback=True,
        ),
        wordart=WordArtPolicy(
            enable_detection=True,
            prefer_native_wordart=True,
            confidence_threshold=0.55,
            allow_outline_fallback=True,
        ),
        layout=TextLayoutPolicy(
            kerning_mode="preserve",
            leading_mode="document",
            language_tagging=True,
            track_letter_spacing=True,
        ),
        allow_effects=True,
        max_runs=4096,
        max_complexity=2048,
        diagnostics_level="verbose",
    )


def _build_balanced_decision() -> TextPolicyDecision:
    return TextPolicyDecision(
        quality="balanced",
        embedding=FontEmbeddingPolicy(
            embed_when_available=True,
            subset_strategy="character",
            preserve_hinting=False,
            package_font_parts=True,
            allow_svg_font_conversion=True,
        ),
        fallback=TextFallbackPolicy(
            missing_font_behavior="outline",
            glyph_fallback="vector_outline",
            fallback_order=("Calibri", "Arial", "sans-serif"),
            max_vectorized_glyphs=2048,
            prefer_vector_fallback=True,
        ),
        wordart=WordArtPolicy(
            enable_detection=True,
            prefer_native_wordart=True,
            confidence_threshold=0.45,
            allow_outline_fallback=True,
        ),
        layout=TextLayoutPolicy(
            kerning_mode="preserve",
            leading_mode="auto",
            language_tagging=True,
            track_letter_spacing=True,
        ),
        allow_effects=True,
        max_runs=2048,
        max_complexity=1024,
        diagnostics_level="summary",
    )


def _build_low_quality_decision() -> TextPolicyDecision:
    return TextPolicyDecision(
        quality="low",
        embedding=FontEmbeddingPolicy(
            embed_when_available=False,
            subset_strategy="none",
            preserve_hinting=False,
            package_font_parts=False,
            allow_svg_font_conversion=False,
        ),
        fallback=TextFallbackPolicy(
            missing_font_behavior="fallback_family",
            glyph_fallback="raster",
            fallback_order=("Arial", "Calibri", "sans-serif"),
            max_vectorized_glyphs=512,
            prefer_vector_fallback=False,
        ),
        wordart=WordArtPolicy(
            enable_detection=False,
            prefer_native_wordart=False,
            confidence_threshold=0.85,
            allow_outline_fallback=False,
        ),
        layout=TextLayoutPolicy(
            kerning_mode="disable",
            leading_mode="auto",
            language_tagging=False,
            track_letter_spacing=False,
        ),
        allow_effects=False,
        max_runs=256,
        max_complexity=160,
        diagnostics_level="minimal",
    )


QUALITY_PRESETS: dict[str, TextPolicyDecision] = {
    "high": _build_high_quality_decision(),
    "balanced": _build_balanced_decision(),
    "low": _build_low_quality_decision(),
}


def resolve_text_policy(
    quality: str,
    overrides: Mapping[str, object] | None = None,
) -> TextPolicyDecision:
    """Return a TextPolicyDecision for the requested quality profile."""

    base = QUALITY_PRESETS.get(quality)
    if base is None:
        base = replace(QUALITY_PRESETS["balanced"], quality=quality)

    decision = base
    if overrides:
        decision = _apply_overrides(decision, overrides)
    return decision


def _apply_overrides(
    decision: TextPolicyDecision,
    overrides: Mapping[str, object],
) -> TextPolicyDecision:
    for path, value in overrides.items():
        match path:
            case "text.embed_fonts":
                embedding = replace(decision.embedding, embed_when_available=bool(value))
                decision = replace(decision, embedding=embedding)
            case "text.subset_strategy":
                embedding = replace(decision.embedding, subset_strategy=str(value))
                decision = replace(decision, embedding=embedding)
            case "text.allow_effects":
                decision = replace(decision, allow_effects=bool(value))
            case "text.svg_font_conversion":
                embedding = replace(
                    decision.embedding,
                    allow_svg_font_conversion=bool(value),
                )
                decision = replace(decision, embedding=embedding)
            case "text.wordart.enable":
                wordart = replace(decision.wordart, enable_detection=bool(value))
                decision = replace(decision, wordart=wordart)
            case "text.wordart.prefer_native":
                wordart = replace(decision.wordart, prefer_native_wordart=bool(value))
                decision = replace(decision, wordart=wordart)
            case "text.wordart.confidence_threshold":
                wordart = replace(decision.wordart, confidence_threshold=float(value))
                decision = replace(decision, wordart=wordart)
            case "text.max_runs":
                decision = replace(decision, max_runs=int(value))
            case "text.max_complexity":
                decision = replace(decision, max_complexity=max(0, int(value)))
            case "text.fallback.behavior":
                fallback = replace(decision.fallback, missing_font_behavior=str(value))
                decision = replace(decision, fallback=fallback)
            case "text.glyph_fallback":
                fallback = replace(decision.fallback, glyph_fallback=str(value))
                decision = replace(decision, fallback=fallback)
            case "text.kerning_mode":
                layout = replace(decision.layout, kerning_mode=str(value))
                decision = replace(decision, layout=layout)
            case "text.language_tagging":
                layout = replace(decision.layout, language_tagging=bool(value))
                decision = replace(decision, layout=layout)
            case "text.font_dirs":
                directories = _normalise_font_directories(value)
                decision = replace(decision, font_directories=directories)
            case _:
                continue
    return decision


def explode_fallback_families(
    decision: TextPolicyDecision,
) -> Sequence[str]:
    """Return the ordered fallback family names for convenience."""

    return decision.fallback.fallback_order


def _normalise_font_directories(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        if not value:
            return ()
        parts = [
            segment.strip()
            for segment in value.replace(";", os.pathsep).split(os.pathsep)
        ]
        return tuple(part for part in parts if part)
    if isinstance(value, (list, tuple, set)):
        directories: list[str] = []
        for entry in value:
            if isinstance(entry, str) and entry.strip():
                directories.append(entry.strip())
        return tuple(directories)
    return ()


__all__ = [
    "FontEmbeddingPolicy",
    "TextFallbackPolicy",
    "TextLayoutPolicy",
    "TextPolicyDecision",
    "WordArtPolicy",
    "QUALITY_PRESETS",
    "_build_balanced_decision",
    "_build_high_quality_decision",
    "_build_low_quality_decision",
    "explode_fallback_families",
    "resolve_text_policy",
]
