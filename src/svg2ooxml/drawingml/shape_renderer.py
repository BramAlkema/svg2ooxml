"""Shape rendering helpers extracted from DrawingMLWriter."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from svg2ooxml.ir.scene import Image

from .animation_pipeline import AnimationPipeline
from .generator import DrawingMLPathGenerator
from .shape_renderer_clip import ShapeRendererClipMixin
from .shape_renderer_dispatch import ShapeRendererDispatchMixin
from .shape_renderer_effects import ShapeRendererEffectsMixin
from .shape_renderer_patterns import ShapeRendererPatternMixin
from .shape_renderer_raster import ShapeRendererRasterMixin

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .rasterizer import Rasterizer


class DrawingMLShapeRenderer(
    ShapeRendererDispatchMixin,
    ShapeRendererEffectsMixin,
    ShapeRendererRasterMixin,
    ShapeRendererPatternMixin,
    ShapeRendererClipMixin,
):
    """Render shapes, paths, and images into DrawingML fragments."""

    _INVALID_EFFECT_SUBSTRINGS = (
        "svg2ooxml:sourcegraphic",
        "svg2ooxml:sourcealpha",
        "svg2ooxml:emf",
        "svg2ooxml:raster",
    )

    def __init__(
        self,
        *,
        rectangle_template: str,
        preset_template: str,
        path_template: str,
        line_template: str,
        picture_template: str,
        path_generator: DrawingMLPathGenerator,
        policy_for: Callable[[dict[str, object] | None, str], dict[str, object]],
        register_media: Callable[[Image], str],
        trace_writer: Callable[..., None],
        animation_pipeline: AnimationPipeline,
        rasterizer: Rasterizer | None,
        logger: logging.Logger,
        rasterizer_provider: Callable[[], Rasterizer | None] | None = None,
    ) -> None:
        self._rectangle_template = rectangle_template
        self._preset_template = preset_template
        self._path_template = path_template
        self._line_template = line_template
        self._picture_template = picture_template
        self._path_generator = path_generator
        self._policy_for = policy_for
        self._register_media = register_media
        self._trace_writer = trace_writer
        self._animation_pipeline = animation_pipeline
        self._rasterizer = rasterizer
        self._rasterizer_provider = rasterizer_provider
        self._logger = logger

    def _resolve_rasterizer(self) -> Rasterizer | None:
        if self._rasterizer is None and self._rasterizer_provider is not None:
            self._rasterizer = self._rasterizer_provider()
        return self._rasterizer


__all__ = ["DrawingMLShapeRenderer"]
