"""Mask pipeline that coordinates mask writer setup per render pass."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .mask_store import MaskAssetStore
from .mask_writer import MaskWriter

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.tracing import ConversionTracer

    from .assets import AssetRegistry


class MaskPipeline:
    """Create and reuse mask writer per render run."""

    def __init__(self, *, mask_store_factory=MaskAssetStore) -> None:
        self._mask_store_factory = mask_store_factory
        self._mask_writer: MaskWriter | None = None

    def reset(self, *, assets: AssetRegistry, tracer: ConversionTracer | None) -> None:
        mask_store = self._mask_store_factory()
        self._mask_writer = MaskWriter(mask_store=mask_store, tracer=tracer)
        self._mask_writer.bind_assets(assets)

    def clear(self) -> None:
        self._mask_writer = None

    def render(self, element) -> tuple[str, list[str]]:
        if self._mask_writer is None:
            return "", []
        return self._mask_writer.render(element)


__all__ = ["MaskPipeline"]
