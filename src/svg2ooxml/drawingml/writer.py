"""DrawingML writer that renders IR scenes to slide XML fragments."""

from __future__ import annotations

from .generator import EMU_PER_PX, px_to_emu  # noqa: F401
from .mask_alpha import apply_mask_alpha as _apply_mask_alpha  # noqa: F401
from .result import DrawingMLRenderResult
from .writer_base import DEFAULT_SLIDE_SIZE, DrawingMLWriterBase
from .writer_elements import DrawingMLElementMixin
from .writer_scene import DrawingMLSceneMixin


class DrawingMLWriter(
    DrawingMLWriterBase,
    DrawingMLSceneMixin,
    DrawingMLElementMixin,
):
    """Render IR scene graphs into DrawingML shape fragments."""


__all__ = ["DrawingMLWriter", "DrawingMLRenderResult", "DEFAULT_SLIDE_SIZE", "EMU_PER_PX"]
