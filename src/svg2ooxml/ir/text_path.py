"""Text path data structures used for curved text layouts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .geometry import Point, Rect
from .text import EnhancedRun, Run, TextAnchor


class TextPathMethod(Enum):
    ALIGN = "align"
    STRETCH = "stretch"


class TextPathSpacing(Enum):
    EXACT = "exact"
    AUTO = "auto"


class TextPathSide(Enum):
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class PathPoint:
    x: float
    y: float
    tangent_angle: float
    distance_along_path: float
    curvature: float = 0.0
    normal_angle: float = 0.0

    @property
    def position(self) -> Point:
        return Point(self.x, self.y)

    @property
    def tangent_degrees(self) -> float:
        import math

        return math.degrees(self.tangent_angle)

    @property
    def normal_degrees(self) -> float:
        import math

        return math.degrees(self.normal_angle)


@dataclass(frozen=True)
class CharacterPlacement:
    character: str
    position: PathPoint
    run_index: int
    char_index: int
    advance_width: float
    baseline_offset: float = 0.0
    rotation: float = 0.0

    @property
    def effective_rotation(self) -> float:
        return self.position.tangent_degrees + self.rotation


RunType = Run | EnhancedRun


@dataclass(frozen=True)
class TextPathFrame:
    runs: list[RunType]
    path_reference: str
    start_offset: float = 0.0
    method: TextPathMethod = TextPathMethod.ALIGN
    spacing: TextPathSpacing = TextPathSpacing.AUTO
    side: TextPathSide = TextPathSide.LEFT
    character_placements: list[CharacterPlacement] | None = None
    path_points: list[PathPoint] | None = None
    total_path_length: float | None = None
    auto_rotate: bool = True
    baseline_offset: float = 0.0
    letter_spacing: float = 0.0
    render_method: str = "positioned_chars"
    fallback_anchor: TextAnchor = TextAnchor.START

    def __post_init__(self) -> None:
        if not self.runs:
            raise ValueError("TextPathFrame must have at least one run")
        if not self.path_reference.strip():
            raise ValueError("Path reference cannot be empty")
        if self.start_offset < 0:
            raise ValueError("Start offset must be non-negative")

    @property
    def text_content(self) -> str:
        return "".join(run.text for run in self.runs)

    @property
    def character_count(self) -> int:
        return len(self.text_content)

    @property
    def run_count(self) -> int:
        return len(self.runs)

    @property
    def is_positioned(self) -> bool:
        placements = self.character_placements or []
        return len(placements) == self.character_count and self.character_count > 0

    @property
    def path_coverage(self) -> float:
        if not self.is_positioned or not self.total_path_length:
            return 0.0
        placements = self.character_placements or []
        if not placements:
            return 0.0
        last = placements[-1]
        return last.position.distance_along_path / self.total_path_length

    @property
    def estimated_bounds(self) -> Rect | None:
        placements = self.character_placements or []
        if not placements:
            return None
        positions = [placement.position for placement in placements]
        min_x = min(pos.x for pos in positions)
        max_x = max(pos.x for pos in positions)
        min_y = min(pos.y for pos in positions)
        max_y = max(pos.y for pos in positions)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)

    def get_characters_with_runs(self) -> list[tuple[str, int, int]]:
        characters: list[tuple[str, int, int]] = []
        for run_idx, run in enumerate(self.runs):
            for char_idx, char in enumerate(run.text):
                characters.append((char, run_idx, char_idx))
        return characters

    def get_run_for_character(self, global_char_index: int) -> RunType | None:
        if global_char_index < 0:
            return None
        remaining = global_char_index
        for run in self.runs:
            if remaining < len(run.text):
                return run
            remaining -= len(run.text)
        return None


__all__ = [
    "CharacterPlacement",
    "PathPoint",
    "TextPathFrame",
    "TextPathMethod",
    "TextPathSpacing",
    "TextPathSide",
]
