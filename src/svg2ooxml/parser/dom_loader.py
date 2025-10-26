"""DOM loader utilities extracted from svg2pptx's parser stack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lxml import etree

from .xml import walk


@dataclass(frozen=True)
class ParserOptions:
    """Configuration passed to the XML parser."""

    remove_comments: bool = False
    remove_blank_text: bool = False
    strip_cdata: bool = False
    recover: bool = True
    resolve_entities: bool = True

    def as_lxml_config(self) -> dict[str, Any]:
        return {
            "remove_comments": self.remove_comments,
            "remove_blank_text": self.remove_blank_text,
            "strip_cdata": self.strip_cdata,
            "recover": self.recover,
            "resolve_entities": self.resolve_entities,
        }


class XMLParser:
    """Wrapper around ``lxml`` parsing with svg2pptx defaults."""

    def __init__(self, options: ParserOptions | None = None) -> None:
        self._options = options or ParserOptions()

    def parse(self, content: str) -> etree._Element:
        parser = etree.XMLParser(**self._options.as_lxml_config())
        return etree.fromstring(content.encode("utf-8"), parser=parser)

    def validate_root(self, root: etree._Element) -> None:
        if root.tag.split("}")[-1].lower() != "svg":
            raise ValueError("Root element is not <svg>.")

    def collect_statistics(self, root: etree._Element) -> dict[str, Any]:
        element_count = sum(1 for _ in walk(root))
        namespaces: set[str] = set()
        for element in walk(root):
            tag = getattr(element, "tag", "")
            if "}" in str(tag):
                namespaces.add(str(tag).split("}")[0][1:])
        return {
            "element_count": element_count,
            "namespace_count": len(namespaces),
        }


def load_dom(svg_text: str, options: ParserOptions | None = None) -> etree._Element:
    """Parse ``svg_text`` into an lxml element tree and validate the root."""
    parser = XMLParser(options)
    root = parser.parse(svg_text)
    parser.validate_root(root)
    return root


__all__ = ["ParserOptions", "XMLParser", "load_dom"]
