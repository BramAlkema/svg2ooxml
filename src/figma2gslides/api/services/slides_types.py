"""Shared types/constants for Slides publishing helpers."""

from __future__ import annotations

from dataclasses import dataclass

SLIDES_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/presentations",
)


class SlidesPublishingError(RuntimeError):
    """Raised when publishing to Google Slides fails."""


@dataclass(frozen=True)
class SlidesPublishResult:
    """Details about an uploaded Google Slides presentation."""

    file_id: str
    web_view_link: str
    published_url: str
    embed_url: str
    thumbnail_urls: tuple[str, ...]


__all__ = ["SLIDES_SCOPES", "SlidesPublishResult", "SlidesPublishingError"]
