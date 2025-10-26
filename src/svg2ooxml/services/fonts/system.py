"""Utilities for discovering and managing font directories."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ENV_FONT_DIRS = "SVG2OOXML_FONT_DIRS"


def _platform_default_directories() -> tuple[str, ...]:
    system = platform.system().lower()
    if system == "darwin":
        return (
            "/System/Library/Fonts",
            "/Library/Fonts",
            "~/Library/Fonts",
        )
    if system == "windows":
        return (
            "C:/Windows/Fonts",
            "~/AppData/Local/Microsoft/Windows/Fonts",
        )
    if system == "linux":
        return (
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            "~/.fonts",
            "~/.local/share/fonts",
        )
    return ()


def _normalise_directory(path: str | os.PathLike[str]) -> Path | None:
    candidate = Path(path).expanduser()
    if not candidate.exists() or not candidate.is_dir():
        return None
    try:
        return candidate.resolve()
    except OSError:
        return candidate


def parse_directory_list(value: str | None) -> tuple[Path, ...]:
    """Parse a path separator delimited list of directories."""

    if not value:
        return ()
    directories: list[Path] = []
    for token in value.split(os.pathsep):
        entry = token.strip()
        if not entry:
            continue
        normalised = _normalise_directory(entry)
        if normalised is not None:
            directories.append(normalised)
    return tuple(directories)


def collect_font_directories(
    extra_directories: Sequence[str | os.PathLike[str]] | None = None,
    *,
    include_env: bool = True,
    env_var: str = ENV_FONT_DIRS,
) -> tuple[Path, ...]:
    """Return platform and user-specified font directories."""

    discovered: list[Path] = []
    for entry in _platform_default_directories():
        normalised = _normalise_directory(entry)
        if normalised is not None:
            discovered.append(normalised)

    if include_env:
        env_dirs = parse_directory_list(os.getenv(env_var))
        discovered.extend(env_dirs)

    if extra_directories:
        for entry in extra_directories:
            normalised = _normalise_directory(entry)
            if normalised is not None:
                discovered.append(normalised)

    unique: list[Path] = []
    seen: set[Path] = set()
    for directory in discovered:
        if directory in seen:
            continue
        seen.add(directory)
        unique.append(directory)
    return tuple(unique)


@dataclass(frozen=True)
class FontSystemConfig:
    """Lightweight configuration for ``FontSystem``."""

    directories: tuple[Path, ...] = ()
    fallback_chain: tuple[str, ...] = ("Arial", "Helvetica", "sans-serif")
    prefer_embedding: bool = True


class FontSystem:
    """Thin wrapper around ``FontService`` offering convenience helpers."""

    def __init__(
        self,
        font_service,
        *,
        config: FontSystemConfig | None = None,
    ) -> None:
        self._service = font_service
        self._config = config or FontSystemConfig()
        self._registered: set[Path] = set()
        self.register_directories(self._config.directories)

    @property
    def service(self):
        return self._service

    @property
    def config(self) -> FontSystemConfig:
        return self._config

    def register_directories(self, directories: Iterable[Path]) -> None:
        from svg2ooxml.services.fonts.providers.directory import DirectoryFontProvider

        for directory in directories:
            normalised = _normalise_directory(directory)
            if normalised is None or normalised in self._registered:
                continue
            provider = DirectoryFontProvider((normalised,))
            self._service.register_provider(provider)
            self._registered.add(normalised)

    def find_font(self, query) -> object | None:
        """Proxy to ``FontService.find_font``."""

        return self._service.find_font(query)

    def iter_alternatives(self, query):
        return self._service.iter_alternatives(query)


__all__ = [
    "ENV_FONT_DIRS",
    "FontSystem",
    "FontSystemConfig",
    "collect_font_directories",
    "parse_directory_list",
]
