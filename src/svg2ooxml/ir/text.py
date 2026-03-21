"""Text representation for svg2ooxml IR."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .font_metadata import FontMetadata
from .geometry import Point, Rect


class TextAnchor(Enum):
    START = "start"
    MIDDLE = "middle"
    END = "end"


@dataclass(frozen=True)
class Run:
    text: str
    font_family: str
    font_size_pt: float
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    rgb: str = "000000"
    theme_color: str | None = None
    fill_opacity: float = 1.0
    stroke_rgb: str | None = None
    stroke_theme_color: str | None = None
    stroke_width_px: float | None = None
    stroke_opacity: float | None = None
    navigation: Any | None = None
    language: str | None = None
    kerning: float | None = None
    letter_spacing: float | None = None
    word_spacing: float | None = None
    east_asian_font: str | None = None
    complex_script_font: str | None = None
    theme_font: str | None = None
    font_variant: str | None = None

    def __post_init__(self) -> None:
        if self.font_size_pt <= 0:
            raise ValueError("font size must be positive")
        if len(self.rgb) != 6:
            raise ValueError("rgb must be 6 hex characters")
        if self.stroke_rgb is not None and len(self.stroke_rgb) != 6:
            raise ValueError("stroke_rgb must be 6 hex characters")

    @property
    def has_decoration(self) -> bool:
        return self.underline or self.strike

    @property
    def has_stroke(self) -> bool:
        return self.stroke_rgb is not None and (self.stroke_width_px or 0.0) > 0.0

    @property
    def weight_class(self) -> int:
        return 700 if self.bold else 400


@dataclass(frozen=True)
class EnhancedRun:
    text: str
    font_family: str
    font_size_pt: float
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    rgb: str = "000000"
    theme_color: str | None = None
    fill_opacity: float = 1.0
    stroke_rgb: str | None = None
    stroke_theme_color: str | None = None
    stroke_width_px: float | None = None
    stroke_opacity: float | None = None
    font_metadata: FontMetadata | None = None
    text_decorations: list[str] = field(default_factory=list)
    style_inheritance: dict[str, Any] = field(default_factory=dict)
    letter_spacing: float | None = None
    word_spacing: float | None = None
    text_transform: str = "none"
    baseline_shift: float = 0.0
    rotation_angle: float = 0.0
    language: str | None = None
    kerning: float | None = None
    east_asian_font: str | None = None
    complex_script_font: str | None = None
    theme_font: str | None = None

    def __post_init__(self) -> None:
        if self.font_size_pt <= 0:
            raise ValueError("font size must be positive")
        if len(self.rgb) != 6:
            raise ValueError("rgb must be 6 hex characters")
        if self.stroke_rgb is not None and len(self.stroke_rgb) != 6:
            raise ValueError("stroke_rgb must be 6 hex characters")

    @property
    def has_decoration(self) -> bool:
        return (
            self.underline
            or self.strike
            or bool(self.text_decorations)
        )

    @property
    def has_stroke(self) -> bool:
        return self.stroke_rgb is not None and (self.stroke_width_px or 0.0) > 0.0

    @property
    def weight_class(self) -> int:
        if self.font_metadata:
            return self.font_metadata.weight
        return 700 if self.bold else 400

    @property
    def effective_font_family(self) -> str:
        if self.font_metadata:
            return self.font_metadata.family
        return self.font_family

    @property
    def effective_font_size(self) -> float:
        if self.font_metadata:
            return self.font_metadata.size_pt
        return self.font_size_pt

    @property
    def is_transformed(self) -> bool:
        return (
            self.baseline_shift != 0.0
            or self.rotation_angle != 0.0
            or self.text_transform != "none"
        )

    def to_basic_run(self) -> Run:
        return Run(
            text=self.text,
            font_family=self.font_family,
            font_size_pt=self.font_size_pt,
            bold=self.bold,
            italic=self.italic,
            underline=self.underline,
            strike=self.strike,
            rgb=self.rgb,
            theme_color=self.theme_color,
            fill_opacity=self.fill_opacity,
            stroke_rgb=self.stroke_rgb,
            stroke_theme_color=self.stroke_theme_color,
            stroke_width_px=self.stroke_width_px,
            stroke_opacity=self.stroke_opacity,
            language=self.language,
            kerning=self.kerning,
            letter_spacing=self.letter_spacing,
            word_spacing=self.word_spacing,
            east_asian_font=self.east_asian_font,
            complex_script_font=self.complex_script_font,
            theme_font=self.theme_font,
        )


@dataclass(frozen=True)
class WordArtCandidate:
    """Metadata for potential WordArt conversions."""

    preset: str
    confidence: float
    fallback_strategy: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.preset:
            raise ValueError("preset must be non-empty")

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.5


@dataclass(frozen=True)
class EmbeddedFontPlan:
    """Embedding plan generated by the text pipeline."""

    font_family: str
    requires_embedding: bool
    subset_strategy: str
    glyph_count: int = 0
    relationship_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.glyph_count < 0:
            raise ValueError("glyph_count cannot be negative")
        if not self.font_family:
            raise ValueError("font_family must be non-empty")


@dataclass(frozen=True)
class TextFrame:
    origin: Point
    anchor: TextAnchor
    bbox: Rect
    runs: list[Run] | None = None
    line_height: float | None = None
    baseline_shift: float = 0.0
    direction: str | None = None  # "rtl" or "ltr" or None (auto-detect)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    wordart_candidate: WordArtCandidate | None = None
    embedding_plan: EmbeddedFontPlan | None = None

    def __post_init__(self) -> None:
        if self.runs is None:
            object.__setattr__(self, "runs", [])

    @property
    def is_textless(self) -> bool:
        return not self.runs

    @property
    def text_content(self) -> str:
        return "".join(run.text for run in self.runs)

    @property
    def is_multiline(self) -> bool:
        return "\n" in self.text_content


__all__ = [
    "Run",
    "EnhancedRun",
    "TextFrame",
    "TextAnchor",
    "WordArtCandidate",
    "EmbeddedFontPlan",
]
