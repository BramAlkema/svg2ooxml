"""Helpers for locating golden baseline artefacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass
class GoldenRepository:
    """Resolve golden artefact paths used by visual regression tests."""

    root: Path

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            root = Path(__file__).resolve().parents[2] / "tests" / "visual" / "golden"
        self.root = root

    def path_for(self, rel_path: str | Path) -> Path:
        """Return the absolute path under the golden root for *rel_path*."""

        return self.root / rel_path

    def ensure(self, rel_path: str | Path) -> Path:
        """Return the path and ensure that it exists."""

        path = self.path_for(rel_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_images(self, rel_dir: str | Path) -> Sequence[Path]:
        """Return sorted PNG paths within *rel_dir* if it exists."""

        directory = self.path_for(rel_dir)
        if not directory.exists():
            return ()
        return tuple(sorted(directory.glob("*.png")))


__all__ = ["GoldenRepository"]
