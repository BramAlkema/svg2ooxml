"""Shared filter-related data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class FilterEffectResult:
    """Represents a rendered filter effect ready for IR consumption."""

    effect: Any | None
    strategy: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    fallback: str | None = None


__all__ = ["FilterEffectResult"]
