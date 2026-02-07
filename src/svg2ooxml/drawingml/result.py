"""Structured output returned by the DrawingML writer."""

from __future__ import annotations

from dataclasses import dataclass

from .assets import AssetRegistrySnapshot


@dataclass(frozen=True)
class DrawingMLRenderResult:
    """Slide XML plus the assets required to package it."""

    slide_xml: str
    slide_size: tuple[int, int]
    assets: AssetRegistrySnapshot

    @property
    def width_emu(self) -> int:
        """Return the slide width in EMUs."""
        return self.slide_size[0]

    @property
    def height_emu(self) -> int:
        """Return the slide height in EMUs."""
        return self.slide_size[1]


__all__ = ["DrawingMLRenderResult"]
