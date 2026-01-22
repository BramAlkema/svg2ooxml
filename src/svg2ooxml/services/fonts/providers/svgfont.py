"""SVG <font> provider with on-the-fly conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from svg2ooxml.ir.fonts import SvgFontDefinition
from svg2ooxml.services.fonts.service import FontMatch, FontProvider, FontQuery
from svg2ooxml.services.fonts.svg_font_converter import convert_svg_font


@dataclass
class SvgFontProvider(FontProvider):
    """Resolve inline SVG fonts by converting them to TTF on demand."""

    fonts: tuple[SvgFontDefinition, ...]
    cache_converted: bool = True

    def __post_init__(self) -> None:
        self._index: dict[str, list[SvgFontDefinition]] = {}
        for font in self.fonts:
            self._index.setdefault(font.normalized_family, []).append(font)
        self._cache: dict[tuple[str, int, str], bytes] = {}

    def resolve(self, query: FontQuery) -> FontMatch | None:
        family_key = query.family.lower().strip('"').strip("'")
        candidates = self._index.get(family_key)
        if not candidates:
            return None
        best = self._best_match(candidates, query)
        if best is None:
            return None
        font_bytes = self._load_font_bytes(best, query)
        if font_bytes is None:
            return None
        key = self._cache_key(best, query)
        pseudo_path = f"svgfont://{family_key}/{key}"
        metadata = {
            "source": "svgfont",
            "font_data": font_bytes,
            "loaded_format": "ttf",
            "loaded": True,
        }
        if best.source:
            metadata["svg_source"] = best.source
        return FontMatch(
            family=best.family,
            path=pseudo_path,
            weight=best.weight_numeric,
            style=best.style,
            found_via="svgfont",
            score=1.0,
            embedding_allowed=True,
            metadata=metadata,
        )

    def list_alternatives(self, query: FontQuery) -> Iterable[FontMatch]:
        family_key = query.family.lower().strip('"').strip("'")
        candidates = self._index.get(family_key)
        if not candidates:
            return
        for candidate in candidates:
            font_bytes = self._load_font_bytes(candidate, query)
            if font_bytes is None:
                continue
            key = self._cache_key(candidate, query)
            pseudo_path = f"svgfont://{family_key}/{key}"
            yield FontMatch(
                family=candidate.family,
                path=pseudo_path,
                weight=candidate.weight_numeric,
                style=candidate.style,
                found_via="svgfont",
                score=1.0,
                embedding_allowed=True,
                metadata={
                    "source": "svgfont",
                    "font_data": font_bytes,
                    "loaded_format": "ttf",
                    "loaded": True,
                    "svg_source": candidate.source,
                },
            )

    def _best_match(
        self,
        candidates: list[SvgFontDefinition],
        query: FontQuery,
    ) -> SvgFontDefinition | None:
        best_score = -1.0
        best = None
        for candidate in candidates:
            score = 0.0
            if candidate.weight_numeric == query.weight:
                score += 1.0
            elif self._weight_compatible(candidate.weight_numeric, query.weight):
                score += 0.5
            if candidate.style.lower() == query.style.lower():
                score += 0.3
            if score > best_score:
                best_score = score
                best = candidate
        return best

    def _load_font_bytes(self, font: SvgFontDefinition, query: FontQuery) -> bytes | None:
        key = self._cache_key(font, query)
        if self.cache_converted and key in self._cache:
            return self._cache[key]
        converted = convert_svg_font(font.svg_data)
        if converted is None:
            return None
        if self.cache_converted:
            self._cache[key] = converted
        return converted

    @staticmethod
    def _weight_compatible(weight_a: int, weight_b: int) -> bool:
        return (weight_a >= 600 and weight_b >= 600) or (
            weight_a < 600 and weight_b < 600
        )

    @staticmethod
    def _cache_key(font: SvgFontDefinition, query: FontQuery) -> tuple[str, int, str]:
        return (font.normalized_family, query.weight, query.style.lower())


__all__ = ["SvgFontProvider"]
