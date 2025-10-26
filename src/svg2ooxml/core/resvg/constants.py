"""Shared constants used across pyportresvg modules."""

from __future__ import annotations

from dataclasses import dataclass

# Placeholder constants; populate as the port progresses.
DEFAULT_DPI: int = 96


@dataclass(frozen=True)
class FeatureFlag:
    """Metadata describing optional behavior mirrored from resvg."""

    name: str
    default: bool
    description: str


FEATURE_FLAGS: dict[str, FeatureFlag] = {
    "text": FeatureFlag(
        name="text",
        default=True,
        description="Enable text shaping and layout.",
    ),
    "system-fonts": FeatureFlag(
        name="system-fonts",
        default=True,
        description="Load fonts from the host system font directories.",
    ),
    "memmap-fonts": FeatureFlag(
        name="memmap-fonts",
        default=True,
        description="Memory-map font files for faster loading.",
    ),
    "raster-images": FeatureFlag(
        name="raster-images",
        default=True,
        description="Decode embedded raster image formats (GIF, JPEG, WebP).",
    ),
}
