"""Structured text policy profiles and runtime decision engine."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any

from svg2ooxml.ir.text import TextFrame
from svg2ooxml.services.fonts import FontMatch, FontQuery

# ---------------------------------------------------------------------------
# Policy profiles (quality presets + overrides)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FontEmbeddingPolicy:
    """Embedding and subsetting configuration for discovered fonts."""

    embed_when_available: bool
    subset_strategy: str  # e.g. "glyph", "character", "none"
    preserve_hinting: bool
    package_font_parts: bool
    allow_svg_font_conversion: bool


@dataclass(frozen=True)
class TextFallbackPolicy:
    """Fallback behaviour when requested fonts are unavailable."""

    missing_font_behavior: str  # e.g. "embedded", "fallback_family", "outline"
    glyph_fallback: str  # e.g. "vector_outline", "emf", "raster"
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

    kerning_mode: str  # e.g. "preserve", "loosen", "disable"
    leading_mode: str  # e.g. "preserve", "auto", "document"
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
    diagnostics_level: str  # e.g. "minimal", "summary", "verbose"
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
            prefer_native_wordart=False,
            confidence_threshold=0.7,
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
        # Default to balanced settings but mark requested quality for diagnostics.
        base = replace(QUALITY_PRESETS["balanced"], quality=quality)

    decision = base
    if overrides:
        decision = _apply_overrides(decision, overrides)
    return decision


def _apply_overrides(
    decision: TextPolicyDecision,
    overrides: Mapping[str, object],
) -> TextPolicyDecision:
    # Recognised overrides follow a dotted path naming scheme.
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
                embedding = replace(decision.embedding, allow_svg_font_conversion=bool(value))
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
                # Unrecognised overrides are ignored for now.
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
        parts = [segment.strip() for segment in value.replace(";", os.pathsep).split(os.pathsep)]
        return tuple(part for part in parts if part)
    if isinstance(value, (list, tuple, set)):
        directories: list[str] = []
        for entry in value:
            if isinstance(entry, str) and entry.strip():
                directories.append(entry.strip())
        return tuple(directories)
    return ()


# ---------------------------------------------------------------------------
# Runtime decision types
# ---------------------------------------------------------------------------


class DecisionReason(Enum):
    """Reasons recorded for text policy decisions."""

    BELOW_THRESHOLDS = "below_thresholds"
    ABOVE_THRESHOLDS = "above_thresholds"
    TEXT_EFFECTS_COMPLEX = "text_effects_complex"
    FONT_UNAVAILABLE = "font_unavailable"
    FONT_AVAILABLE = "font_available"
    SUPPORTED_FEATURES = "supported_features"
    CONSERVATIVE_MODE = "conservative_mode"
    COMPLEXITY_LIMIT = "complexity_limit"
    WORDART_PATTERN_DETECTED = "wordart_pattern_detected"
    NATIVE_PRESET_AVAILABLE = "native_preset_available"
    FALLBACK_TRIGGERED = "fallback_triggered"


@dataclass(frozen=True)
class TextDecision:
    """Policy outcome describing how a TextFrame should be rendered."""

    use_native: bool
    reasons: list[DecisionReason]
    confidence: float = 1.0
    run_count: int = 0
    complexity_score: int = 0
    has_missing_fonts: bool = False
    has_effects: bool = False
    has_multiline: bool = False
    wordart_preset: str | None = None
    wordart_parameters: Mapping[str, Any] | None = None
    font_strategy: str | None = None
    font_match_confidence: float = 0.0
    embedded_font_name: str | None = None
    system_font_fallback: str | None = None
    glyph_fallback: str | None = None
    missing_fonts: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.missing_fonts is None:
            object.__setattr__(self, "missing_fonts", ())
        elif not isinstance(self.missing_fonts, tuple):
            object.__setattr__(self, "missing_fonts", tuple(self.missing_fonts))

    @classmethod
    def native(cls, *, reasons: Iterable[DecisionReason], **kwargs: Any) -> TextDecision:
        return cls(use_native=True, reasons=list(reasons), **_normalise_decision_kwargs(kwargs))

    @classmethod
    def emf(cls, *, reasons: Iterable[DecisionReason], **kwargs: Any) -> TextDecision:
        return cls(use_native=False, reasons=list(reasons), **_normalise_decision_kwargs(kwargs))

    @classmethod
    def wordart(
        cls,
        *,
        preset: str,
        parameters: Mapping[str, Any] | None,
        confidence: float,
        reasons: Iterable[DecisionReason],
        **kwargs: Any,
    ) -> TextDecision:
        payload = dict(kwargs)
        payload["wordart_preset"] = preset
        payload["wordart_parameters"] = dict(parameters or {})
        payload["confidence"] = confidence
        return cls(use_native=True, reasons=list(reasons), **_normalise_decision_kwargs(payload))

    def to_mapping(self) -> dict[str, Any]:
        """Expose the decision as a mapping useful for diagnostics."""

        return {
            "use_native": self.use_native,
            "reasons": [reason.value for reason in self.reasons],
            "confidence": self.confidence,
            "run_count": self.run_count,
            "complexity_score": self.complexity_score,
            "has_missing_fonts": self.has_missing_fonts,
            "has_effects": self.has_effects,
            "has_multiline": self.has_multiline,
            "wordart_preset": self.wordart_preset,
            "font_strategy": self.font_strategy,
            "font_match_confidence": self.font_match_confidence,
            "embedded_font_name": self.embedded_font_name,
            "system_font_fallback": self.system_font_fallback,
            "glyph_fallback": self.glyph_fallback,
            "missing_fonts": list(self.missing_fonts),
        }


def _normalise_decision_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(kwargs)
    missing_fonts = payload.get("missing_fonts")
    if missing_fonts is not None and not isinstance(missing_fonts, tuple):
        payload["missing_fonts"] = tuple(missing_fonts)
    return payload


def _filtered_font_kwargs(font_kwargs: Mapping[str, Any], *ignore: str) -> dict[str, Any]:
    return {key: value for key, value in font_kwargs.items() if key not in ignore}


GENERIC_FONT_FALLBACKS = {
    "sans-serif": ("Arial", "Helvetica"),
    "serif": ("Times New Roman", "Georgia"),
    "monospace": ("Courier New", "Consolas", "Courier"),
    "cursive": ("Comic Sans MS", "Brush Script MT"),
    "fantasy": ("Impact", "Papyrus"),
}


@dataclass
class FontDecisionContext:
    """Result of policy font availability analysis."""

    has_missing_fonts: bool = False
    strategy: str | None = None
    confidence: float = 0.0
    embedded_font: str | None = None
    fallback_font: str | None = None
    missing_fonts: list[str] = field(default_factory=list)

    def to_decision_kwargs(self) -> dict[str, Any]:
        return {
            "font_strategy": self.strategy,
            "font_match_confidence": self.confidence,
            "embedded_font_name": self.embedded_font,
            "system_font_fallback": self.fallback_font,
            "missing_fonts": list(self.missing_fonts),
        }


class TextPolicy:
    """Evaluate text complexity and determine rendering strategy."""

    def __init__(
        self,
        *,
        font_service: Any | None = None,
        font_system: Any | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.font_service = font_service
        self.font_system = font_system
        self.logger = logger or logging.getLogger(__name__)

    def attach_font_services(self, *, font_service: Any | None = None, font_system: Any | None = None) -> None:
        if font_service is not None:
            self.font_service = font_service
        if font_system is not None:
            self.font_system = font_system

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def decide(
        self,
        frame: TextFrame,
        *,
        policy: TextPolicyDecision | None = None,
    ) -> TextDecision:
        """Return a TextDecision describing the rendering strategy."""

        decision = policy or QUALITY_PRESETS["balanced"]

        runs = list(frame.runs or [])
        run_count = len(runs)
        complexity_score = self._estimate_complexity(frame)
        has_effects = any(self._run_has_effects(run) for run in runs)
        has_multiline = frame.is_multiline

        if run_count == 0:
            return TextDecision.native(
                reasons=[DecisionReason.BELOW_THRESHOLDS],
                run_count=0,
                complexity_score=0,
                has_effects=False,
                has_multiline=False,
                has_missing_fonts=False,
                confidence=1.0,
            )

        font_context = self._evaluate_font_availability(frame, decision)
        font_kwargs = font_context.to_decision_kwargs()
        glyph_fallback = decision.fallback.glyph_fallback

        # Conservative mode strips decorated text.
        if not decision.allow_effects and has_effects:
            reasons = [DecisionReason.CONSERVATIVE_MODE, DecisionReason.TEXT_EFFECTS_COMPLEX]
            return TextDecision.emf(
                reasons=reasons,
                run_count=run_count,
                complexity_score=complexity_score,
                has_missing_fonts=font_context.has_missing_fonts,
                has_effects=has_effects,
                has_multiline=has_multiline,
                confidence=0.9,
                glyph_fallback=glyph_fallback,
                **font_kwargs,
            )

        if run_count > decision.max_runs:
            reasons = [DecisionReason.ABOVE_THRESHOLDS]
            return TextDecision.emf(
                reasons=reasons,
                run_count=run_count,
                complexity_score=complexity_score,
                has_missing_fonts=font_context.has_missing_fonts,
                has_effects=has_effects,
                has_multiline=has_multiline,
                confidence=0.85,
                glyph_fallback=glyph_fallback,
                **font_kwargs,
            )

        if complexity_score > decision.max_complexity:
            reasons = [DecisionReason.ABOVE_THRESHOLDS, DecisionReason.COMPLEXITY_LIMIT]
            return TextDecision.emf(
                reasons=reasons,
                run_count=run_count,
                complexity_score=complexity_score,
                has_missing_fonts=font_context.has_missing_fonts,
                has_effects=has_effects,
                has_multiline=has_multiline,
                confidence=0.8,
                glyph_fallback=glyph_fallback,
                **font_kwargs,
            )

        if font_context.has_missing_fonts:
            return self._handle_missing_fonts(
                decision=decision,
                run_count=run_count,
                complexity_score=complexity_score,
                has_effects=has_effects,
                has_multiline=has_multiline,
                font_kwargs=font_kwargs,
                glyph_fallback=glyph_fallback,
            )

        reasons = [
            DecisionReason.BELOW_THRESHOLDS,
            DecisionReason.FONT_AVAILABLE,
            DecisionReason.SUPPORTED_FEATURES,
        ]
        return TextDecision.native(
            reasons=reasons,
            run_count=run_count,
            complexity_score=complexity_score,
            has_missing_fonts=False,
            has_effects=has_effects,
            has_multiline=has_multiline,
            confidence=0.95,
            glyph_fallback=glyph_fallback,
            **font_kwargs,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_missing_fonts(
        self,
        *,
        decision: TextPolicyDecision,
        run_count: int,
        complexity_score: int,
        has_effects: bool,
        has_multiline: bool,
        font_kwargs: Mapping[str, Any],
        glyph_fallback: str | None,
    ) -> TextDecision:
        reasons = [DecisionReason.FONT_UNAVAILABLE]
        missing_fonts = tuple(font_kwargs.get("missing_fonts", ()))
        behavior = decision.fallback.missing_font_behavior.lower()

        if behavior == "outline":
            reasons.append(DecisionReason.FALLBACK_TRIGGERED)
            return TextDecision.native(
                reasons=reasons,
                run_count=run_count,
                complexity_score=complexity_score,
                has_missing_fonts=True,
                has_effects=has_effects,
                has_multiline=has_multiline,
                confidence=0.9,
                font_strategy="text_to_path",
                glyph_fallback=glyph_fallback,
                missing_fonts=missing_fonts,
                **_filtered_font_kwargs(font_kwargs, "missing_fonts", "font_strategy"),
            )

        if behavior == "fallback_family":
            fallback_font = font_kwargs.get("system_font_fallback")
            if fallback_font:
                reasons.append(DecisionReason.FALLBACK_TRIGGERED)
                return TextDecision.native(
                    reasons=reasons,
                    run_count=run_count,
                    complexity_score=complexity_score,
                    has_missing_fonts=True,
                    has_effects=has_effects,
                    has_multiline=has_multiline,
                    confidence=0.9,
                    font_strategy="system_fallback",
                    glyph_fallback=glyph_fallback,
                    system_font_fallback=fallback_font,
                    missing_fonts=missing_fonts,
                    **_filtered_font_kwargs(font_kwargs, "missing_fonts", "system_font_fallback", "font_strategy"),
                )

        if behavior == "emf":
            reasons.append(DecisionReason.FALLBACK_TRIGGERED)
            return TextDecision.emf(
                reasons=reasons,
                run_count=run_count,
                complexity_score=complexity_score,
                has_missing_fonts=True,
                has_effects=has_effects,
                has_multiline=has_multiline,
                confidence=0.95,
                glyph_fallback=glyph_fallback,
                missing_fonts=missing_fonts,
                **_filtered_font_kwargs(font_kwargs, "missing_fonts", "font_strategy"),
            )

        # Default behaviour attempts embedding if allowed, otherwise falls back to EMF.
        if decision.embedding.embed_when_available:
            reasons.append(DecisionReason.FALLBACK_TRIGGERED)
            return TextDecision.native(
                reasons=reasons,
                run_count=run_count,
                complexity_score=complexity_score,
                has_missing_fonts=True,
                has_effects=has_effects,
                has_multiline=has_multiline,
                confidence=0.9,
                font_strategy="embedded",
                glyph_fallback=glyph_fallback,
                missing_fonts=missing_fonts,
                **_filtered_font_kwargs(font_kwargs, "missing_fonts", "font_strategy"),
            )

        reasons.append(DecisionReason.FALLBACK_TRIGGERED)
        return TextDecision.emf(
            reasons=reasons,
            run_count=run_count,
            complexity_score=complexity_score,
            has_missing_fonts=True,
            has_effects=has_effects,
            has_multiline=has_multiline,
            confidence=0.95,
            glyph_fallback=glyph_fallback,
            missing_fonts=missing_fonts,
            **_filtered_font_kwargs(font_kwargs, "missing_fonts", "font_strategy"),
        )

    def _estimate_complexity(self, frame: TextFrame) -> int:
        score = 0
        for run in frame.runs or []:
            text_length = len(run.text or "")
            score += 1 + text_length // 16
            if getattr(run, "bold", False):
                score += 1
            if getattr(run, "italic", False):
                score += 1
            if getattr(run, "underline", False) or getattr(run, "strike", False) or getattr(run, "has_decoration", False):
                score += 2
        if frame.is_multiline:
            score += 3
        return score

    @staticmethod
    def _run_has_effects(run: Any) -> bool:
        return bool(
            getattr(run, "bold", False)
            or getattr(run, "italic", False)
            or getattr(run, "underline", False)
            or getattr(run, "strike", False)
            or getattr(run, "has_decoration", False)
        )

    def _evaluate_font_availability(
        self,
        frame: TextFrame,
        decision: TextPolicyDecision,
    ) -> FontDecisionContext:
        if self.font_service is None:
            context = FontDecisionContext(
                has_missing_fonts=False,
                strategy="unknown",
                confidence=0.0,
                missing_fonts=[],
            )
            return context

        runs = list(frame.runs or [])
        if not runs:
            return FontDecisionContext(strategy="none", confidence=1.0)

        missing_fonts: list[str] = []
        available_runs = 0
        fallback_font: str | None = None

        for run in runs:
            families = self._parse_font_families(getattr(run, "font_family", None))
            if not families:
                families = ["sans-serif"]

            primary_family = families[0]
            weight = 700 if getattr(run, "bold", False) else 400
            style = "italic" if getattr(run, "italic", False) else "normal"

            direct_match = self._find_font_match(
                candidates=families,
                weight=weight,
                style=style,
                fallback_chain=(),
            )
            if direct_match is not None:
                available_runs += 1
                fallback_font = fallback_font or direct_match.family
                continue

            candidates = list(families)
            for family in families:
                candidates.extend(GENERIC_FONT_FALLBACKS.get(family.lower(), ()))

            fallback_match = self._find_font_match(
                candidates=candidates,
                weight=weight,
                style=style,
                fallback_chain=decision.fallback.fallback_order,
            )
            if fallback_match is not None:
                available_runs += 1
                fallback_font = fallback_font or fallback_match.family
                if primary_family not in missing_fonts:
                    missing_fonts.append(primary_family)
            else:
                if primary_family not in missing_fonts:
                    missing_fonts.append(primary_family)

        total_runs = len(runs)
        confidence = round(available_runs / total_runs, 2) if total_runs else 0.0
        context = FontDecisionContext(
            has_missing_fonts=bool(missing_fonts),
            strategy="system" if not missing_fonts else "fallback",
            confidence=confidence,
            missing_fonts=missing_fonts,
            fallback_font=fallback_font,
        )
        return context

    def _find_font_match(
        self,
        *,
        candidates: Sequence[str],
        weight: int,
        style: str,
        fallback_chain: Sequence[str],
    ) -> FontMatch | None:
        service = self.font_service
        if service is None:
            return None

        for family in candidates:
            try:
                query = FontQuery(
                    family=family,
                    weight=weight,
                    style=style,
                    fallback_chain=fallback_chain,
                )
                match = service.find_font(query)
            except Exception as exc:  # pragma: no cover - defensive logging
                self.logger.debug("Font lookup failed for %s: %s", family, exc)
                match = None
            if match is not None:
                return match
        return None

    @staticmethod
    def _parse_font_families(font_family: str | None) -> list[str]:
        if not font_family:
            return []
        families: list[str] = []
        for token in font_family.split(","):
            name = token.strip().strip('"').strip("'")
            if name:
                families.append(name)
        return families


__all__ = [
    "DecisionReason",
    "FontEmbeddingPolicy",
    "FontDecisionContext",
    "TextDecision",
    "TextFallbackPolicy",
    "TextLayoutPolicy",
    "TextPolicy",
    "TextPolicyDecision",
    "WordArtPolicy",
    "QUALITY_PRESETS",
    "explode_fallback_families",
    "resolve_text_policy",
]
