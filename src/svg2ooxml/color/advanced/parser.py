#!/usr/bin/env python3
"""Lightweight color parser utilities for ConversionServices."""

from __future__ import annotations

from typing import Optional, Tuple

from .core import Color


class ColorParser:
    """Helper object for normalizing and converting color inputs."""

    def __call__(self, value) -> Color:
        return Color(value)

    def normalize_color(
        self,
        value: str | None,
        *,
        include_hash: bool = False,
        default: Optional[str] = None,
    ) -> Optional[str]:
        hex_value = self.to_hex(value, include_hash=include_hash)
        if hex_value is None:
            return default
        return hex_value

    def to_hex(
        self,
        value: str | None,
        *,
        include_hash: bool = False,
    ) -> Optional[str]:
        if not value:
            return None
        try:
            color = Color(value)
            hex_value = color.hex(include_hash=True)
            return hex_value if include_hash else hex_value.lstrip('#')
        except Exception:
            return None

    def to_rgb(self, value: str | None) -> Optional[Tuple[int, int, int]]:
        if not value:
            return None
        try:
            color = Color(value)
            return color.rgb()
        except Exception:
            return None
