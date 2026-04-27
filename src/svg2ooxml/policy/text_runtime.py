"""Runtime text policy evaluation."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from svg2ooxml.ir.text import TextFrame
from svg2ooxml.services.fonts import FontMatch, FontQuery

from .text_decisions import (
    GENERIC_FONT_FALLBACKS,
    DecisionReason,
    FontDecisionContext,
    TextDecision,
    _filtered_font_kwargs,
)
from .text_profiles import QUALITY_PRESETS, TextPolicyDecision


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

    def attach_font_services(
        self,
        *,
        font_service: Any | None = None,
        font_system: Any | None = None,
    ) -> None:
        if font_service is not None:
            self.font_service = font_service
        if font_system is not None:
            self.font_system = font_system

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

        if not decision.allow_effects and has_effects:
            reasons = [
                DecisionReason.CONSERVATIVE_MODE,
                DecisionReason.TEXT_EFFECTS_COMPLEX,
            ]
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
            reasons = [
                DecisionReason.ABOVE_THRESHOLDS,
                DecisionReason.COMPLEXITY_LIMIT,
            ]
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
                **_filtered_font_kwargs(
                    font_kwargs,
                    "missing_fonts",
                    "font_strategy",
                ),
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
                    **_filtered_font_kwargs(
                        font_kwargs,
                        "missing_fonts",
                        "system_font_fallback",
                        "font_strategy",
                    ),
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
                **_filtered_font_kwargs(
                    font_kwargs,
                    "missing_fonts",
                    "font_strategy",
                ),
            )

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
                **_filtered_font_kwargs(
                    font_kwargs,
                    "missing_fonts",
                    "font_strategy",
                ),
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
            if (
                getattr(run, "underline", False)
                or getattr(run, "strike", False)
                or getattr(run, "has_decoration", False)
            ):
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
            return FontDecisionContext(
                has_missing_fonts=False,
                strategy="unknown",
                confidence=0.0,
                missing_fonts=[],
            )

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
            elif primary_family not in missing_fonts:
                missing_fonts.append(primary_family)

        total_runs = len(runs)
        confidence = round(available_runs / total_runs, 2) if total_runs else 0.0
        return FontDecisionContext(
            has_missing_fonts=bool(missing_fonts),
            strategy="system" if not missing_fonts else "fallback",
            confidence=confidence,
            missing_fonts=missing_fonts,
            fallback_font=fallback_font,
        )

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


__all__ = ["TextPolicy"]
