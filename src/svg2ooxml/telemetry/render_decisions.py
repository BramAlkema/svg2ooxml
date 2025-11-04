"""Telemetry system for tracking rendering decisions and fallback strategies."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class RenderDecision:
    """Record of a single rendering decision made during conversion."""

    element_type: str
    strategy: Literal["native", "emf", "raster"]
    reason: str
    timestamp: float  # Unix timestamp
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class RenderTracer:
    """Traces rendering decisions throughout the conversion pipeline."""

    def __init__(self) -> None:
        self._decisions: list[RenderDecision] = []

    def record_decision(
        self,
        element_type: str,
        strategy: Literal["native", "emf", "raster"],
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a rendering decision.

        Args:
            element_type: Type of element being rendered (e.g., "feBlend", "feComposite", "path")
            strategy: Rendering strategy chosen
            reason: Human-readable explanation of why this strategy was chosen
            metadata: Additional context about the decision
        """
        decision = RenderDecision(
            element_type=element_type,
            strategy=strategy,
            reason=reason,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._decisions.append(decision)

    def get_decisions(self) -> list[RenderDecision]:
        """Get all recorded decisions."""
        return list(self._decisions)

    def clear(self) -> None:
        """Clear all recorded decisions."""
        self._decisions.clear()

    def to_json(self) -> str:
        """Export decisions as JSON string."""
        data = {
            "decisions": [decision.to_dict() for decision in self._decisions],
            "summary": self._compute_summary(),
        }
        return json.dumps(data, indent=2)

    def to_file(self, path: str | Path) -> None:
        """Write decisions to JSON file.

        Args:
            path: Output file path
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_json())

    def _compute_summary(self) -> dict[str, Any]:
        """Compute aggregate statistics from recorded decisions."""
        if not self._decisions:
            return {
                "total_decisions": 0,
                "native_count": 0,
                "emf_count": 0,
                "raster_count": 0,
                "native_rate": 0.0,
                "emf_rate": 0.0,
                "raster_rate": 0.0,
            }

        total = len(self._decisions)
        native_count = sum(1 for d in self._decisions if d.strategy == "native")
        emf_count = sum(1 for d in self._decisions if d.strategy == "emf")
        raster_count = sum(1 for d in self._decisions if d.strategy == "raster")

        return {
            "total_decisions": total,
            "native_count": native_count,
            "emf_count": emf_count,
            "raster_count": raster_count,
            "native_rate": native_count / total,
            "emf_rate": emf_count / total,
            "raster_rate": raster_count / total,
        }


__all__ = ["RenderDecision", "RenderTracer"]
