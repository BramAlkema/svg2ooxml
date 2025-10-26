"""DOM traversal helpers reused by the parser."""

# TODO(ADR-parser-core): Inline svg2pptx traversal logic instead of re-exporting.

from __future__ import annotations

from svg2ooxml.map.converter.traversal import ElementTraversal

__all__ = ["ElementTraversal"]
