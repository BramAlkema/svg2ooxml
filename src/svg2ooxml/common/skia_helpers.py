"""Small Skia adapter helpers without importing optional Skia eagerly."""

from __future__ import annotations


def tile_mode(skia_module, spread_method: str | None):
    """Resolve an SVG spread method to a Skia tile mode."""

    if spread_method == "repeat":
        return skia_module.TileMode.kRepeat
    if spread_method == "reflect":
        return skia_module.TileMode.kMirror
    return skia_module.TileMode.kClamp


__all__ = ["tile_mode"]
