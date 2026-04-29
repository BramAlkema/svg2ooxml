"""Surface seeding and EMF wrapping helpers for resvg filter promotion."""

from __future__ import annotations

import struct
from typing import Any

from svg2ooxml.common.numpy_compat import require_numpy
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.io.emf.blob import EMFBlob
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.render.filters import FilterPlan
from svg2ooxml.render.rasterizer import Viewport
from svg2ooxml.render.surface import Surface
from svg2ooxml.services.filter_types import FilterEffectResult

np = require_numpy("Filter raster bridging requires NumPy; install the 'render' extra.")


def seed_source_surface(width: int, height: int) -> Surface:
    """Create a synthetic RGBA source surface for resvg evaluation."""
    width = max(1, width)
    height = max(1, height)
    surface = Surface.make(width, height)
    xs = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]

    red = 0.15 + 0.75 * xs
    green = 0.2 + 0.6 * (1.0 - ys)
    radial = np.sqrt((xs - 0.5) ** 2 + (ys - 0.5) ** 2)
    blue = np.clip(0.9 - 0.8 * radial, 0.1, 0.9)

    base_alpha = np.clip(0.6 + 0.4 * (1.0 - radial * 1.2), 0.25, 1.0)
    stripe = ((xs + ys) % 0.25) < 0.02
    base_alpha = np.where(stripe, np.minimum(base_alpha, 0.4), base_alpha)

    surface.data[..., 0] = red
    surface.data[..., 1] = green
    surface.data[..., 2] = blue
    surface.data[..., 3] = base_alpha
    surface.data[..., :3] *= surface.data[..., 3:4]
    return surface


def surface_to_bmp(surface: Surface) -> bytes:
    """Convert a float32 RGBA surface to a 24-bit BMP byte string."""
    data = np.clip(surface.data, 0.0, 1.0)
    rgb = data[..., :3]
    alpha = data[..., 3:4]
    safe_alpha = np.where(alpha > 1e-6, alpha, 1.0)
    unpremult = np.where(alpha > 1e-6, rgb / safe_alpha, 0.0)
    unpremult = np.clip(unpremult, 0.0, 1.0)
    bgr = (unpremult[..., ::-1] * 255.0 + 0.5).astype(np.uint8)
    height, width = bgr.shape[:2]
    row_stride = (width * 3 + 3) & ~3
    padding = row_stride - width * 3
    pad_bytes = b"\x00" * padding
    rows = []
    for y in range(height - 1, -1, -1):
        rows.append(bgr[y].tobytes() + pad_bytes)
    pixel_data = b"".join(rows)
    header_size = 40
    dib_header = struct.pack(
        "<IIIHHIIIIII",
        header_size,
        width,
        height,
        1,
        24,
        0,
        len(pixel_data),
        int(96 / 0.0254),
        int(96 / 0.0254),
        0,
        0,
    )
    file_header = b"BM" + struct.pack(
        "<IHHI",
        14 + len(dib_header) + len(pixel_data),
        0,
        0,
        14 + len(dib_header),
    )
    return file_header + dib_header + pixel_data


def turbulence_emf_effect(
    surface: Surface,
    viewport: Viewport,
    plan: FilterPlan,
    filter_id: str,
) -> FilterEffectResult:
    """Wrap a turbulence result surface into an EMF-backed effect."""
    width_px = max(1, int(round(viewport.width)))
    height_px = max(1, int(round(viewport.height)))
    bmp_bytes = surface_to_bmp(surface)
    width_emu = max(1, int(round(px_to_emu(width_px))))
    height_emu = max(1, int(round(px_to_emu(height_px))))
    blob = EMFBlob(width_emu=width_emu, height_emu=height_emu)
    blob.draw_bitmap(
        0,
        0,
        width_emu,
        height_emu,
        0,
        0,
        width_px,
        height_px,
        bmp_bytes,
    )
    emf_bytes = blob.finalize()
    metadata: dict[str, Any] = {
        "renderer": "resvg",
        "resvg_promotion": "emf",
        "promotion_source": "resvg",
        "promotion_primitives": [primitive.tag for primitive in plan.primitives],
        "fallback_assets": [
            {
                "type": "emf",
                "format": "emf",
                "data": emf_bytes,
                "width_px": width_px,
                "height_px": height_px,
            }
        ],
        "turbulence_emf": True,
        "filter_id": filter_id,
    }
    effect = CustomEffect(drawingml="")
    return FilterEffectResult(effect=effect, strategy="vector", metadata=metadata, fallback="emf")



__all__ = [
    "seed_source_surface",
    "surface_to_bmp",
    "turbulence_emf_effect",
]
