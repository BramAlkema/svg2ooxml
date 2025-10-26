"""Filesystem-backed font provider."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List

from ..service import FontMatch, FontProvider, FontQuery

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}


@dataclass
class DirectoryFontProvider(FontProvider):
    """Resolve fonts by scanning directories for font files."""

    roots: tuple[Path, ...]

    def __post_init__(self) -> None:
        normalised: List[Path] = []
        for root in self.roots:
            resolved = root.expanduser()
            if resolved.exists() and resolved.is_dir():
                normalised.append(resolved.resolve())
        self._roots = tuple(normalised)
        self._index: Dict[str, List[FontMatch]] | None = None

    def resolve(self, query: FontQuery) -> FontMatch | None:
        index = self._ensure_index()
        for family in self._candidate_families(query):
            matches = index.get(family.lower())
            if not matches:
                continue
            # Prefer a match with compatible weight/style if available.
            for match in matches:
                if _weight_compatible(match.weight, query.weight) and _style_compatible(match.style, query.style):
                    return match
            return matches[0]
        return None

    def list_alternatives(self, query: FontQuery) -> Iterable[FontMatch]:
        index = self._ensure_index()
        yielded: set[str] = set()
        for family in self._candidate_families(query):
            matches = index.get(family.lower())
            if not matches:
                continue
            for match in matches:
                key = match.path or ""
                if key in yielded:
                    continue
                yielded.add(key)
                yield match

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_index(self) -> Dict[str, List[FontMatch]]:
        if self._index is not None:
            return self._index
        index: Dict[str, List[FontMatch]] = {}
        for root in self._roots:
            for path in self._iter_fonts(root):
                match = _match_from_path(path)
                index.setdefault(match.family.lower(), []).append(match)
        self._index = index
        return index

    def _iter_fonts(self, root: Path) -> Iterator[Path]:
        try:
            for entry in root.rglob("*"):
                if entry.is_file() and entry.suffix.lower() in FONT_EXTENSIONS:
                    yield entry
        except Exception:
            return

    @staticmethod
    def _candidate_families(query: FontQuery) -> Iterator[str]:
        yield query.family
        for fallback in query.fallback_chain:
            if fallback.lower() != query.family.lower():
                yield fallback


def _match_from_path(path: Path) -> FontMatch:
    name = path.stem.replace("_", " ")
    family = _derive_family(name)
    weight = 700 if "bold" in name.lower() else 400
    style = "italic" if any(token in name.lower() for token in ("italic", "oblique")) else "normal"
    metadata = {
        "source": "directory",
        "filename": path.name,
        "directory": str(path.parent),
    }
    return FontMatch(
        family=family,
        path=str(path),
        weight=weight,
        style=style,
        found_via="directory",
        metadata=metadata,
    )


def _derive_family(name: str) -> str:
    if "-" in name:
        return name.split("-", 1)[0]
    if " Bold" in name:
        return name.replace(" Bold", "")
    if " Italic" in name:
        return name.replace(" Italic", "")
    return name


def _weight_compatible(found: int, requested: int) -> bool:
    return (found >= 700 and requested >= 700) or (found < 700 and requested < 700)


def _style_compatible(found: str, requested: str) -> bool:
    return (found.lower() == "italic" and requested.lower() == "italic") or (
        found.lower() == "normal" and requested.lower() == "normal"
    )


__all__ = ["DirectoryFontProvider"]
