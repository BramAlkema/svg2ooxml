"""SVG preview/source markup helpers for raster filter fallbacks."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from lxml import etree

from svg2ooxml.common.svg_refs import local_name, local_url_id

_URL_REF_RE = re.compile(r"url\(\s*#([^)]+?)\s*\)")


class RasterPreviewBuilder:
    """Build temporary SVG documents used by raster fallback rendering."""

    def build_preview_svg_markup(
        self,
        *,
        filter_clone: etree._Element,
        preview_filter_id: str,
        width_px: int,
        height_px: int,
        context,
        resolved_bounds: dict[str, float] | None,
    ) -> str:
        svg_ns = "http://www.w3.org/2000/svg"
        xlink_ns = "http://www.w3.org/1999/xlink"
        source_element = self.source_element_from_context(context)
        source_root = None
        if source_element is not None:
            try:
                source_root = source_element.getroottree().getroot()
            except Exception:
                source_root = None

        svg_root = etree.Element(
            f"{{{svg_ns}}}svg",
            nsmap={None: svg_ns, "xlink": xlink_ns},
            attrib={
                "width": str(max(1, int(width_px))),
                "height": str(max(1, int(height_px))),
            },
        )
        defs = etree.SubElement(svg_root, f"{{{svg_ns}}}defs")
        if isinstance(source_root, etree._Element):
            for defs_child in self.iter_defs_children(source_root):
                defs.append(defs_child)
        defs.append(filter_clone)

        source_subtree = self.build_source_subtree(
            source_element=source_element,
            source_root=source_root,
            preview_filter_id=preview_filter_id,
            svg_ns=svg_ns,
        )
        if source_subtree is not None:
            preserve_user_space = self.requires_original_user_space(
                source_subtree,
                source_root,
            )
            svg_root.set(
                "viewBox",
                self.preview_viewbox(
                    bounds=resolved_bounds,
                    width_px=width_px,
                    height_px=height_px,
                    preserve_user_space=preserve_user_space,
                ),
            )
            svg_root.append(
                self.localize_source_subtree(
                    source_subtree,
                    resolved_bounds,
                    preserve_user_space=preserve_user_space,
                )
            )
        else:
            svg_root.set(
                "viewBox",
                self.preview_viewbox(
                    bounds=resolved_bounds,
                    width_px=width_px,
                    height_px=height_px,
                ),
            )
            rect = etree.SubElement(
                svg_root,
                f"{{{svg_ns}}}rect",
                attrib={
                    "x": "0",
                    "y": "0",
                    "width": "100%",
                    "height": "100%",
                    "fill": "#7F8CFF",
                    "filter": f"url(#{preview_filter_id})",
                },
            )
            rect.set("opacity", "1")

        return etree.tostring(svg_root, encoding="unicode")

    def build_source_svg_markup(
        self,
        *,
        source_element: etree._Element,
        source_root: etree._Element | None,
        resolved_bounds: dict[str, float] | None,
        width_px: int,
        height_px: int,
    ) -> str | None:
        svg_ns = "http://www.w3.org/2000/svg"
        xlink_ns = "http://www.w3.org/1999/xlink"
        svg_root = etree.Element(
            f"{{{svg_ns}}}svg",
            nsmap={None: svg_ns, "xlink": xlink_ns},
            attrib={
                "width": str(max(1, int(width_px))),
                "height": str(max(1, int(height_px))),
            },
        )
        defs = etree.SubElement(svg_root, f"{{{svg_ns}}}defs")
        if isinstance(source_root, etree._Element):
            for defs_child in self.iter_defs_children(source_root):
                defs.append(defs_child)
        source_subtree = self.build_source_subtree(
            source_element=source_element,
            source_root=source_root,
            preview_filter_id=None,
            svg_ns=svg_ns,
        )
        if source_subtree is None:
            return None
        preserve_user_space = self.requires_original_user_space(
            source_subtree,
            source_root,
        )
        svg_root.set(
            "viewBox",
            self.preview_viewbox(
                bounds=resolved_bounds,
                width_px=width_px,
                height_px=height_px,
                preserve_user_space=preserve_user_space,
            ),
        )
        svg_root.append(
            self.localize_source_subtree(
                source_subtree,
                resolved_bounds,
                preserve_user_space=preserve_user_space,
            )
        )
        return etree.tostring(svg_root, encoding="unicode")

    def source_element_from_context(self, context) -> etree._Element | None:
        options = getattr(context, "options", None)
        if not isinstance(options, dict):
            return None
        candidate = options.get("element")
        if isinstance(candidate, etree._Element):
            return candidate
        return None

    def iter_defs_children(self, source_root: etree._Element) -> list[etree._Element]:
        svg_ns = "http://www.w3.org/2000/svg"
        children: list[etree._Element] = []
        for defs in source_root.findall(f".//{{{svg_ns}}}defs"):
            for child in defs:
                if isinstance(child.tag, str):
                    children.append(deepcopy(child))
        return children

    def build_source_subtree(
        self,
        *,
        source_element: etree._Element | None,
        source_root: etree._Element | None,
        preview_filter_id: str | None,
        svg_ns: str,
    ) -> etree._Element | None:
        del svg_ns
        if source_element is None:
            return None
        node = deepcopy(source_element)
        self.rewrite_filter_reference(node, preview_filter_id)
        ancestors: list[etree._Element] = []
        current = source_element.getparent()
        while current is not None and current is not source_root:
            if local_name(current.tag).lower() != "defs":
                ancestors.append(current)
            current = current.getparent()
        for ancestor in reversed(ancestors):
            wrapper = etree.Element(ancestor.tag, attrib=dict(ancestor.attrib))
            wrapper.append(node)
            node = wrapper
        self.flatten_transforms_in_place(node)
        return node

    def rewrite_filter_reference(
        self, element: etree._Element, preview_filter_id: str | None
    ) -> None:
        if preview_filter_id:
            element.set("filter", f"url(#{preview_filter_id})")
        else:
            element.attrib.pop("filter", None)
        style_attr = element.get("style")
        if not style_attr or "filter" not in style_attr:
            return
        if preview_filter_id:
            style_attr = re.sub(
                r"filter\s*:\s*url\([^)]+\)",
                f"filter:url(#{preview_filter_id})",
                style_attr,
            )
        else:
            style_attr = re.sub(
                r"(?:^|;)\s*filter\s*:\s*url\([^)]+\)\s*;?",
                ";",
                style_attr,
            )
            style_attr = re.sub(r";{2,}", ";", style_attr).strip(" ;")
        if style_attr:
            element.set("style", style_attr)
        else:
            element.attrib.pop("style", None)

    def preview_viewbox(
        self,
        *,
        bounds: dict[str, float | Any] | None,
        width_px: int,
        height_px: int,
        preserve_user_space: bool = False,
    ) -> str:
        if not bounds:
            return f"0 0 {max(1, int(width_px))} {max(1, int(height_px))}"

        x = float(bounds.get("x", 0.0))
        y = float(bounds.get("y", 0.0))
        width = max(1.0, float(bounds.get("width", width_px)))
        height = max(1.0, float(bounds.get("height", height_px)))

        if preserve_user_space:
            return f"{x:g} {y:g} {width:g} {height:g}"
        return f"0 0 {width:g} {height:g}"

    def localize_source_subtree(
        self,
        source_subtree: etree._Element,
        bounds: dict[str, float | Any] | None,
        *,
        preserve_user_space: bool = False,
    ) -> etree._Element:
        if preserve_user_space or not isinstance(bounds, dict):
            return source_subtree
        try:
            x = float(bounds.get("x", 0.0))
            y = float(bounds.get("y", 0.0))
        except (TypeError, ValueError):
            return source_subtree
        if abs(x) <= 1e-6 and abs(y) <= 1e-6:
            return source_subtree
        self.flatten_transforms_in_place(
            source_subtree,
            inherited_transform=f"translate({-x:g},{-y:g})",
        )
        return source_subtree

    def flatten_transforms_in_place(
        self,
        element: etree._Element,
        inherited_transform: str = "",
    ) -> None:
        if not isinstance(element.tag, str):
            return

        local_tag = local_name(element.tag)
        current_transform = (element.get("transform") or "").strip()
        combined_transform = " ".join(
            part for part in (inherited_transform.strip(), current_transform) if part
        )

        if local_tag in {"g", "svg"}:
            element.attrib.pop("transform", None)
        elif combined_transform:
            element.set("transform", combined_transform)
        else:
            element.attrib.pop("transform", None)

        for child in element:
            if isinstance(child.tag, str):
                self.flatten_transforms_in_place(child, combined_transform)

    def requires_original_user_space(
        self,
        source_subtree: etree._Element,
        source_root: etree._Element | None,
    ) -> bool:
        if not isinstance(source_root, etree._Element):
            return False

        referenced_ids: set[str] = set()
        for node in source_subtree.iter():
            if not isinstance(node.tag, str):
                continue
            for attr_name, attr_value in node.attrib.items():
                if not isinstance(attr_value, str):
                    continue
                if attr_name in {
                    "fill",
                    "stroke",
                    "filter",
                    "clip-path",
                    "mask",
                    "href",
                    "{http://www.w3.org/1999/xlink}href",
                }:
                    referenced_ids.update(_URL_REF_RE.findall(attr_value))
                    ref_id = local_url_id(attr_value)
                    if ref_id is not None:
                        referenced_ids.add(ref_id)
                elif attr_name == "style":
                    referenced_ids.update(_URL_REF_RE.findall(attr_value))

        if not referenced_ids:
            return False

        targets = {
            element.get("id"): element
            for element in source_root.xpath(".//*[@id]")
            if isinstance(element.tag, str) and isinstance(element.get("id"), str)
        }
        for ref_id in referenced_ids:
            target = targets.get(ref_id)
            if target is None:
                continue
            local_tag = local_name(target.tag)
            if local_tag in {"linearGradient", "radialGradient"}:
                if (target.get("gradientUnits") or "").strip() == "userSpaceOnUse":
                    return True
            elif local_tag == "pattern":
                if (
                    (target.get("patternUnits") or "").strip() == "userSpaceOnUse"
                    or (target.get("patternContentUnits") or "userSpaceOnUse").strip()
                    == "userSpaceOnUse"
                ):
                    return True
            elif local_tag == "clipPath":
                if (target.get("clipPathUnits") or "userSpaceOnUse").strip() == "userSpaceOnUse":
                    return True
            elif local_tag == "mask":
                if (
                    (target.get("maskUnits") or "").strip() == "userSpaceOnUse"
                    or (target.get("maskContentUnits") or "userSpaceOnUse").strip()
                    == "userSpaceOnUse"
                ):
                    return True
        return False


__all__ = ["RasterPreviewBuilder"]
