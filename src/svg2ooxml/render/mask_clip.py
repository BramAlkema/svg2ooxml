"""Mask and clip rasterisation scaffolding."""

from __future__ import annotations

import numpy as np

from .geometry import Tessellator
from .rasterizer import Rasterizer, Viewport
from .surface import Surface


def rasterize_mask(node, tree, *, tessellator: Tessellator, rasterizer: Rasterizer, viewport: Viewport) -> np.ndarray:
    """Return an alpha mask sampled into a NumPy array.

    Placeholder returning NotImplemented until the render refactor supplies a
    real implementation.
    """

    raise NotImplementedError("Mask rasterisation will be ported from pyportresvg.")


def rasterize_clip(node, tree, *, tessellator: Tessellator, rasterizer: Rasterizer, viewport: Viewport) -> np.ndarray:
    """Return a boolean clip mask."""

    raise NotImplementedError("Clip rasterisation will be ported from pyportresvg.")


def export_mask_png(alpha: np.ndarray) -> bytes:
    """Encode a mask array to PNG bytes."""

    raise NotImplementedError("PNG encoding will be added alongside mask rasterisation.")


__all__ = ["rasterize_mask", "rasterize_clip", "export_mask_png"]

