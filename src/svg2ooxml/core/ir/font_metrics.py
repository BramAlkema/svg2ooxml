"""Font metrics resolution and text width estimation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import TYPE_CHECKING, Any

from svg2ooxml.services.fonts.fontforge_utils import (
    FONTFORGE_AVAILABLE,
    open_font,
)

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.ir.text import Run


@dataclass(frozen=True)
class FontMetrics:
    units_per_em: int
    cmap: dict[int, str]
    advances: dict[str, int]
    default_advance: float
    ascender: int
    descender: int
    line_gap: int


_FONT_METRICS_CACHE: dict[str, FontMetrics] = {}
_FONT_METRICS_MISS: set[str] = set()


def _metrics_cache_key(path: str | None, font_data: bytes | None) -> str | None:
    if font_data is not None:
        return f"data:{sha1(font_data).hexdigest()}"
    if path:
        return path
    return None


def load_font_metrics(path: str | None, font_data: bytes | None = None) -> FontMetrics | None:
    cache_key = _metrics_cache_key(path, font_data)
    if cache_key and cache_key in _FONT_METRICS_CACHE:
        return _FONT_METRICS_CACHE[cache_key]
    if not FONTFORGE_AVAILABLE:
        return None
    if cache_key and cache_key in _FONT_METRICS_MISS:
        return None

    source = font_data if font_data is not None else path
    if source is None:
        return None

    suffix = ".ttf"
    if font_data is None and path:
        suffix = Path(path).suffix or ".ttf"

    try:
        with open_font(source, suffix=suffix) as font:
            units_per_em = int(getattr(font, "em", 1000) or getattr(font, "emsize", 1000) or 1000)
            cmap: dict[int, str] = {}
            advances: dict[str, int] = {}

            glyphs = getattr(font, "glyphs", None)
            if callable(glyphs):
                for glyph in font.glyphs():
                    glyph_name = getattr(glyph, "glyphname", None)
                    if glyph_name:
                        width = getattr(glyph, "width", None)
                        if isinstance(width, (int, float)):
                            advances[glyph_name] = int(width)
                    codepoint = getattr(glyph, "unicode", None)
                    if isinstance(codepoint, int) and codepoint >= 0 and glyph_name:
                        cmap[codepoint] = glyph_name

            if "space" in advances:
                default_advance = float(advances["space"])
            elif advances:
                default_advance = float(sum(advances.values()) / max(1, len(advances)))
            else:
                default_advance = float(units_per_em) * 0.5

            ascender = int(getattr(font, "ascent", units_per_em * 0.8))
            descender_raw = getattr(font, "descent", units_per_em * 0.2)
            descender = -abs(int(descender_raw))
            line_gap = int(getattr(font, "os2_typolinegap", 0) or 0)
    except Exception:
        if cache_key:
            _FONT_METRICS_MISS.add(cache_key)
        return None

    metrics = FontMetrics(
        units_per_em=max(1, units_per_em),
        cmap=cmap,
        advances=advances,
        default_advance=default_advance,
        ascender=ascender,
        descender=descender,
        line_gap=line_gap,
    )
    if cache_key:
        _FONT_METRICS_CACHE[cache_key] = metrics
    return metrics


def resolve_font_metrics(font_service: Any | None, run: Run) -> FontMetrics | None:
    if font_service is None or not hasattr(font_service, "find_font"):
        return None
    try:
        from svg2ooxml.services.fonts import FontQuery
    except Exception:
        return None

    family = (run.font_family or "Arial").split(",")[0].strip().strip('"\'')
    weight = 700 if run.bold else 400
    style = "italic" if run.italic else "normal"

    try:
        query = FontQuery(family=family, weight=weight, style=style)
        match = font_service.find_font(query)
    except Exception:
        return None

    if match is None:
        return None

    font_data = None
    if isinstance(match.metadata, dict):
        data = match.metadata.get("font_data")
        if isinstance(data, (bytes, bytearray)):
            font_data = bytes(data)

    path = str(match.path) if getattr(match, "path", None) else None
    if path is None and font_data is None:
        return None
    return load_font_metrics(path, font_data)


def estimate_run_width(text: str, run: Run, font_service: Any | None) -> float:
    font_px = run.font_size_pt * (96.0 / 72.0)
    if font_px <= 0:
        return 0.0

    metrics = resolve_font_metrics(font_service, run)
    if metrics is None:
        return len(text) * font_px * 0.6

    width_units = 0.0
    for ch in text:
        if ch == "\n":
            continue
        glyph_name = metrics.cmap.get(ord(ch))
        if glyph_name is None:
            width_units += metrics.default_advance
            continue
        width_units += metrics.advances.get(glyph_name, metrics.default_advance)

    return (width_units / metrics.units_per_em) * font_px


__all__ = ["FontMetrics", "load_font_metrics", "resolve_font_metrics", "estimate_run_width"]
