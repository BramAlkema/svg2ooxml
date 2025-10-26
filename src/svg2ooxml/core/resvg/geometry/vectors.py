"""Vector math helpers used during path processing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Vec2:
    x: float
    y: float

    def to_tuple(self) -> tuple[float, float]:
        return self.x, self.y
