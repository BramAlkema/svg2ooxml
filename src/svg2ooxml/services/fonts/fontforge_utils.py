"""FontForge helpers for optional font parsing and generation."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from svg2ooxml.common.tempfiles import project_temp_dir

try:  # pragma: no cover - optional dependency guard
    import fontforge  # type: ignore[import-not-found]
    FONTFORGE_AVAILABLE = True
except Exception:  # pragma: no cover - environments without FontForge
    fontforge = None  # type: ignore[assignment]
    FONTFORGE_AVAILABLE = False


@contextmanager
def suppress_stderr() -> Iterator[None]:
    """Suppress noisy C-level stderr output for the duration of the context."""
    saved_stderr = os.dup(2)
    try:
        with open(os.devnull, "wb") as devnull:
            os.dup2(devnull.fileno(), 2)
            yield
    finally:
        try:
            os.dup2(saved_stderr, 2)
        finally:
            os.close(saved_stderr)


@contextmanager
def open_font(source: str | bytes, *, suffix: str = ".ttf") -> Iterator[Any]:
    if not FONTFORGE_AVAILABLE:  # pragma: no cover - optional dependency guard
        raise RuntimeError("FontForge is not available")

    temp_path: str | None = None
    if isinstance(source, (bytes, bytearray)):
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False,
            dir=project_temp_dir(),
        ) as temp_file:
            temp_file.write(bytes(source))
            temp_path = temp_file.name
        path = temp_path
    else:
        path = source

    with suppress_stderr():
        font = fontforge.open(path)
    try:
        yield font
    finally:
        try:
            font.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:  # pragma: no cover - best effort cleanup
                pass


def generate_font_bytes(font: Any, *, suffix: str = ".ttf") -> bytes:
    with tempfile.NamedTemporaryFile(
        suffix=suffix,
        delete=False,
        dir=project_temp_dir(),
    ) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        with suppress_stderr():
            font.generate(str(temp_path))
        return temp_path.read_bytes()
    finally:
        try:
            temp_path.unlink()
        except OSError:  # pragma: no cover - best effort cleanup
            pass


def get_table_data(font: Any, tag: str) -> bytes | None:
    try:
        data = font.getTableData(tag)
    except Exception:
        return None
    if data is None:
        return None
    return bytes(data)


__all__ = [
    "FONTFORGE_AVAILABLE",
    "generate_font_bytes",
    "get_table_data",
    "open_font",
    "suppress_stderr",
]
