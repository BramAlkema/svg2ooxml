"""Ensure legacy hyperlink processor shim points at the core implementation."""

from svg2ooxml.core.hyperlinks import HyperlinkProcessor
from svg2ooxml.map.hyperlinks import HyperlinkProcessor as LegacyHyperlinkProcessor


def test_legacy_shim_reexports_core_processor() -> None:
    assert LegacyHyperlinkProcessor is HyperlinkProcessor
