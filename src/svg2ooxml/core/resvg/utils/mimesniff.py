"""Minimal image MIME detection based on magic bytes."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def sniff_image_mime(path: Path) -> Optional[str]:
    with path.open("rb") as handle:
        header = handle.read(16)

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xFF\xD8\xFF"):
        return "image/jpeg"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "image/gif"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image/webp"

    return None
