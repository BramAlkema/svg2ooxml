"""Limited SVG CSS selector parsing and matching."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from lxml import etree


@dataclass(frozen=True)
class SelectorPart:
    """Single selector component with optional combinator to the left."""

    tag: str | None
    element_id: str | None
    classes: tuple[str, ...]
    combinator: str | None  # 'descendant', 'child', or None


@dataclass(frozen=True)
class CompiledSelector:
    """Selector compiled into reversed parts for fast matching."""

    parts: tuple[SelectorPart, ...]
    specificity: tuple[int, int, int]

    def matches(self, element: etree._Element) -> bool:
        return matches_selector(self.parts, element)


def parse_selector(selector: str) -> list[SelectorPart]:
    """Parse a limited subset of CSS selectors (type, class, id, descendant, child)."""

    parts: list[SelectorPart] = []
    length = len(selector)
    i = 0
    pending_combinator: str | None = None

    while i < length:
        while i < length and selector[i].isspace():
            i += 1
            pending_combinator = pending_combinator or ("descendant" if parts else None)

        if i >= length:
            break

        if selector[i] == ">":
            pending_combinator = "child"
            i += 1
            continue

        start = i
        tag = None
        while i < length and (selector[i].isalnum() or selector[i] in {"-", "_"}):
            i += 1
        if i > start:
            tag = selector[start:i]

        classes: list[str] = []
        element_id: str | None = None
        while i < length:
            if selector[i] == ".":
                i += 1
                start = i
                while i < length and (selector[i].isalnum() or selector[i] in {"-", "_"}):
                    i += 1
                if start < i:
                    classes.append(selector[start:i])
            elif selector[i] == "#":
                i += 1
                start = i
                while i < length and (selector[i].isalnum() or selector[i] in {"-", "_"}):
                    i += 1
                if start < i:
                    element_id = selector[start:i]
            else:
                break

        if tag is None and not classes and element_id is None:
            return []

        parts.append(
            SelectorPart(
                tag=tag,
                element_id=element_id,
                classes=tuple(classes),
                combinator=pending_combinator,
            )
        )
        pending_combinator = None

    if parts:
        parts[0] = SelectorPart(
            tag=parts[0].tag,
            element_id=parts[0].element_id,
            classes=parts[0].classes,
            combinator=None,
        )
    return parts


def compute_specificity(parts: Iterable[SelectorPart]) -> tuple[int, int, int]:
    ids = 0
    classes = 0
    tags = 0
    for part in parts:
        if part.element_id:
            ids += 1
        if part.classes:
            classes += len(part.classes)
        if part.tag:
            tags += 1
    return (ids, classes, tags)


def matches_selector(parts: tuple[SelectorPart, ...], element: etree._Element) -> bool:
    def match_part(index: int, node: etree._Element) -> bool:
        part = parts[index]
        if not matches_simple_selector(part, node):
            return False
        if index == len(parts) - 1:
            return True

        combinator = part.combinator
        if combinator == "child":
            parent = node.getparent()
            if parent is None:
                return False
            return match_part(index + 1, parent)
        if combinator == "descendant":
            parent = node.getparent()
            while parent is not None:
                if match_part(index + 1, parent):
                    return True
                parent = parent.getparent()
            return False
        return match_part(index + 1, node)

    if not parts:
        return False
    return match_part(0, element)


def matches_simple_selector(part: SelectorPart, element: etree._Element) -> bool:
    if part.tag:
        local_name = element.tag.split("}")[-1]
        if local_name != part.tag:
            return False

    if part.element_id:
        if element.get("id") != part.element_id:
            return False

    if part.classes:
        class_attr = element.get("class")
        if not class_attr:
            return False
        classes = class_attr.split()
        for token in part.classes:
            if token not in classes:
                return False
    return True


__all__ = [
    "CompiledSelector",
    "SelectorPart",
    "compute_specificity",
    "matches_selector",
    "matches_simple_selector",
    "parse_selector",
]
