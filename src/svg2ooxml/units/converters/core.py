"""Core unit conversion helpers used by higher-level services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..conversion import ConversionContext, UnitConverter


@dataclass(slots=True)
class LengthConverter:
    """Convenience wrapper that mirrors the svg2pptx `LengthConverter` surface."""

    unit_converter: UnitConverter

    @classmethod
    def default(cls) -> "LengthConverter":
        return cls(UnitConverter())

    def to_emus(
        self,
        value: str | float | int,
        context: ConversionContext | None = None,
        *,
        axis: str | None = None,
    ) -> float:
        return self.unit_converter.to_emu(value, context, axis=axis)

    def to_px(
        self,
        value: str | float | int,
        context: ConversionContext | None = None,
        *,
        axis: str | None = None,
    ) -> float:
        return self.unit_converter.to_px(value, context, axis=axis)

    def to_emu_pair(
        self,
        values: Iterable[str | float | int],
        context: ConversionContext | None = None,
    ) -> tuple[float, float]:
        coords = tuple(values)
        if len(coords) != 2:
            raise ValueError("expected an (x, y) iterable")
        x, y = coords
        return (
            self.unit_converter.to_emu(x, context, axis="x"),
            self.unit_converter.to_emu(y, context, axis="y"),
        )

    def create_context(self, **kwargs) -> ConversionContext:
        return self.unit_converter.create_context(**kwargs)


__all__ = ["LengthConverter"]
