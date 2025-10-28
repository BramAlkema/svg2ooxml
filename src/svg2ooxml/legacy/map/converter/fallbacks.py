"""Compatibility shim for legacy fallback helpers."""

from __future__ import annotations

from svg2ooxml.core.ir.fallbacks import hex_to_rgba, render_bitmap_fallback, render_emf_fallback

__all__ = ["render_emf_fallback", "render_bitmap_fallback", "hex_to_rgba"]
