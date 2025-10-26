"""Asset descriptors collected by the DrawingML writer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Tuple

from svg2ooxml.ir.text import EmbeddedFontPlan


@dataclass(frozen=True)
class MediaAsset:
    """Binary payload that must be packaged alongside slide XML."""

    relationship_id: str
    filename: str
    content_type: str
    data: bytes
    width_emu: int | None = None
    height_emu: int | None = None
    source: str | None = None


@dataclass(frozen=True)
class FontAsset:
    """Font embedding plan associated with a rendered shape."""

    shape_id: int
    plan: EmbeddedFontPlan


@dataclass(frozen=True)
class NavigationAsset:
    """Hyperlink or navigation descriptor associated with shapes or runs."""

    relationship_id: str | None
    relationship_type: str | None
    target: str | None
    target_mode: str | None = None
    action: str | None = None
    tooltip: str | None = None
    history: bool = True
    scope: str = "shape"
    text: str | None = None

    def requires_relationship(self) -> bool:
        return bool(self.relationship_id and self.relationship_type and self.target)


@dataclass(frozen=True)
class AssetRegistrySnapshot:
    """Immutable view of the collected assets."""

    media: Tuple[MediaAsset, ...] = field(default_factory=tuple)
    fonts: Tuple[FontAsset, ...] = field(default_factory=tuple)
    navigation: Tuple[NavigationAsset, ...] = field(default_factory=tuple)
    diagnostics: Tuple[str, ...] = field(default_factory=tuple)
    masks: Tuple[dict[str, object], ...] = field(default_factory=tuple)

    def iter_media(self) -> Iterable[MediaAsset]:
        """Iterate media assets."""
        return iter(self.media)

    def iter_fonts(self) -> Iterable[FontAsset]:
        """Iterate font embedding entries."""
        return iter(self.fonts)

    def iter_navigation(self) -> Iterable[NavigationAsset]:
        """Iterate navigation assets."""
        return iter(self.navigation)

    def iter_masks(self) -> Iterable[dict[str, object]]:
        """Iterate mask assets."""
        return iter(self.masks)


class AssetRegistry:
    """Mutable collector used while rendering a slide."""

    def __init__(self) -> None:
        self._media: list[MediaAsset] = []
        self._fonts: list[FontAsset] = []
        self._navigation: list[NavigationAsset] = []
        self._diagnostics: list[str] = []
        self._masks: list[dict[str, object]] = []

    def add_media(
        self,
        *,
        relationship_id: str,
        filename: str,
        content_type: str,
        data: bytes | bytearray,
        width_emu: int | None = None,
        height_emu: int | None = None,
        source: str | None = None,
    ) -> None:
        """Register a media payload to be packaged."""
        self._media.append(
            MediaAsset(
                relationship_id=relationship_id,
                filename=filename,
                content_type=content_type,
                data=bytes(data),
                width_emu=width_emu,
                height_emu=height_emu,
                source=source,
            )
        )

    def add_font_plan(self, *, shape_id: int, plan: EmbeddedFontPlan) -> None:
        """Register a font embedding plan associated with a shape."""
        self._fonts.append(FontAsset(shape_id=shape_id, plan=plan))

    def add_navigation(
        self,
        *,
        relationship_id: str | None,
        relationship_type: str | None,
        target: str | None,
        target_mode: str | None = None,
        action: str | None = None,
        tooltip: str | None = None,
        history: bool = True,
        scope: str = "shape",
        text: str | None = None,
    ) -> NavigationAsset:
        """Register navigation metadata that requires relationship wiring."""
        asset = NavigationAsset(
            relationship_id=relationship_id,
            relationship_type=relationship_type,
            target=target,
            target_mode=target_mode,
            action=action,
            tooltip=tooltip,
            history=history,
            scope=scope,
            text=text,
        )
        self._navigation.append(asset)
        return asset

    def add_diagnostic(self, message: str) -> None:
        """Record a diagnostic message emitted during rendering."""
        self._diagnostics.append(message)

    def add_mask_asset(
        self,
        *,
        relationship_id: str,
        part_name: str,
        content_type: str,
        data: bytes,
    ) -> None:
        """Register a mask part to be packaged."""
        existing = next((entry for entry in self._masks if entry["part_name"] == part_name), None)
        if existing is not None:
            return
        self._masks.append(
            {
                "relationship_id": relationship_id,
                "part_name": part_name,
                "content_type": content_type,
                "data": bytes(data),
            }
        )

    def snapshot(self) -> AssetRegistrySnapshot:
        """Return an immutable view of the collected assets."""
        return AssetRegistrySnapshot(
            media=tuple(self._media),
            fonts=tuple(self._fonts),
            navigation=tuple(self._navigation),
            diagnostics=tuple(self._diagnostics),
            masks=tuple(self._masks),
        )


__all__ = [
    "AssetRegistry",
    "AssetRegistrySnapshot",
    "FontAsset",
    "MediaAsset",
    "NavigationAsset",
]
