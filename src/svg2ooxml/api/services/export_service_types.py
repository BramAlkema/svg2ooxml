"""Shared datatypes for export service internals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class FontPreparationResult:
    """Information gathered when preparing fonts for a conversion."""

    workspace: Path | None
    directories: tuple[Path, ...]
    downloaded_fonts: list[dict[str, str]]
    missing_sources: list[str]


__all__ = ["FontPreparationResult"]
