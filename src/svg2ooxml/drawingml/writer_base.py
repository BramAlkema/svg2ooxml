"""Base state and setup for the DrawingML writer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .animation_pipeline import AnimationPipeline
from .assets import AssetRegistry
from .generator import DrawingMLPathGenerator
from .mask_pipeline import MaskPipeline
from .navigation_runtime import NavigationRegistrar
from .pipelines.asset_pipeline import AssetPipeline

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.tracing import ConversionTracer
    from svg2ooxml.services.image_service import ImageService

    from .rasterizer import Rasterizer

DEFAULT_SLIDE_SIZE = (9144000, 6858000)  # 10" x 7.5"

logger = logging.getLogger("svg2ooxml.drawingml.writer")
_RASTERIZER_PENDING = object()


def assets_root() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "pptx_scaffold"


class DrawingMLWriterBase:
    """Own shared renderer state for one DrawingML writer instance."""

    def __init__(
        self,
        *,
        template_dir: Path | None = None,
        image_service: ImageService | None = None,
    ) -> None:
        self._template_dir = template_dir or assets_root()
        self._image_service = image_service
        self._slide_template = (self._template_dir / "slide_template.xml").read_text(encoding="utf-8")
        self._text_template = (self._template_dir / "text_shape_template.xml").read_text(encoding="utf-8")
        self._rectangle_template = (self._template_dir / "shape_rectangle.xml").read_text(encoding="utf-8")
        self._preset_template = (self._template_dir / "shape_preset.xml").read_text(encoding="utf-8")
        self._path_template = (self._template_dir / "shape_path.xml").read_text(encoding="utf-8")
        self._line_template = (self._template_dir / "shape_line.xml").read_text(encoding="utf-8")
        self._picture_template = (self._template_dir / "picture_shape.xml").read_text(encoding="utf-8")
        self._wordart_template = (self._template_dir / "wordart_shape_template.xml").read_text(encoding="utf-8")
        self._path_generator = DrawingMLPathGenerator()
        self._asset_pipeline = AssetPipeline(image_service=image_service)
        self._asset_registry: AssetRegistry | None = None
        self._navigation = NavigationRegistrar()
        self._mask_pipeline = MaskPipeline()
        self._rasterizer: Rasterizer | None | object = _RASTERIZER_PENDING
        self._animation_pipeline = AnimationPipeline(trace_writer=self._trace_writer)
        self._text_renderer = None
        self._shape_renderer = None
        self._scene_metadata: dict[str, Any] | None = None
        self._scene_background_color = None
        self._tracer: ConversionTracer | None = None

    @property
    def _assets(self) -> AssetRegistry:
        if self._asset_registry is None:
            raise RuntimeError("Asset registry not initialised for current rendering run.")
        return self._asset_registry

    @property
    def _scene_background_color(self):
        return self._asset_pipeline._scene_background_color

    @_scene_background_color.setter
    def _scene_background_color(self, value):
        self._asset_pipeline._scene_background_color = value

    @property
    def _emf_manager(self):
        return self._asset_pipeline.emf_manager

    @property
    def _next_media_index(self):
        return self._asset_pipeline.next_media_index

    @_next_media_index.setter
    def _next_media_index(self, value):
        self._asset_pipeline.next_media_index = value

    def set_image_service(self, image_service: ImageService | None) -> None:
        """Update the image service used for on-the-fly media resolution."""
        self._image_service = image_service
        self._asset_pipeline.set_image_service(image_service)

    def _resolve_rasterizer(self) -> Rasterizer | None:
        """Instantiate the optional skia rasterizer only when raster output is needed."""

        if self._rasterizer is None:
            return None
        if self._rasterizer is not _RASTERIZER_PENDING:
            return self._rasterizer
        try:
            from .rasterizer import SKIA_AVAILABLE, Rasterizer
        except Exception:  # pragma: no cover - optional dependency boundary
            self._rasterizer = None
            return None
        if not SKIA_AVAILABLE:
            self._rasterizer = None
            return None
        try:
            self._rasterizer = Rasterizer()
        except Exception:  # pragma: no cover - defensive
            self._rasterizer = None
        return self._rasterizer


__all__ = ["DEFAULT_SLIDE_SIZE", "DrawingMLWriterBase", "assets_root", "logger"]
