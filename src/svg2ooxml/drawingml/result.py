"""Structured output returned by the DrawingML writer."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .assets import AssetRegistrySnapshot

_BG_TEMPLATE = (
    '\n        <p:bg><p:bgPr>'
    '<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
    '<a:effectLst/>'
    '</p:bgPr></p:bg>'
)


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

    def _apply_background(self, color: str | None) -> DrawingMLRenderResult:
        """Return a copy with a solid slide background injected."""
        if not color:
            return self
        bg_xml = _BG_TEMPLATE.format(color=color)
        new_xml = self.slide_xml.replace("<p:cSld>", f"<p:cSld>{bg_xml}", 1)
        return replace(self, slide_xml=new_xml)


__all__ = ["DrawingMLRenderResult"]
