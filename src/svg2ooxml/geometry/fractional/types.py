"""Precision modes for fractional EMU conversion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PrecisionMode(Enum):
    STANDARD = 1
    HIGH = 10
    ULTRA = 100


@dataclass(frozen=True)
class PrecisionContext:
    mode: PrecisionMode = PrecisionMode.STANDARD
    dpi: float = 96.0


__all__ = ["PrecisionMode", "PrecisionContext"]
