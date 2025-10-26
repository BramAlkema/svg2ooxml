"""Element-safe iteration utilities (ported from svg2pptx)."""

from __future__ import annotations

from collections.abc import Iterator

from lxml import etree

_EXCLUDE_NODE_TYPES = (etree._Comment, etree._ProcessingInstruction)


def is_element(node: object) -> bool:
    """Return True when node is a real XML element (no comments/PIs)."""
    return isinstance(node, etree._Element) and not isinstance(
        node, _EXCLUDE_NODE_TYPES
    )


def children(element: etree._Element) -> Iterator[etree._Element]:
    """Yield only element children, skipping comments and processing instructions."""
    for child in element:
        if is_element(child):
            yield child


def walk(root: etree._Element) -> Iterator[etree._Element]:
    """Depth-first traversal yielding elements only, in document order."""
    if not is_element(root):
        return
    stack: list[etree._Element] = [root]
    while stack:
        current = stack.pop()
        yield current
        kids = [child for child in current if is_element(child)]
        stack.extend(reversed(kids))


def iter_descendants(element: etree._Element) -> Iterator[etree._Element]:
    """Yield element descendants (excluding the element itself)."""
    for child in children(element):
        yield child
        yield from iter_descendants(child)


def count_elements(root: etree._Element) -> int:
    """Count all real elements within the tree."""
    return sum(1 for _ in walk(root))


def find_elements_by_tag(root: etree._Element, tag: str) -> Iterator[etree._Element]:
    """Find all elements with the given local tag name."""
    for elem in walk(root):
        raw_tag = getattr(elem, "tag", "")
        local = raw_tag.split('}')[-1] if '}' in raw_tag else raw_tag
        if local == tag:
            yield elem


__all__ = [
    "children",
    "count_elements",
    "find_elements_by_tag",
    "is_element",
    "iter_descendants",
    "walk",
]
