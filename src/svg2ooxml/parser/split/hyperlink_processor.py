"""Hyperlink processing helpers re-exported for parser compatibility."""

# TODO(ADR-parser-core): Port hyperlink processing from svg2pptx rather than re-exporting.

from __future__ import annotations

from svg2ooxml.map.converter.hyperlinks import HyperlinkProcessor

__all__ = ["HyperlinkProcessor"]
