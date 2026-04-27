"""Text rendering decision data types."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
    def native(
        cls,
        *,
        reasons: Iterable[DecisionReason],
        **kwargs: Any,
    ) -> TextDecision:
        return cls(
            use_native=True,
            reasons=list(reasons),
            **_normalise_decision_kwargs(kwargs),
        )

    @classmethod
    def emf(
        cls,
        *,
        reasons: Iterable[DecisionReason],
        **kwargs: Any,
    ) -> TextDecision:
        return cls(
            use_native=False,
            reasons=list(reasons),
            **_normalise_decision_kwargs(kwargs),
        )

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
        return cls(
            use_native=True,
            reasons=list(reasons),
            **_normalise_decision_kwargs(payload),
        )

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


__all__ = [
    "DecisionReason",
    "FontDecisionContext",
    "GENERIC_FONT_FALLBACKS",
    "TextDecision",
]
