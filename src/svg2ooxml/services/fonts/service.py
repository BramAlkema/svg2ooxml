"""High-level font lookup service used during conversion."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol


@dataclass(frozen=True)
class FontQuery:
    """Describe the desired font attributes for mapping SVG runs."""

    family: str
    weight: int = 400
    style: str = "normal"
    stretch: str = "normal"
    language: str | None = None
    fallback_chain: tuple[str, ...] = ()


@dataclass(frozen=True)
class FontMatch:
    """Represents the resolved font along with diagnostic metadata."""

    family: str
    path: str | None
    weight: int
    style: str
    found_via: str
    score: float = 0.0
    embedding_allowed: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)


class FontProvider(Protocol):
    """Pluggable source capable of resolving fonts."""

    def resolve(self, query: FontQuery) -> FontMatch | None:  # pragma: no cover - protocol shim
        ...

    def list_alternatives(self, query: FontQuery) -> Iterable[FontMatch]:  # pragma: no cover
        ...


class FontService:
    """Aggregate registered font providers and cache lookup results."""

    def __init__(self) -> None:
        self._providers: list[FontProvider] = []
        self._cache: dict[FontQuery, FontMatch | None] = {}

    # ------------------------------------------------------------------
    # Provider registration
    # ------------------------------------------------------------------

    def register_provider(self, provider: FontProvider) -> None:
        """Add a provider to the resolution chain (at the end)."""

        if provider in self._providers:
            return
        self._providers.append(provider)

    def prepend_provider(self, provider: FontProvider) -> None:
        """Add a provider to the front of the resolution chain (highest priority).

        Use this for document-specific fonts that should override system fonts.
        """
        if provider in self._providers:
            return
        self._providers.insert(0, provider)

    def iter_providers(self) -> Iterator[FontProvider]:
        return iter(self._providers)

    # ------------------------------------------------------------------
    # Lookup APIs
    # ------------------------------------------------------------------

    def find_font(self, query: FontQuery) -> FontMatch | None:
        """Return the first matching font for the requested attributes."""

        for probe in self._expand_queries(query):
            if probe in self._cache:
                cached = self._cache[probe]
                if cached is not None:
                    return cached
                continue

            match = self._resolve_once(probe)
            self._cache[probe] = match
            if match is not None:
                return match
        return None

    def iter_alternatives(self, query: FontQuery) -> Iterator[FontMatch]:
        """Yield candidate matches ordered by provider preference."""

        yielded: set[str] = set()
        for probe in self._expand_queries(query):
            for provider in self._providers:
                for match in provider.list_alternatives(probe):
                    key = match.path or f"{match.family}:{match.style}:{match.weight}"
                    if key in yielded:
                        continue
                    yielded.add(key)
                    yield match

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        self._cache.clear()

    def clone(self) -> FontService:
        """Create a shallow clone with the same providers but empty cache.

        Used for per-parse isolation to prevent cache pollution across documents.
        """
        cloned = FontService()
        cloned._providers = list(self._providers)  # Shallow copy of provider list
        return cloned

    def _resolve_once(self, query: FontQuery) -> FontMatch | None:
        for provider in self._providers:
            match = provider.resolve(query)
            if match is not None:
                return match
        return None

    def _expand_queries(self, query: FontQuery) -> Iterator[FontQuery]:
        yield query
        for fallback in query.fallback_chain:
            if fallback.lower() == query.family.lower():
                continue
            yield replace(query, family=fallback, fallback_chain=())
        # Inject visually similar fonts when explicit fallbacks don't resolve
        from svg2ooxml.services.fonts.similarity import get_similar_fonts

        seen = {query.family.lower()} | {f.lower() for f in query.fallback_chain}
        for similar in get_similar_fonts(query.family):
            if similar.lower() not in seen:
                seen.add(similar.lower())
                yield replace(query, family=similar, fallback_chain=())


__all__ = ["FontService", "FontProvider", "FontQuery", "FontMatch"]
