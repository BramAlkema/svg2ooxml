"""Shared types for feComposite parsing."""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_OPERATORS = {
    "over",
    "in",
    "out",
    "atop",
    "xor",
    "arithmetic",
}


@dataclass
class CompositeParams:
    operator: str
    input_1: str | None
    input_2: str | None
    k1: float
    k2: float
    k3: float
    k4: float
    result: str | None


__all__ = ["CompositeParams", "SUPPORTED_OPERATORS"]
