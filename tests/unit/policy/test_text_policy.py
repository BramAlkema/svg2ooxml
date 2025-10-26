"""Unit tests for the text policy decision engine."""

from __future__ import annotations

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.policy.text_policy import (
    DecisionReason,
    TextDecision,
    TextPolicy,
    resolve_text_policy,
)
from svg2ooxml.services.fonts import FontMatch, FontQuery, FontService


def _make_frame(*runs: Run) -> TextFrame:
    return TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 40),
        runs=list(runs),
    )


class _StaticFontProvider:
    def __init__(self, available: dict[str, str]) -> None:
        self._available = {key.lower(): value for key, value in available.items()}

    def resolve(self, query: FontQuery) -> FontMatch | None:  # pragma: no cover - simple shim
        path = self._available.get(query.family.lower())
        if path is None:
            return None
        return FontMatch(
            family=query.family,
            path=path,
            weight=query.weight,
            style=query.style,
            found_via="static",
        )

    def list_alternatives(self, query: FontQuery):  # pragma: no cover - shim for FontService contract
        match = self.resolve(query)
        if match is not None:
            yield match


def test_native_decision_when_below_thresholds() -> None:
    service = FontService()
    service.register_provider(_StaticFontProvider({"Inter": "/fonts/Inter.ttf"}))

    policy = TextPolicy(font_service=service)
    decision = resolve_text_policy("balanced")
    frame = _make_frame(Run(text="Hello", font_family="Inter", font_size_pt=20.0))

    result = policy.decide(frame, policy=decision)

    assert isinstance(result, TextDecision)
    assert result.use_native is True
    assert DecisionReason.BELOW_THRESHOLDS in result.reasons
    assert result.has_missing_fonts is False
    assert result.font_strategy in {None, "system"}  # strategy may be inferred lazily


def test_run_count_above_threshold_falls_back_to_emf() -> None:
    service = FontService()
    service.register_provider(_StaticFontProvider({"Inter": "/fonts/Inter.ttf"}))

    policy = TextPolicy(font_service=service)
    decision = resolve_text_policy("low", {"text.max_runs": 1})
    frame = _make_frame(
        Run(text="Hello", font_family="Inter", font_size_pt=20.0),
        Run(text="World", font_family="Inter", font_size_pt=20.0),
    )

    result = policy.decide(frame, policy=decision)

    assert result.use_native is False
    assert DecisionReason.ABOVE_THRESHOLDS in result.reasons


def test_missing_fonts_with_fallback_family_prefers_system_font() -> None:
    service = FontService()
    service.register_provider(_StaticFontProvider({"Arial": "/fonts/Arial.ttf"}))

    policy = TextPolicy(font_service=service)
    decision = resolve_text_policy("balanced", {"text.fallback.behavior": "fallback_family"})
    frame = _make_frame(Run(text="Test", font_family="Unknown Font", font_size_pt=16.0))

    result = policy.decide(frame, policy=decision)

    assert result.use_native is True
    assert result.has_missing_fonts is True
    assert result.font_strategy == "system_fallback"
    assert result.system_font_fallback == "Arial"
    assert "Unknown Font" in result.missing_fonts


def test_disallow_effects_triggers_conservative_emf() -> None:
    service = FontService()
    service.register_provider(_StaticFontProvider({"Inter": "/fonts/Inter.ttf"}))

    policy = TextPolicy(font_service=service)
    decision = resolve_text_policy("balanced", {"text.allow_effects": False})
    frame = _make_frame(Run(text="Bold", font_family="Inter", font_size_pt=18.0, bold=True))

    result = policy.decide(frame, policy=decision)

    assert result.use_native is False
    assert DecisionReason.CONSERVATIVE_MODE in result.reasons
    assert DecisionReason.TEXT_EFFECTS_COMPLEX in result.reasons
