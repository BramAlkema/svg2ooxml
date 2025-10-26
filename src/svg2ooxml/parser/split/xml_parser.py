"""Low-level SVG XML parsing utilities."""

from __future__ import annotations

import logging
from typing import Any

from lxml import etree

from svg2ooxml.parser.xml import walk

logger = logging.getLogger(__name__)


class XMLParser:
    """Wrapper around :mod:`lxml` parsing with recoverable defaults."""

    def __init__(self, parser_config: dict[str, Any]) -> None:
        self._config = dict(parser_config)

    def parse(self, content: str) -> etree._Element:
        parser = etree.XMLParser(**self._config)
        return etree.fromstring(content.encode("utf-8"), parser=parser)

    @staticmethod
    def validate_root(svg_root: etree._Element) -> None:
        """Ensure the document root is an ``<svg>`` element."""
        if svg_root.tag.split("}")[-1].lower() != "svg":
            raise ValueError("Root element is not <svg>")

    def collect_statistics(self, svg_root: etree._Element) -> dict[str, Any]:
        element_count = sum(1 for _ in walk(svg_root))
        namespaces: set[str] = set()
        for element in walk(svg_root):
            tag = getattr(element, "tag", "")
            if "}" in str(tag):
                namespace = str(tag).split("}")[0][1:]
                namespaces.add(namespace)
        return {
            "element_count": element_count,
            "namespace_count": len(namespaces),
        }


__all__ = ["XMLParser"]
