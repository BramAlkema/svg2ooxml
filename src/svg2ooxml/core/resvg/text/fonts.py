"""Font resolver that respects pyportresvg feature flags."""

from __future__ import annotations

import mmap
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from ..config import Config, DEFAULT_CONFIG

_DEFAULT_FALLBACKS = ("DejaVuSans", "NotoSans", "Arial", "LiberationSans")
_FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")


def _default_font_dirs() -> tuple[Path, ...]:
    system = platform.system()
    candidates: list[Path] = []

    if system == "Darwin":
        candidates.extend(
            [
                Path("/System/Library/Fonts"),
                Path("/Library/Fonts"),
                Path.home() / "Library/Fonts",
            ]
        )
    elif system == "Windows":
        candidates.append(Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts")
    else:  # Linux / Unix
        candidates.extend(
            [
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                Path.home() / ".fonts",
            ]
        )

    return tuple(path for path in candidates if path.exists())


def _iter_font_files(font_dirs: Iterable[Path]) -> Iterable[Path]:
    for directory in font_dirs:
        if not directory.exists():
            continue
        for root, _, files in os.walk(directory):
            for name in files:
                if any(name.lower().endswith(ext) for ext in _FONT_EXTENSIONS):
                    yield Path(root) / name


def _normalize_family(family: str) -> str:
    return "".join(ch for ch in family.lower() if ch.isalnum())


@dataclass
class FontResolver:
    """Resolve primary and fallback fonts based on filesystem scanning."""

    config: Config
    font_dirs: tuple[Path, ...] = field(default_factory=_default_font_dirs)
    fallback_families: tuple[str, ...] = _DEFAULT_FALLBACKS
    _cache: dict[str, Optional[Path]] = field(default_factory=dict, init=False)

    def resolve_primary(self, family: str) -> Optional[Path]:
        if not self.config.feature_enabled("text"):
            raise RuntimeError("Text rendering is disabled by configuration.")
        if not self.config.feature_enabled("system-fonts"):
            return None
        key = f"primary:{family}"
        if key not in self._cache:
            self._cache[key] = self._find_font(family)
        return self._cache[key]

    def resolve_fallback(self, char: str) -> Optional[Path]:
        if not self.config.feature_enabled("text"):
            raise RuntimeError("Text rendering is disabled by configuration.")
        if not self.config.feature_enabled("system-fonts"):
            return None
        for family in self.fallback_families:
            path = self.resolve_primary(family)
            if path is not None:
                return path
        return None

    def read_bytes(self, path: Path) -> bytes:
        if not self.config.feature_enabled("text"):
            raise RuntimeError("Text rendering is disabled by configuration.")
        if self.config.feature_enabled("memmap-fonts"):
            with path.open("rb") as handle:
                with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    return mm[:]
        return path.read_bytes()

    def _find_font(self, family: str) -> Optional[Path]:
        normalized = _normalize_family(family)
        if not normalized:
            return None
        for path in _iter_font_files(self.font_dirs):
            if normalized in _normalize_family(path.stem):
                return path
        return None


def default_font_resolver(config: Config | None = None) -> FontResolver:
    return FontResolver(config=config or DEFAULT_CONFIG)
