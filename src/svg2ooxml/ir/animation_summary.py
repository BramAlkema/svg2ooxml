"""Animation summary and complexity rollups."""

from __future__ import annotations

from dataclasses import dataclass, field

from svg2ooxml.ir.animation_enums import AnimationComplexity


@dataclass(slots=True)
class AnimationSummary:
    """Roll-up statistics describing the animations found in an SVG."""

    total_animations: int = 0
    complexity: AnimationComplexity = AnimationComplexity.SIMPLE
    duration: float = 0.0
    has_transforms: bool = False
    has_motion_paths: bool = False
    has_color_animations: bool = False
    has_easing: bool = False
    has_sequences: bool = False
    element_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def calculate_complexity(self) -> None:
        score = 0
        score += min(self.total_animations, 10)

        if self.has_transforms:
            score += 5
        if self.has_motion_paths:
            score += 8
        if self.has_color_animations:
            score += 3
        if self.has_easing:
            score += 4
        if self.has_sequences:
            score += 6

        if self.duration > 10:
            score += 3
        elif self.duration > 5:
            score += 1

        if self.element_count > 10:
            score += 4
        elif self.element_count > 5:
            score += 2

        if score <= 5:
            self.complexity = AnimationComplexity.SIMPLE
        elif score <= 15:
            self.complexity = AnimationComplexity.MODERATE
        elif score <= 25:
            self.complexity = AnimationComplexity.COMPLEX
        else:
            self.complexity = AnimationComplexity.VERY_COMPLEX


__all__ = ["AnimationSummary"]
