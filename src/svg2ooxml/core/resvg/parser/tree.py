"""Lightweight structures for the parsed SVG tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, List, Optional

from .css import StyleRule


@dataclass(slots=True)
class SvgNode:
    """Lightweight node representation for the normalized SVG tree."""

    tag: str
    source: Any | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list["SvgNode"] = field(default_factory=list)
    styles: dict[str, str] = field(default_factory=dict)
    text: Optional[str] = None
    tail: Optional[str] = None

    def iter(self) -> Iterator["SvgNode"]:
        yield self
        for child in self.children:
            yield from child.iter()

    def find_first(self, tag: str) -> Optional["SvgNode"]:
        if self.tag == tag:
            return self
        for child in self.children:
            result = child.find_first(tag)
            if result is not None:
                return result
        return None


@dataclass(slots=True)
class SvgDocument:
    """Parsed SVG document representation."""

    root: SvgNode
    base_dir: Optional[str] = None
    style_rules: List[StyleRule] = field(default_factory=list)

    def iter(self) -> Iterable[SvgNode]:
        return self.root.iter()

    def find_first(self, tag: str) -> Optional[SvgNode]:
        return self.root.find_first(tag)
