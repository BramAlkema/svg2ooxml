"""Structured output returned by the DrawingML writer."""

from __future__ import annotations

from dataclasses import dataclass

from .assets import AssetRegistrySnapshot


@dataclass(frozen=True)
class DrawingMLRenderResult:
    """Slide XML, shape fragments, and the assets required to package them."""

    slide_xml: str
    slide_size: tuple[int, int]
    assets: AssetRegistrySnapshot
    shape_xml: tuple[str, ...] = ()

    @property
    def width_emu(self) -> int:
        """Return the slide width in EMUs."""
        return self.slide_size[0]

    @property
    def height_emu(self) -> int:
        """Return the slide height in EMUs."""
        return self.slide_size[1]


__all__ = ["DrawingMLRenderResult"]
