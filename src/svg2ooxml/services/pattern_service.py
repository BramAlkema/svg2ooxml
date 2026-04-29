"""Pattern service helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.svg_refs import local_name, local_url_id, reference_id
from svg2ooxml.drawingml.bridges import (
    PatternDescriptor,
    build_pattern_element,
    describe_pattern_element,
)

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.elements.patterns._helpers import parse_float_attr

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .conversion import ConversionServices


@dataclass
class PatternService:
    """Provides access to pattern definitions and basic inheritance."""

    _patterns: dict[str, PatternDescriptor] = field(default_factory=dict)
    _services: ConversionServices | None = None
    _processor: Any | None = None
    _conversion_cache: dict[str, str] = field(default_factory=dict)
    _materialized_elements: dict[str, etree._Element] = field(default_factory=dict)

    def bind_services(self, services: ConversionServices) -> None:
        self._services = services
        existing = services.resolve("patterns")
        if existing:
            self.update_definitions(existing)

    def update_definitions(
        self,
        patterns: Mapping[str, PatternDescriptor | etree._Element] | None,
    ) -> None:
        self._patterns.clear()
        self._materialized_elements.clear()
        self._conversion_cache.clear()
        if not patterns:
            return
        for pattern_id, definition in patterns.items():
            descriptor = self._coerce_descriptor(pattern_id, definition)
            if descriptor is None:
                continue
            key = descriptor.pattern_id or pattern_id
            self._patterns[key] = descriptor

    def get(self, pattern_id: str) -> PatternDescriptor | None:
        return self._patterns.get(pattern_id)

    def require(self, pattern_id: str) -> PatternDescriptor:
        descriptor = self.get(pattern_id)
        if descriptor is None:
            raise KeyError(f"pattern {pattern_id!r} is not defined")
        return descriptor

    def ids(self) -> Iterable[str]:
        return tuple(self._patterns.keys())

    def resolve_chain(
        self, pattern_id: str, *, include_self: bool = True
    ) -> list[PatternDescriptor]:
        """Resolve pattern inheritance via xlink:href."""
        chain: list[PatternDescriptor] = []
        visited: set[str] = set()
        current = pattern_id
        while current and current not in visited:
            visited.add(current)
            descriptor = self.get(current)
            if descriptor is None:
                break
            if include_self or current != pattern_id:
                chain.append(descriptor)
            href = descriptor.href if descriptor.href else descriptor.attributes.get("href")
            next_id = local_url_id(href)
            if next_id is None:
                break
            current = next_id
        return chain

    def clone(self) -> PatternService:
        clone = PatternService()
        clone._patterns = dict(self._patterns)
        clone._processor = self._processor
        clone._conversion_cache = dict(self._conversion_cache)
        clone._materialized_elements = dict(self._materialized_elements)
        return clone

    def set_processor(self, processor: Any) -> None:
        self._processor = processor

    @property
    def processor(self) -> Any | None:
        return self._processor

    # ------------------------------------------------------------------ #
    # Registration & conversion                                          #
    # ------------------------------------------------------------------ #

    def register_pattern(
        self,
        pattern_id: str,
        definition: PatternDescriptor | etree._Element,
    ) -> None:
        descriptor = self._coerce_descriptor(pattern_id, definition)
        if descriptor is None:
            return
        key = descriptor.pattern_id or pattern_id
        self._patterns[key] = descriptor
        self._conversion_cache.pop(key, None)
        self._materialized_elements.pop(key, None)

    def get_pattern_content(self, pattern_id: str, context: Any | None = None) -> str | None:
        clean_id = reference_id(pattern_id) or ""

        cached = self._conversion_cache.get(clean_id)
        if cached is not None:
            return cached

        descriptor = self.get(clean_id)
        if descriptor is None:
            logger.debug("Pattern %s not registered", pattern_id)
            return None
        element = self._materialize_pattern(clean_id, descriptor)

        if self._processor is not None:
            try:
                self._processor.analyze_pattern_element(element, context)
            except Exception:  # pragma: no cover - defensive
                logger.debug("Pattern processor failed for %s", clean_id, exc_info=True)

        content = self._convert_pattern(element)
        self._conversion_cache[clean_id] = content
        return content

    def process_svg_patterns(self, svg_root: etree._Element) -> None:
        if svg_root is None:
            return
        xpath = ".//svg:defs//svg:pattern"
        for pattern in svg_root.xpath(xpath, namespaces={"svg": "http://www.w3.org/2000/svg"}):
            identifier = pattern.get("id")
            if identifier:
                self.register_pattern(identifier, pattern)

    def clear_cache(self) -> None:
        self._conversion_cache.clear()
        self._materialized_elements.clear()

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _convert_pattern(self, pattern_element: etree._Element) -> str:
        pattern_type = self._detect_pattern_type(pattern_element)
        fg_color = self._resolve_style_color(pattern_element, default="#000000")
        bg_color = self._resolve_style_color(pattern_element, attribute="patternBackground", default="#FFFFFF")

        if pattern_type == "dots":
            preset = "dotGrid"
        elif pattern_type == "lines":
            preset = "horz"
        elif pattern_type == "diagonal":
            preset = "dnDiag"
        else:
            preset = None

        if preset:
            # Build a:pattFill with lxml
            pattFill = a_elem("pattFill", prst=preset)
            fgClr = a_sub(pattFill, "fgClr")
            a_sub(fgClr, "srgbClr", val=fg_color)
            bgClr = a_sub(pattFill, "bgClr")
            a_sub(bgClr, "srgbClr", val=bg_color)
            return to_string(pattFill)

        # Build a:solidFill with lxml
        solidFill = a_elem("solidFill")
        a_sub(solidFill, "srgbClr", val=fg_color)
        return to_string(solidFill)

    def _coerce_descriptor(
        self,
        pattern_id: str,
        definition: PatternDescriptor | etree._Element,
    ) -> PatternDescriptor | None:
        if isinstance(definition, PatternDescriptor):
            descriptor = definition
        elif isinstance(definition, etree._Element):
            try:
                descriptor = describe_pattern_element(definition)
            except Exception:  # pragma: no cover - defensive
                logger.debug("Failed to convert pattern %s to descriptor", pattern_id, exc_info=True)
                return None
        else:
            logger.debug("Unsupported pattern definition type for %s: %r", pattern_id, type(definition))
            return None

        if not descriptor.pattern_id:
            descriptor = replace(descriptor, pattern_id=pattern_id)
        return descriptor

    def _materialize_pattern(
        self,
        pattern_id: str,
        descriptor: PatternDescriptor,
    ) -> etree._Element:
        cached = self._materialized_elements.get(pattern_id)
        if cached is not None:
            return cached
        element = build_pattern_element(descriptor)
        self._materialized_elements[pattern_id] = element
        return element

    def as_element(self, descriptor: PatternDescriptor) -> etree._Element:
        key = descriptor.pattern_id or "__anon__"
        return self._materialize_pattern(key, descriptor)

    def _detect_pattern_type(self, pattern_element: etree._Element) -> str:
        children = list(pattern_element)
        if not children:
            return "solid"

        tags = [local_name(child.tag) for child in children if hasattr(child, "tag")]
        if any(tag == "circle" for tag in tags):
            return "dots"
        if any(tag == "line" for tag in tags):
            return "lines"
        for child, tag in zip(children, tags, strict=True):
            if tag == "rect":
                width = parse_float_attr(child, "width", axis="x", default=0.0)
                height = parse_float_attr(child, "height", axis="y", default=0.0)
                if width is None or height is None:
                    continue
                if width == 0 or height == 0:
                    continue
                ratio = max(width, height) / max(min(width, height), 1.0)
                if ratio > 3:
                    return "lines"
            elif tag == "path":
                d = child.get("d", "")
                if "L" in d and "M" in d:
                    return "diagonal"
        return "solid"

    def _resolve_style_color(
        self,
        element: etree._Element,
        *,
        attribute: str = "patternTransform",
        default: str,
    ) -> str:
        candidate = element.get(attribute)
        if isinstance(candidate, str) and candidate.strip():
            token = candidate.strip().lstrip("#")
        else:
            token = default.strip().lstrip("#")
        if len(token) == 3:
            token = "".join(ch * 2 for ch in token)
        return token.upper()


__all__ = ["PatternService"]
