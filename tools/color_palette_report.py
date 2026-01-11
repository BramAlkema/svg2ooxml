#!/usr/bin/env python3
"""
Palette analysis helper for developers.

This script relies on the optional colour stack (`pip install -e .[color]`) and,
when installed, surfaces harmony suggestions and perceptual palette metrics.
Run `python tools/color_palette_report.py --help` for usage instructions.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable, Sequence

from svg2ooxml.color.analysis import summarize_palette
from svg2ooxml.color.bridge import (
    ADVANCED_COLOR_ENGINE_AVAILABLE,
    ensure_advanced_color_engine,
    to_advanced_color,
)
from svg2ooxml.color.models import Color
from svg2ooxml.color.advanced.batch import ColorBatch
from svg2ooxml.color.advanced.engine import AdvancedColor
from svg2ooxml.color.advanced.harmony import ColorHarmony
from svg2ooxml.color.parsers import parse_color

try:  # Pillow is optional but required for image sampling.
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore[assignment]


def _sample_image(path: str, *, max_samples: int = 4096) -> list[Color]:
    if Image is None:
        raise RuntimeError("Pillow is required to sample images. Install with `pip install pillow`.")
    with Image.open(path) as image:
        working = image.convert("RGBA")
        width, height = working.size
        total_pixels = width * height
        if total_pixels > max_samples:
            scale = (max_samples / float(total_pixels)) ** 0.5
            new_width = max(1, int(width * scale))
            new_height = max(1, int(height * scale))
            resampling = getattr(Image, "Resampling", None)
            resample_filter = getattr(resampling, "BILINEAR", Image.BILINEAR) if resampling else Image.BILINEAR
            working = working.resize((new_width, new_height), resample_filter)
        pixels = list(working.getdata())

    colours: list[Color] = []
    for pixel in pixels:
        if len(pixel) == 4:
            r, g, b, a = pixel
        elif len(pixel) == 3:
            r, g, b = pixel
            a = 255
        else:
            continue
        colours.append(Color(r / 255.0, g / 255.0, b / 255.0, a / 255.0))
    return colours


def _prepare_colours(raw_values: Sequence[str]) -> list[Color]:
    colours: list[Color] = []
    for value in raw_values:
        value = value.strip()
        if not value:
            continue
        parsed = parse_color(value)
        if parsed is None:
            raise ValueError(f"Could not parse colour value: {value!r}")
        colours.append(parsed)
    return colours


def _format_hex(value: Color | AdvancedColor) -> str:
    if isinstance(value, AdvancedColor):
        return value.hex(include_hash=True).upper()
    include_alpha = value.a < 1.0
    return value.to_hex(include_alpha=include_alpha).upper()


def _report_palette(colours: Sequence[Color]) -> tuple[str, dict[str, object]]:
    stats = summarize_palette(colours)
    lines: list[str] = []
    lines.append("Palette Summary")
    lines.append("----------------")
    lines.append(f"Count: {stats['count']} (unique: {stats['unique']})")
    lines.append(f"Palette: {', '.join(stats['palette']) or '—'}")
    lines.append(f"Has transparency: {bool(stats.get('has_transparency'))}")
    lines.append(f"Recommended colour space: {stats.get('recommended_space', 'srgb')}")
    lines.append(f"Max OKLab distance: {stats.get('max_oklab_distance', 0):.4f}")
    lines.append(f"Complexity: {stats.get('complexity', 0):.3f}")

    if stats.get("advanced_available"):
        mean_l, mean_c, mean_h = stats.get("mean_oklch", (0.0, 0.0, 0.0))
        lines.append("")
        lines.append("Advanced Metrics")
        lines.append("----------------")
        lines.append(f"Mean OKLCh: L={mean_l:.3f}, C={mean_c:.3f}, h={mean_h:.2f}")
        lines.append(f"Hue spread: {stats.get('hue_spread', 0.0):.2f}")
        lines.append(f"Saturation variance: {stats.get('saturation_variance', 0.0):.5f}")
        lines.append(f"Lightness stddev: {stats.get('lightness_std', 0.0):.5f}")
        if stats.get("harmony_suggestions"):
            lines.append(f"Harmony suggestions: {', '.join(stats['harmony_suggestions'])}")
        if stats.get("pairwise_contrast") is not None:
            lines.append(f"Contrast (first pair): {stats['pairwise_contrast']:.2f}:1")
        if stats.get("lighten_preview"):
            lines.append(f"Lighten preview: {', '.join(stats['lighten_preview'])}")
        if stats.get("saturate_preview"):
            lines.append(f"Saturate preview: {', '.join(stats['saturate_preview'])}")

    return "\n".join(lines), stats


def _convert_to_advanced(colours: Sequence[Color]) -> list[AdvancedColor]:
    advanced: list[AdvancedColor] = []
    if not ADVANCED_COLOR_ENGINE_AVAILABLE:
        return advanced
    try:
        ensure_advanced_color_engine()
    except RuntimeError:
        return []

    for colour in colours:
        try:
            advanced.append(to_advanced_color(colour))
        except Exception:
            continue
    return advanced


def _report_harmonies(colours: Sequence[Color]) -> str | None:
    advanced_colours = _convert_to_advanced(colours[:1])
    if not advanced_colours:
        return None

    base = advanced_colours[0]
    harmony = ColorHarmony(base)
    complementary = _format_hex(harmony.complementary())
    analogous = [_format_hex(color) for color in harmony.analogous(count=5)]
    triadic = [_format_hex(color) for color in harmony.triadic()]

    lines = []
    lines.append("Harmony")
    lines.append("-------")
    lines.append(f"Base colour: {_format_hex(base)}")
    lines.append(f"Complementary: {complementary}")
    lines.append(f"Analogous (5): {', '.join(analogous)}")
    lines.append(f"Triadic: {', '.join(triadic)}")
    return "\n".join(lines)


def _report_batch(colours: Sequence[Color]) -> str | None:
    advanced_colours = _convert_to_advanced(colours)
    if not advanced_colours:
        return None

    try:
        batch = ColorBatch(advanced_colours)
        lightened = batch.lighten(0.1).to_colors()
        saturated = batch.saturate(0.15).to_colors()
    except Exception:  # pragma: no cover - batch operations are optional
        return None

    lines = []
    lines.append("Batch transforms")
    lines.append("----------------")
    lines.append(f"Lighten(+0.1): {', '.join(_format_hex(color) for color in lightened)}")
    lines.append(f"Saturate(+0.15): {', '.join(_format_hex(color) for color in saturated)}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyse colour palettes using svg2ooxml's advanced engine.")
    parser.add_argument(
        "--image",
        type=str,
        help="Optional image to sample colours from (requires Pillow).",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=4096,
        help="Maximum number of pixels to sample from the image (default: 4096).",
    )
    parser.add_argument(
        "colours",
        nargs="*",
        help="Individual colour values (hex, rgb(), named). If omitted, --image must be provided.",
    )

    args = parser.parse_args(argv)

    colours: list[Color] = []
    if args.image:
        if not os.path.exists(args.image):
            parser.error(f"Image path does not exist: {args.image}")
        colours.extend(_sample_image(args.image, max_samples=args.max_samples))
    if args.colours:
        try:
            colours.extend(_prepare_colours(args.colours))
        except ValueError as exc:
            parser.error(str(exc))

    if not colours:
        parser.error("Provide at least one colour value or an image to analyse.")

    palette_report, stats = _report_palette(colours)
    print(palette_report)
    print()

    harmony_report = _report_harmonies(colours)
    if harmony_report:
        print(harmony_report)
        print()

    batch_report = _report_batch(colours[: min(len(colours), 8)])
    if batch_report:
        print(batch_report)
        print()

    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    sys.exit(main())
