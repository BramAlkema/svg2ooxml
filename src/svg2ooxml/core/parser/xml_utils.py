"""Utility helpers for safe XML traversal."""

from __future__ import annotations

from collections.abc import Iterator

from lxml import etree


def children(element: etree._Element) -> Iterator[etree._Element]:
    """Yield direct child elements, skipping comments and processing instructions."""
    for child in element:
        if isinstance(child.tag, str):
            yield child  # type: ignore[misc]


def walk(element: etree._Element) -> Iterator[etree._Element]:
    """Yield ``element`` and all descendant elements depth-first."""
    stack: list[etree._Element] = [element]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(list(children(current))))


__all__ = ["children", "walk"]
