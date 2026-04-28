"""Shared PatternPaint merge helpers for style/resvg bridges."""

from __future__ import annotations

from dataclasses import replace

from svg2ooxml.ir.paint import PatternPaint


def merge_pattern_paint(
    runtime_paint: PatternPaint,
    analyzed_paint: PatternPaint,
) -> PatternPaint:
    return replace(
        runtime_paint,
        preset=analyzed_paint.preset or runtime_paint.preset,
        foreground=analyzed_paint.foreground or runtime_paint.foreground,
        background=analyzed_paint.background or runtime_paint.background,
        background_opacity=analyzed_paint.background_opacity,
        foreground_theme_color=analyzed_paint.foreground_theme_color
        or runtime_paint.foreground_theme_color,
        background_theme_color=analyzed_paint.background_theme_color
        or runtime_paint.background_theme_color,
        tile_image=analyzed_paint.tile_image or runtime_paint.tile_image,
        tile_width_px=analyzed_paint.tile_width_px or runtime_paint.tile_width_px,
        tile_height_px=analyzed_paint.tile_height_px or runtime_paint.tile_height_px,
    )


__all__ = ["merge_pattern_paint"]
