"""Web font provider for @font-face rules extracted from SVG."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Iterable

from ..service import FontMatch, FontProvider, FontQuery

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.ir.fonts import FontFaceRule, FontFaceSrc
    from svg2ooxml.services.fonts.loader import FontLoader, LoadedFont

logger = logging.getLogger(__name__)


@dataclass
class WebFontProvider(FontProvider):
    """Resolve fonts from @font-face rules extracted during SVG parsing.

    This provider matches font queries against FontFaceRule objects
    parsed from <style> elements in SVG documents.

    Optionally loads and caches font data when a FontLoader is provided.
    """

    rules: tuple["FontFaceRule", ...]
    loader: "FontLoader | None" = None
    enable_loading: bool = True  # Load fonts on demand
    cache_loaded_fonts: bool = True  # Cache loaded font data

    def __post_init__(self) -> None:
        """Build lookup index for fast resolution."""
        # Index: family.lower() -> list of rules with that family
        self._index: dict[str, list[FontFaceRule]] = {}
        for rule in self.rules:
            family_key = rule.normalized_family
            self._index.setdefault(family_key, []).append(rule)

        # Font data cache: (family, weight, style) -> LoadedFont
        self._font_cache: dict[tuple[str, int, str], "LoadedFont"] = {}

    def resolve(self, query: FontQuery) -> FontMatch | None:
        """Return the best matching web font for the query.

        Matching algorithm:
        1. Try exact family match
        2. Filter by weight and style
        3. Return highest priority match (first src with compatible format)

        Args:
            query: Font query with desired attributes

        Returns:
            FontMatch if a compatible web font is found, None otherwise
        """
        family_key = query.family.lower().strip('"').strip("'")
        rules = self._index.get(family_key)
        if not rules:
            return None

        # Find best rule match based on weight and style
        best_rule = self._find_best_rule(rules, query)
        if not best_rule:
            return None

        # Convert to FontMatch
        return self._rule_to_match(best_rule, query)

    def list_alternatives(self, query: FontQuery) -> Iterable[FontMatch]:
        """Yield all compatible web font matches for the query.

        Args:
            query: Font query with desired attributes

        Yields:
            FontMatch objects in priority order
        """
        family_key = query.family.lower().strip('"').strip("'")
        rules = self._index.get(family_key)
        if not rules:
            return

        # Score and sort all rules
        scored = [
            (self._score_rule(rule, query), rule)
            for rule in rules
        ]
        scored.sort(key=lambda x: x[0], reverse=True)

        # Yield matches in score order
        for score, rule in scored:
            if score > 0:  # Only yield compatible matches
                yield self._rule_to_match(rule, query, score=score)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_best_rule(
        self, rules: list["FontFaceRule"], query: FontQuery
    ) -> "FontFaceRule | None":
        """Find the rule that best matches the query."""
        best_score = 0.0
        best_rule = None

        for rule in rules:
            score = self._score_rule(rule, query)
            if score > best_score:
                best_score = score
                best_rule = rule

        return best_rule

    def _score_rule(self, rule: "FontFaceRule", query: FontQuery) -> float:
        """Calculate compatibility score for a rule.

        Score components:
        - Exact weight match: +1.0
        - Weight in same category (bold vs normal): +0.5
        - Exact style match: +0.5
        - Has compatible format: +0.3
        - Base score for family match: +0.1

        Returns:
            Score >= 0.0, higher is better match
        """
        score = 0.1  # Base score for family match

        # Weight scoring
        rule_weight = rule.weight_numeric
        if rule_weight == query.weight:
            score += 1.0  # Exact match
        elif self._weight_compatible(rule_weight, query.weight):
            score += 0.5  # Compatible category

        # Style scoring
        rule_style = rule.style.lower()
        query_style = query.style.lower()
        if rule_style == query_style:
            score += 0.5  # Exact match
        elif rule_style == "normal" and query_style not in ("italic", "oblique"):
            score += 0.3  # Compatible

        # Format availability (prefer web-compatible formats)
        if self._has_compatible_format(rule):
            score += 0.3

        return score

    def _weight_compatible(self, rule_weight: int, query_weight: int) -> bool:
        """Check if weights are in the same category (bold vs normal)."""
        return (rule_weight >= 600 and query_weight >= 600) or (
            rule_weight < 600 and query_weight < 600
        )

    def _has_compatible_format(self, rule: "FontFaceRule") -> bool:
        """Check if rule has web-compatible font formats."""
        compatible_formats = {"woff", "woff2", "truetype", "opentype", "svg"}
        for src in rule.src:
            if src.format and src.format.lower() in compatible_formats:
                return True
            # No format specified - assume compatible
            if not src.format and not src.is_local:
                return True
        return False

    def _rule_to_match(
        self,
        rule: "FontFaceRule",
        query: FontQuery,
        score: float | None = None,
    ) -> FontMatch:
        """Convert FontFaceRule to FontMatch.

        Uses the first src in the src chain (highest priority).
        Optionally loads font data if loader is configured.
        """
        # Try to load font from src chain (try each src until one succeeds)
        loaded_font = None
        primary_src = None

        if self.enable_loading and self.loader:
            # Try loading from cache first
            cache_key = (
                rule.normalized_family,
                rule.weight_numeric,
                rule.style.lower(),
            )

            if self.cache_loaded_fonts and cache_key in self._font_cache:
                loaded_font = self._font_cache[cache_key]
                logger.debug("Using cached font: %s", rule.family)
            else:
                # Try each src in order until one loads successfully
                for src in rule.src:
                    try:
                        loaded_font = self.loader.load_from_src(src)
                        if loaded_font:
                            primary_src = src
                            # Cache the loaded font
                            if self.cache_loaded_fonts:
                                self._font_cache[cache_key] = loaded_font
                            logger.debug(
                                "Loaded web font: %s (%d bytes, format=%s)",
                                rule.family,
                                loaded_font.size_bytes,
                                loaded_font.format,
                            )
                            break
                    except Exception as exc:
                        logger.debug(
                            "Failed to load font from %s: %s",
                            src.url[:50],
                            exc
                        )
                        continue

        # Fall back to first src if loading disabled or failed
        if not primary_src:
            primary_src = rule.src[0] if rule.src else None

        # Extract URL and metadata
        url = primary_src.url if primary_src else None
        format_hint = primary_src.format if primary_src else None

        # Determine embedding permission
        # Data URIs and remote URLs: embedding allowed
        # Local fonts: embedding not allowed (system font)
        embedding_allowed = True
        if primary_src and primary_src.url.startswith("local("):
            embedding_allowed = False

        metadata: dict[str, object] = {
            "source": "webfont",
            "format": format_hint,
            "font_display": rule.display,
            "unicode_range": rule.unicode_range,
            "src_count": len(rule.src),
        }

        if primary_src:
            metadata["is_data_uri"] = primary_src.is_data_uri
            metadata["is_remote"] = primary_src.is_remote
            metadata["is_local"] = primary_src.is_local

        # Add loaded font data to metadata if available
        if loaded_font:
            metadata["loaded"] = True
            metadata["font_data"] = loaded_font.data
            metadata["decompressed"] = loaded_font.decompressed
            metadata["loaded_format"] = loaded_font.format
            metadata["loaded_size_bytes"] = loaded_font.size_bytes
            # Update path to reflect actual loaded source
            if primary_src:
                url = loaded_font.source_url
        else:
            metadata["loaded"] = False

        if score is None:
            score = self._score_rule(rule, query)

        return FontMatch(
            family=rule.family,
            path=url,  # URL or loaded source URL
            weight=rule.weight_numeric,
            style=rule.style,
            found_via="webfont",
            score=score,
            embedding_allowed=embedding_allowed,
            metadata=metadata,
        )

    def clear_cache(self) -> None:
        """Clear the loaded font cache."""
        self._font_cache.clear()
        logger.debug("Cleared web font cache")

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats (size, total_bytes)
        """
        total_bytes = sum(
            font.size_bytes
            for font in self._font_cache.values()
        )
        return {
            "cached_fonts": len(self._font_cache),
            "total_bytes": total_bytes,
        }


__all__ = ["WebFontProvider"]
