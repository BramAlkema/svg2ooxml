"""Safe SVG normalization helpers inspired by svg2pptx."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from lxml import etree

from .xml import children, walk


@dataclass(frozen=True)
class NormalizationSettings:
    """Toggle individual normalization routines."""

    fix_namespaces: bool = True
    normalize_whitespace: bool = True
    add_missing_attributes: bool = True
    prune_empty_containers: bool = True
    filter_comments: bool = True
    fix_encoding_issues: bool = True


class SafeSVGNormalizer:
    """Apply svg2pptx-style normalization to an SVG element tree."""

    def __init__(
        self,
        settings: NormalizationSettings | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings or NormalizationSettings()
        self._logger = logger or logging.getLogger(__name__)

    def normalize(
        self, svg_root: etree._Element
    ) -> tuple[etree._Element, dict[str, Any]]:
        changes: dict[str, Any] = {
            "namespaces_fixed": False,
            "attributes_added": [],
            "structure_fixes": [],
            "encoding_fixes": [],
            "whitespace_normalized": False,
            "comments_filtered": False,
            "log": [],
        }

        if self.settings.fix_encoding_issues:
            self._fix_encoding_issues(svg_root, changes)

        if self.settings.fix_namespaces:
            svg_root = self._fix_namespaces(svg_root, changes)

        if self.settings.add_missing_attributes:
            self._add_missing_attributes(svg_root, changes)

        if self.settings.normalize_whitespace:
            self._normalize_whitespace(svg_root, changes)

        if self.settings.prune_empty_containers:
            self._prune_empty_containers(svg_root, changes)

        if self.settings.filter_comments:
            self._filter_comments(svg_root, changes)

        return svg_root, changes

    # ------------------------------------------------------------------
    # Namespace handling
    # ------------------------------------------------------------------

    def _fix_namespaces(
        self, svg_root: etree._Element, changes: dict[str, Any]
    ) -> etree._Element:
        svg_ns = "http://www.w3.org/2000/svg"
        nsmap = dict(svg_root.nsmap or {})
        if svg_ns not in nsmap.values():  # rebuild with default namespace
            nsmap.setdefault(None, svg_ns)
            rebuilt = self._clone_with_ns(svg_root, nsmap)
            changes["namespaces_fixed"] = True
            self._log(
                changes,
                action="fix_namespaces",
                details={"added_default_namespace": True},
            )
            return rebuilt
        return svg_root

    def _clone_with_ns(
        self, element: etree._Element, nsmap: dict[str | None, str]
    ) -> etree._Element:
        tag = element.tag
        if "}" not in tag and nsmap.get(None):
            tag = f"{{{nsmap[None]}}}{tag}"

        clone = etree.Element(tag, nsmap=nsmap)
        for attr, value in element.attrib.items():
            clone.set(attr, value)
        clone.text = element.text
        clone.tail = element.tail

        for child in children(element):
            clone.append(self._clone_with_ns(child, nsmap))
        return clone

    # ------------------------------------------------------------------
    # Attribute fixes
    # ------------------------------------------------------------------

    def _add_missing_attributes(
        self, svg_root: etree._Element, changes: dict[str, Any]
    ) -> None:
        added: list[str] = []
        if "version" not in svg_root.attrib:
            svg_root.set("version", "1.1")
            added.append("version")
        if (
            "xmlns" not in svg_root.attrib
            and "http://www.w3.org/2000/svg" not in (svg_root.nsmap or {}).values()
        ):
            svg_root.set("xmlns", "http://www.w3.org/2000/svg")
            added.append("xmlns")
        changes["attributes_added"] = added
        if added:
            self._log(
                changes,
                action="add_root_attributes",
                details={"attributes": added},
                target=self._element_identifier(svg_root),
            )

    # ------------------------------------------------------------------
    # Whitespace
    # ------------------------------------------------------------------

    def _normalize_whitespace(
        self, svg_root: etree._Element, changes: dict[str, Any]
    ) -> None:
        text_changes = 0
        tail_changes = 0
        impacted_ids: set[str] = set()

        for element in walk(svg_root):
            if element.text and element.text.strip() != element.text:
                element.text = element.text.strip() or None
                text_changes += 1
                element_id = element.get("id")
                if element_id:
                    impacted_ids.add(element_id)
            if element.tail and element.tail.strip() != element.tail:
                element.tail = element.tail.strip() or None
                tail_changes += 1
                parent = element.getparent()
                if parent is not None:
                    parent_id = parent.get("id")
                    if parent_id:
                        impacted_ids.add(parent_id)

        normalized = (text_changes + tail_changes) > 0
        changes["whitespace_normalized"] = normalized
        if normalized:
            details: dict[str, Any] = {
                "text_nodes": text_changes,
                "tail_nodes": tail_changes,
            }
            if impacted_ids:
                details["element_ids"] = sorted(impacted_ids)
            self._log(
                changes,
                action="normalize_whitespace",
                details=details,
            )

    # ------------------------------------------------------------------
    # Structure pruning
    # ------------------------------------------------------------------

    def _prune_empty_containers(
        self, svg_root: etree._Element, changes: dict[str, Any]
    ) -> None:
        removable_tags = {"g", "defs", "clipPath", "mask", "pattern", "marker", "symbol"}
        removed: list[str] = []
        removed_details: list[dict[str, Any]] = []
        for element in list(walk(svg_root)):
            local_name = element.tag.split("}")[-1]
            if local_name not in removable_tags:
                continue
            if self._has_meaningful_attributes(element):
                continue
            if next(children(element), None) is not None:
                continue
            parent = element.getparent()
            if parent is not None:
                element_id = element.get("id")
                parent.remove(element)
                removed.append(local_name)
                removed_details.append(
                    {
                        "tag": local_name,
                        "element_id": element_id,
                    }
                )
        if removed:
            changes["structure_fixes"] = removed
            self._log(
                changes,
                action="prune_empty_containers",
                details={
                    "count": len(removed),
                    "removed": removed_details,
                },
            )

    # ------------------------------------------------------------------
    # Comment filtering
    # ------------------------------------------------------------------

    def _filter_comments(
        self, svg_root: etree._Element, changes: dict[str, Any]
    ) -> None:
        removed_count = 0
        parent_ids: set[str] = set()
        for element in list(walk(svg_root)):
            for child in list(element):
                if isinstance(child, etree._Comment):
                    element.remove(child)
                    removed_count += 1
                    element_id = element.get("id")
                    if element_id:
                        parent_ids.add(element_id)
        changes["comments_filtered"] = removed_count > 0
        if removed_count:
            details: dict[str, Any] = {"count": removed_count}
            if parent_ids:
                details["parent_ids"] = sorted(parent_ids)
            self._log(
                changes,
                action="filter_comments",
                details=details,
            )

    # ------------------------------------------------------------------
    # Encoding fixes
    # ------------------------------------------------------------------

    def _fix_encoding_issues(
        self, svg_root: etree._Element, changes: dict[str, Any]
    ) -> None:
        replacements = {
            "\x00": "",
            "\x0b": " ",
            "\x0c": " ",
            "\ufeff": "",
        }
        translation = str.maketrans(replacements)
        text_changes = 0
        tail_changes = 0
        attribute_changes = 0
        impacted_ids: set[str] = set()

        for element in walk(svg_root):
            element_id = element.get("id")

            if element.text:
                new_text = element.text.translate(translation)
                if new_text != element.text:
                    element.text = new_text
                    text_changes += 1
                    if element_id:
                        impacted_ids.add(element_id)
            if element.tail:
                new_tail = element.tail.translate(translation)
                if new_tail != element.tail:
                    element.tail = new_tail
                    tail_changes += 1
                    if element_id:
                        impacted_ids.add(element_id)

            updated_attrs: dict[str, str] = {}
            for attr, value in element.attrib.items():
                translated = value.translate(translation)
                if translated != value:
                    updated_attrs[attr] = translated
            if updated_attrs:
                attribute_changes += len(updated_attrs)
                for attr, value in updated_attrs.items():
                    element.set(attr, value)
                if element_id:
                    impacted_ids.add(element_id)

        if text_changes or tail_changes or attribute_changes:
            details: dict[str, Any] = {
                "text_nodes": text_changes,
                "tail_nodes": tail_changes,
                "attributes": attribute_changes,
            }
            if impacted_ids:
                details["element_ids"] = sorted(impacted_ids)
            changes["encoding_fixes"].append(details)
            self._log(
                changes,
                action="fix_encoding",
                details=details,
            )

    # ------------------------------------------------------------------
    # Attribute heuristics
    # ------------------------------------------------------------------

    def _has_meaningful_attributes(self, element: etree._Element) -> bool:
        meaningful = {
            "id",
            "class",
            "style",
            "transform",
            "fill",
            "stroke",
            "opacity",
            "x",
            "y",
            "width",
            "height",
            "cx",
            "cy",
            "r",
            "rx",
            "ry",
            "d",
            "points",
            "x1",
            "y1",
            "x2",
            "y2",
            "font-size",
            "font-family",
            "text-anchor",
            "href",
            "xlink:href",
            "patternUnits",
            "gradientUnits",
            "offset",
            "stop-color",
            "in",
            "result",
            "stdDeviation",
        }
        for attr in element.attrib:
            local_attr = attr.split("}")[-1]
            if local_attr in meaningful:
                return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _element_identifier(element: etree._Element) -> str:
        element_id = element.get("id")
        if element_id:
            return element_id
        local_name = element.tag.split("}")[-1]
        return f"<{local_name}>"

    def _log(
        self,
        changes: dict[str, Any],
        *,
        action: str,
        target: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        entry = {"action": action}
        if target is not None:
            entry["target"] = target
        if details:
            entry["details"] = details
        changes["log"].append(entry)
        if details:
            self._logger.debug("%s: %s", action, details)
        else:
            self._logger.debug("%s", action)


__all__ = ["NormalizationSettings", "SafeSVGNormalizer"]
