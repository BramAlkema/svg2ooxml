"""Helpers for allocating temporary files and directories within the project tree."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TMP_DIR = PROJECT_ROOT / "tmp"


def project_temp_dir() -> Path:
    """Ensure and return the repository-scoped tmp directory."""

    DEFAULT_TMP_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_TMP_DIR


@contextmanager
def temporary_directory(prefix: str = "svg2ooxml_") -> Iterator[Path]:
    """Yield a temporary directory located under the project tmp folder."""

    base_dir = project_temp_dir()
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=base_dir))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
