"""Precision helpers for fractional EMU calculations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrecisionMetrics:
    total_points: int = 0
    total_segments: int = 0
    rounding_operations: int = 0

    def record_point(self, count: int = 1) -> PrecisionMetrics:
        return PrecisionMetrics(
            total_points=self.total_points + count,
            total_segments=self.total_segments,
            rounding_operations=self.rounding_operations,
        )

    def record_segment(self, count: int = 1) -> PrecisionMetrics:
        return PrecisionMetrics(
            total_points=self.total_points,
            total_segments=self.total_segments + count,
            rounding_operations=self.rounding_operations,
        )

    def record_rounding(self) -> PrecisionMetrics:
        return PrecisionMetrics(
            total_points=self.total_points,
            total_segments=self.total_segments,
            rounding_operations=self.rounding_operations + 1,
        )


__all__ = ["PrecisionMetrics"]
