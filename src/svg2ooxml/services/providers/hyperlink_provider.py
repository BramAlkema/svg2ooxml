"""Register hyperlink processor provider."""

from __future__ import annotations

import logging

from svg2ooxml.core.hyperlinks import HyperlinkProcessor

from .registry import register_provider


def _factory() -> HyperlinkProcessor:
    logger = logging.getLogger("svg2ooxml.hyperlinks")
    return HyperlinkProcessor(logger)


register_provider("hyperlink_processor", _factory)


__all__ = ["_factory"]
