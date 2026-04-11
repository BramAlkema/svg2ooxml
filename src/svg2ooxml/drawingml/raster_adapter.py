"""Raster fallback adapter with optional skia rendering."""

from __future__ import annotations

import re
import struct
import zlib
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from lxml import etree

try:  # pragma: no cover - skia optional during transition
    import skia  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade without skia
    skia = None

try:  # pragma: no cover - numpy optional for lightweight deployments
    import numpy as np

    NUMPY_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]
    NUMPY_AVAILABLE = False

_UNSUPPORTED_SOURCE_STYLE = object()
_URL_REF_RE = re.compile(r"url\(\s*#([^)]+?)\s*\)")


@dataclass
class RasterResult:
    image_bytes: bytes
    relationship_id: str
    width_px: int
    height_px: int
    metadata: dict[str, Any]


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _solid_gray_png(width: int, height: int, gray: int) -> bytes:
    width = max(1, width)
    height = max(1, height)
    gray = max(0, min(255, gray))
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = _png_chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0),
    )
    row = bytes([0]) + bytes([gray] * width)
    pixel_rows = row * height
    idat = _png_chunk(b"IDAT", zlib.compress(pixel_rows))
    iend = _png_chunk(b"IEND", b"")
    return header + ihdr + idat + iend


class RasterAdapter:
    """Generate raster filter fallbacks (skia-backed when available)."""

    def __init__(self) -> None:
        self._counter = 0

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def render_filter(
        self,
        *,
        filter_id: str,
        filter_element,
        context,
        default_size: tuple[int, int] = (192, 128),
    ) -> RasterResult:
        """Render a PNG fallback for ``filter_id`` using skia when available."""

        descriptor, bounds = self._descriptor_payload(context)
        if descriptor is None:
            descriptor = self._descriptor_from_filter_element(filter_element, filter_id)
        primitive_tags = tuple(descriptor.get("primitive_tags", ())) if descriptor else ()
        filter_units = (descriptor or {}).get("filter_units")
        primitive_units = (descriptor or {}).get("primitive_units")
        complexity = max(1, len(primitive_tags)) if primitive_tags else 1

        if skia is None or not NUMPY_AVAILABLE:
            return self.generate_placeholder(
                width_px=default_size[0],
                height_px=default_size[1],
                metadata={
                    "filter_id": filter_id,
                    "renderer": "placeholder",
                    "primitives": primitive_tags,
                    "filter_units": filter_units,
                    "primitive_units": primitive_units,
                    "complexity": complexity,
                },
            )

        resolved_bounds = self._resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=default_size[0],
            default_height=default_size[1],
        )
        width_px, height_px = self._derive_dimensions(context, default_size, descriptor, resolved_bounds)
        passes = self._pass_count(descriptor, complexity)
        scale = self._scale_factor(descriptor, bounds, complexity)

        surface = self._render_surface_with_filter_pipeline(
            filter_element=filter_element,
            context=context,
        )
        if surface is None:
            surface = self._render_preview_with_resvg(
                filter_element,
                filter_id,
                width_px,
                height_px,
                context=context,
            )
        if surface is not None:
            self._counter += 1
            relationship_id = f"rIdRaster{self._counter}"
            filter_tag = getattr(filter_element, "tag", "")
            filter_name = filter_tag.split("}")[-1] if isinstance(filter_tag, str) else "filter"
            metadata = {
                "filter_id": filter_id,
                "renderer": "resvg",
                "filter_tag": filter_name,
                "width_px": surface.width,
                "height_px": surface.height,
                "primitives": primitive_tags,
                "filter_units": filter_units,
                "primitive_units": primitive_units,
                "render_passes": passes,
                "scale_factor": scale,
                "complexity": complexity,
            }
            if descriptor:
                metadata["descriptor"] = descriptor
            if resolved_bounds:
                metadata["bounds"] = resolved_bounds
            return RasterResult(
                image_bytes=_surface_to_png(surface),
                relationship_id=relationship_id,
                width_px=surface.width,
                height_px=surface.height,
                metadata=metadata,
            )

        return self._render_placeholder_preview(
            filter_id=filter_id,
            filter_element=filter_element,
            primitive_tags=primitive_tags,
            filter_units=filter_units,
            primitive_units=primitive_units,
            complexity=complexity,
            width_px=width_px,
            height_px=height_px,
            passes=passes,
            scale=scale,
            descriptor=descriptor,
            bounds=bounds,
            default_size=default_size,
        )

    def _render_surface_with_filter_pipeline(
        self,
        *,
        filter_element: etree._Element,
        context,
    ):
        if skia is None or not NUMPY_AVAILABLE:
            return None
        try:
            from svg2ooxml.filters.planner import FilterPlanner
            from svg2ooxml.filters.resvg_bridge import resolve_filter_element
            from svg2ooxml.render.filters import apply_filter
        except Exception:  # pragma: no cover - optional render path
            return None

        try:
            resolved_filter = resolve_filter_element(filter_element)
        except Exception:
            return None

        planner = FilterPlanner()
        options = getattr(context, "options", None)
        if not isinstance(options, dict):
            options = {}

        plan = planner.build_resvg_plan(resolved_filter, options=options)
        if plan is None:
            return None

        try:
            bounds = planner.resvg_bounds(options, resolved_filter)
            viewport = planner.resvg_viewport(bounds)
        except Exception:
            return None

        source_surface = self.render_source_surface(
            width_px=viewport.width,
            height_px=viewport.height,
            context=context,
        )
        if source_surface is None:
            return None

        try:
            return apply_filter(source_surface, plan, bounds, viewport)
        except Exception:
            return None

    def render_source_surface(
        self,
        *,
        width_px: int,
        height_px: int,
        context,
    ):
        """Render the unfiltered source element subtree into a surface."""

        if skia is None or not NUMPY_AVAILABLE:
            return None
        source_descriptor = self._source_graphic_descriptor_from_context(context)
        descriptor, bounds = self._descriptor_payload(context)
        if isinstance(source_descriptor, dict):
            surface = self._render_surface_from_descriptor(
                descriptor=source_descriptor,
                bounds=bounds,
                width_px=width_px,
                height_px=height_px,
            )
            if surface is not None:
                return surface
        try:
            from svg2ooxml.core.resvg.normalizer import normalize_svg_string
            from svg2ooxml.core.resvg.parser.options import build_default_options
            from svg2ooxml.render.pipeline import render
        except Exception:  # pragma: no cover - renderer dependencies missing
            return None

        source_element = self._source_element_from_context(context)
        if source_element is None:
            return None

        source_root = None
        try:
            source_root = source_element.getroottree().getroot()
        except Exception:
            source_root = None

        svg_markup = self._build_source_svg_markup(
            source_element=source_element,
            source_root=source_root,
            descriptor=descriptor,
            bounds=bounds,
            width_px=width_px,
            height_px=height_px,
        )
        if svg_markup is None:
            return None

        resources_dir = None
        if context and context.services:
            image_service = getattr(context.services, "image_service", None)
            if image_service:
                from svg2ooxml.services.image_service import FileResolver

                for resolver in image_service.resolvers():
                    if isinstance(resolver, FileResolver):
                        resources_dir = resolver.base_dir
                        break

        try:
            options = build_default_options(resources_dir=resources_dir)
            normalized = normalize_svg_string(svg_markup, options=options)
            return render(normalized.tree)
        except Exception:  # pragma: no cover - renderer failure
            return None

    def _source_graphic_descriptor_from_context(self, context) -> dict[str, Any] | None:
        options = getattr(context, "options", None)
        if not isinstance(options, dict):
            return None
        filter_inputs = options.get("filter_inputs")
        if not isinstance(filter_inputs, dict):
            return None
        source_graphic = filter_inputs.get("SourceGraphic")
        if isinstance(source_graphic, dict):
            return dict(source_graphic)
        return None

    def _render_surface_from_descriptor(
        self,
        *,
        descriptor: dict[str, Any],
        bounds: dict[str, float | Any] | None,
        width_px: int,
        height_px: int,
    ):
        if skia is None:
            return None
        if not _transform_is_identity(descriptor.get("transform")):
            return None

        source_bounds = bounds
        descriptor_bbox = descriptor.get("bbox")
        if isinstance(descriptor_bbox, dict) and descriptor_bbox:
            source_bounds = descriptor_bbox
        if not isinstance(source_bounds, dict):
            return None

        try:
            x = float(source_bounds.get("x", 0.0))
            y = float(source_bounds.get("y", 0.0))
            width = max(1.0, float(source_bounds.get("width", width_px)))
            height = max(1.0, float(source_bounds.get("height", height_px)))
        except (TypeError, ValueError):
            return None

        surface = skia.Surface(int(max(1, width_px)), int(max(1, height_px)))
        canvas = surface.getCanvas()
        canvas.clear(skia.Color4f(0.0, 0.0, 0.0, 0.0))

        canvas.save()
        canvas.scale(width_px / width, height_px / height)
        canvas.translate(-x, -y)

        path = self._descriptor_to_skia_path(descriptor)
        if path is None:
            canvas.restore()
            return None

        opacity = _float_or(descriptor.get("opacity"), 1.0)
        fill = descriptor.get("fill")
        stroke = descriptor.get("stroke")
        fill_color = _color4f_from_paint_descriptor(fill, opacity)
        if fill_color is _UNSUPPORTED_SOURCE_STYLE:
            canvas.restore()
            return None
        if fill_color is not None:
            paint = skia.Paint(
                AntiAlias=True,
                Style=skia.Paint.kFill_Style,
                Color4f=fill_color,
            )
            canvas.drawPath(path, paint)

        stroke_paint = _stroke_paint_from_descriptor(stroke, opacity)
        if stroke_paint is _UNSUPPORTED_SOURCE_STYLE:
            canvas.restore()
            return None
        if stroke_paint is not None:
            canvas.drawPath(path, stroke_paint)

        canvas.restore()
        try:
            image = surface.makeImageSnapshot()
            return _surface_from_skia_image(image)
        except Exception:  # pragma: no cover - defensive
            return None

    def _descriptor_to_skia_path(self, descriptor: dict[str, Any]):
        geometry = descriptor.get("geometry")
        if not isinstance(geometry, list) or not geometry:
            return None
        path = skia.Path()
        started = False
        for segment in geometry:
            if not isinstance(segment, dict):
                continue
            start = segment.get("start")
            if not started and _is_point_pair(start):
                path.moveTo(float(start[0]), float(start[1]))
                started = True
            segment_type = str(segment.get("type") or "").lower()
            if segment_type == "line":
                end = segment.get("end")
                if _is_point_pair(end):
                    path.lineTo(float(end[0]), float(end[1]))
                else:
                    return None
            elif segment_type == "cubic":
                control1 = segment.get("control1")
                control2 = segment.get("control2")
                end = segment.get("end")
                if _is_point_pair(control1) and _is_point_pair(control2) and _is_point_pair(end):
                    path.cubicTo(
                        float(control1[0]),
                        float(control1[1]),
                        float(control2[0]),
                        float(control2[1]),
                        float(end[0]),
                        float(end[1]),
                    )
                else:
                    return None
            else:
                return None
        if descriptor.get("closed"):
            path.close()
        return path if started else None

    def generate_placeholder(
        self,
        *,
        width_px: int = 64,
        height_px: int = 64,
        metadata: dict[str, Any] | None = None,
    ) -> RasterResult:
        self._counter += 1
        gray = 64 + (self._counter % 128)
        payload = _solid_gray_png(width_px, height_px, gray)
        meta: dict[str, Any] = {
            "placeholder": True,
            "width_px": width_px,
            "height_px": height_px,
            "render_passes": 0,
            "scale_factor": 1.0,
        }
        if metadata:
            meta.update(metadata)
        return RasterResult(
            image_bytes=payload,
            relationship_id=f"rIdRaster{self._counter}",
            width_px=width_px,
            height_px=height_px,
            metadata=meta,
        )

    def _render_preview_with_resvg(
        self,
        filter_element,
        filter_id: str,
        width_px: int,
        height_px: int,
        context=None,
    ):
        if skia is None or not NUMPY_AVAILABLE:
            return None
        try:
            from svg2ooxml.core.resvg.normalizer import normalize_svg_string
            from svg2ooxml.core.resvg.parser.options import build_default_options
            from svg2ooxml.render.pipeline import render
        except Exception:  # pragma: no cover - renderer dependencies missing
            return None

        try:
            filter_clone = deepcopy(filter_element)
        except Exception:
            return None

        svg_ns = "http://www.w3.org/2000/svg"
        if not isinstance(filter_clone.tag, str) or "}" not in filter_clone.tag:
            filter_clone.tag = f"{{{svg_ns}}}filter"

        preview_filter_id = filter_clone.get("id") or f"svg2ooxml_filter_{self._counter + 1}"
        filter_clone.set("id", preview_filter_id)

        svg_markup = self._build_preview_svg_markup(
            filter_clone=filter_clone,
            preview_filter_id=preview_filter_id,
            width_px=width_px,
            height_px=height_px,
            context=context,
        )

        resources_dir = None
        if context and context.services:
            image_service = getattr(context.services, "image_service", None)
            if image_service:
                from svg2ooxml.services.image_service import FileResolver
                for resolver in image_service.resolvers():
                    if isinstance(resolver, FileResolver):
                        resources_dir = resolver.base_dir
                        break

        try:
            options = build_default_options(resources_dir=resources_dir)
            normalized = normalize_svg_string(svg_markup, options=options)
            return render(normalized.tree)
        except Exception:  # pragma: no cover - renderer failure
            return None

    def _build_preview_svg_markup(
        self,
        *,
        filter_clone: etree._Element,
        preview_filter_id: str,
        width_px: int,
        height_px: int,
        context,
    ) -> str:
        svg_ns = "http://www.w3.org/2000/svg"
        xlink_ns = "http://www.w3.org/1999/xlink"
        descriptor, bounds = self._descriptor_payload(context)
        source_element = self._source_element_from_context(context)
        source_root = None
        if source_element is not None:
            try:
                source_root = source_element.getroottree().getroot()
            except Exception:
                source_root = None

        resolved_bounds = self._resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=width_px,
            default_height=height_px,
        )
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
            for defs_child in self._iter_defs_children(source_root):
                defs.append(defs_child)
        defs.append(filter_clone)

        source_subtree = self._build_source_subtree(
            source_element=source_element,
            source_root=source_root,
            preview_filter_id=preview_filter_id,
            svg_ns=svg_ns,
        )
        if source_subtree is not None:
            preserve_user_space = self._requires_original_user_space(
                source_subtree,
                source_root,
            )
            svg_root.set(
                "viewBox",
                self._preview_viewbox(
                    bounds=resolved_bounds,
                    width_px=width_px,
                    height_px=height_px,
                    preserve_user_space=preserve_user_space,
                ),
            )
            svg_root.append(
                self._localize_source_subtree(
                    source_subtree,
                    resolved_bounds,
                    svg_ns,
                    preserve_user_space=preserve_user_space,
                )
            )
        else:
            svg_root.set(
                "viewBox",
                self._preview_viewbox(bounds=resolved_bounds, width_px=width_px, height_px=height_px),
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

    def _build_source_svg_markup(
        self,
        *,
        source_element: etree._Element,
        source_root: etree._Element | None,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
        width_px: int,
        height_px: int,
    ) -> str | None:
        svg_ns = "http://www.w3.org/2000/svg"
        xlink_ns = "http://www.w3.org/1999/xlink"
        resolved_bounds = self._resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=width_px,
            default_height=height_px,
        )
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
            for defs_child in self._iter_defs_children(source_root):
                defs.append(defs_child)
        source_subtree = self._build_source_subtree(
            source_element=source_element,
            source_root=source_root,
            preview_filter_id=None,
            svg_ns=svg_ns,
        )
        if source_subtree is None:
            return None
        preserve_user_space = self._requires_original_user_space(
            source_subtree,
            source_root,
        )
        svg_root.set(
            "viewBox",
            self._preview_viewbox(
                bounds=resolved_bounds,
                width_px=width_px,
                height_px=height_px,
                preserve_user_space=preserve_user_space,
            ),
        )
        svg_root.append(
            self._localize_source_subtree(
                source_subtree,
                resolved_bounds,
                svg_ns,
                preserve_user_space=preserve_user_space,
            )
        )
        return etree.tostring(svg_root, encoding="unicode")

    def _source_element_from_context(self, context) -> etree._Element | None:
        options = getattr(context, "options", None)
        if not isinstance(options, dict):
            return None
        candidate = options.get("element")
        if isinstance(candidate, etree._Element):
            return candidate
        return None

    def _iter_defs_children(self, source_root: etree._Element) -> list[etree._Element]:
        svg_ns = "http://www.w3.org/2000/svg"
        children: list[etree._Element] = []
        for defs in source_root.findall(f".//{{{svg_ns}}}defs"):
            for child in defs:
                if isinstance(child.tag, str):
                    children.append(deepcopy(child))
        return children

    def _build_source_subtree(
        self,
        *,
        source_element: etree._Element | None,
        source_root: etree._Element | None,
        preview_filter_id: str | None,
        svg_ns: str,
    ) -> etree._Element | None:
        if source_element is None:
            return None
        node = deepcopy(source_element)
        self._rewrite_filter_reference(node, preview_filter_id)
        ancestors: list[etree._Element] = []
        current = source_element.getparent()
        while current is not None and current is not source_root:
            local = current.tag.split("}", 1)[-1] if isinstance(current.tag, str) and "}" in current.tag else str(current.tag)
            if local.lower() != "defs":
                ancestors.append(current)
            current = current.getparent()
        for ancestor in reversed(ancestors):
            wrapper = etree.Element(ancestor.tag, attrib=dict(ancestor.attrib))
            wrapper.append(node)
            node = wrapper
        self._flatten_transforms_in_place(node)
        return node

    def _rewrite_filter_reference(
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

    def _preview_viewbox(
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

    def _localize_source_subtree(
        self,
        source_subtree: etree._Element,
        bounds: dict[str, float | Any] | None,
        svg_ns: str,
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
        self._flatten_transforms_in_place(
            source_subtree,
            inherited_transform=f"translate({-x:g},{-y:g})",
        )
        return source_subtree

    def _flatten_transforms_in_place(
        self,
        element: etree._Element,
        inherited_transform: str = "",
    ) -> None:
        if not isinstance(element.tag, str):
            return

        local_tag = element.tag.split("}", 1)[-1] if "}" in element.tag else element.tag
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
                self._flatten_transforms_in_place(child, combined_transform)

    def _requires_original_user_space(
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
                    if attr_value.startswith("#"):
                        referenced_ids.add(attr_value[1:])
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
            local_tag = target.tag.split("}", 1)[-1] if "}" in target.tag else target.tag
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

    def _render_placeholder_preview(
        self,
        *,
        filter_id: str,
        filter_element,
        primitive_tags: tuple[str, ...],
        filter_units,
        primitive_units,
        complexity: int,
        width_px: int,
        height_px: int,
        passes: int,
        scale: float,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
        default_size: tuple[int, int],
    ) -> RasterResult:
        if skia is None:
            return self.generate_placeholder(
                width_px=default_size[0],
                height_px=default_size[1],
                metadata={
                    "filter_id": filter_id,
                    "renderer": "placeholder",
                    "primitives": primitive_tags,
                    "filter_units": filter_units,
                    "primitive_units": primitive_units,
                    "complexity": complexity,
                },
            )

        try:
            surface = skia.Surface(int(max(1, width_px)), int(max(1, height_px)))
        except Exception:  # pragma: no cover - defensive
            return self.generate_placeholder(
                width_px=default_size[0],
                height_px=default_size[1],
                metadata={
                    "filter_id": filter_id,
                    "renderer": "placeholder",
                    "primitives": primitive_tags,
                    "filter_units": filter_units,
                    "primitive_units": primitive_units,
                    "complexity": complexity,
                },
            )

        canvas = surface.getCanvas()
        canvas.clear(skia.Color4f(0.0, 0.0, 0.0, 0.0))

        palette = self._palette_for_primitives(primitive_tags, seed=hash(filter_id))
        self._render_gradient_passes(
            canvas,
            width_px,
            height_px,
            palette,
            passes=passes,
            scale=scale,
            descriptor=descriptor,
            bounds=bounds,
        )

        if bounds:
            self._draw_bounds(canvas, bounds, width_px, height_px, palette)

        filter_tag = getattr(filter_element, "tag", "")
        filter_name = filter_tag.split("}")[-1] if isinstance(filter_tag, str) else "filter"
        self._render_caption(canvas, width_px, height_px, filter_name, primitive_tags, passes)

        image = surface.makeImageSnapshot()
        if image is None:
            return self.generate_placeholder(
                width_px=default_size[0],
                height_px=default_size[1],
                metadata={
                    "filter_id": filter_id,
                    "renderer": "placeholder",
                    "primitives": primitive_tags,
                    "filter_units": filter_units,
                    "primitive_units": primitive_units,
                    "complexity": complexity,
                },
            )

        encoded = image.encodeToData()
        if encoded is None:
            return self.generate_placeholder(
                width_px=default_size[0],
                height_px=default_size[1],
                metadata={
                    "filter_id": filter_id,
                    "renderer": "placeholder",
                    "primitives": primitive_tags,
                    "filter_units": filter_units,
                    "primitive_units": primitive_units,
                    "complexity": complexity,
                },
            )

        self._counter += 1
        relationship_id = f"rIdRaster{self._counter}"
        metadata = {
            "filter_id": filter_id,
            "renderer": "skia",
            "filter_tag": filter_name,
            "width_px": width_px,
            "height_px": height_px,
            "primitives": primitive_tags,
            "filter_units": filter_units,
            "primitive_units": primitive_units,
            "render_passes": passes,
            "scale_factor": scale,
            "complexity": complexity,
        }
        if descriptor:
            metadata["descriptor"] = descriptor
        if bounds:
            metadata["bounds"] = bounds
        return RasterResult(
            image_bytes=bytes(encoded),
            relationship_id=relationship_id,
            width_px=width_px,
            height_px=height_px,
            metadata=metadata,
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _derive_dimensions(
        self,
        context,
        defaults: tuple[int, int],
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
    ) -> tuple[int, int]:
        width, height = defaults
        if context is not None:
            options = getattr(context, "options", None)
            if isinstance(options, dict):
                bbox = options.get("ir_bbox")
                if isinstance(bbox, dict):
                    try:
                        width = max(1.0, float(bbox.get("width", width)))
                        height = max(1.0, float(bbox.get("height", height)))
                    except (TypeError, ValueError):
                        pass
        if bounds:
            width = max(width, _coerce_positive(bounds.get("width"), width))
            height = max(height, _coerce_positive(bounds.get("height"), height))
        width *= self._viewport_scale(descriptor)
        height *= self._viewport_scale(descriptor)
        return int(min(width, 1024)), int(min(height, 1024))

    def _resolved_filter_bounds(
        self,
        *,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
        default_width: float,
        default_height: float,
    ) -> dict[str, float] | None:
        if isinstance(bounds, dict):
            try:
                x = float(bounds.get("x", 0.0))
                y = float(bounds.get("y", 0.0))
                width = max(1.0, float(bounds.get("width", default_width)))
                height = max(1.0, float(bounds.get("height", default_height)))
            except (TypeError, ValueError):
                x = 0.0
                y = 0.0
                width = max(1.0, float(default_width))
                height = max(1.0, float(default_height))
        else:
            x = 0.0
            y = 0.0
            width = max(1.0, float(default_width))
            height = max(1.0, float(default_height))

        region = (descriptor or {}).get("filter_region") if descriptor else None
        units = (descriptor or {}).get("filter_units") if descriptor else None
        if isinstance(region, dict):
            base_width = width
            base_height = height
            if units == "objectBoundingBox":
                rx = self._parse_object_bbox_region_value(region.get("x"), reference=base_width)
                ry = self._parse_object_bbox_region_value(region.get("y"), reference=base_height)
                rw = self._parse_object_bbox_region_value(region.get("width"), reference=base_width)
                rh = self._parse_object_bbox_region_value(region.get("height"), reference=base_height)
                if rx is not None:
                    x += rx
                if ry is not None:
                    y += ry
                if rw is not None and rw > 0:
                    width = rw
                if rh is not None and rh > 0:
                    height = rh
            else:
                rx = self._parse_region_value(region.get("x"), reference=base_width)
                ry = self._parse_region_value(region.get("y"), reference=base_height)
                rw = self._parse_region_value(region.get("width"), reference=base_width)
                rh = self._parse_region_value(region.get("height"), reference=base_height)
                if rx is not None:
                    x = rx
                if ry is not None:
                    y = ry
                if rw is not None and rw > 0:
                    width = rw
                if rh is not None and rh > 0:
                    height = rh

        return {"x": x, "y": y, "width": width, "height": height}

    def _parse_region_value(self, value: object, *, reference: float) -> float | None:
        if value is None:
            return None
        if isinstance(value, str):
            token = value.strip()
            if token.endswith("%"):
                try:
                    return (float(token[:-1]) / 100.0) * reference
                except ValueError:
                    return None
        if _is_number(value):
            return float(value)
        return None

    def _parse_object_bbox_region_value(
        self,
        value: object,
        *,
        reference: float,
    ) -> float | None:
        if value is None:
            return None
        if isinstance(value, str):
            token = value.strip()
            if token.endswith("%"):
                try:
                    return (float(token[:-1]) / 100.0) * reference
                except ValueError:
                    return None
        if _is_number(value):
            return float(value) * reference
        return None

    def _color_from_seed(self, seed: int) -> skia.Color4f:
        hue = (seed % 360) / 360.0
        r, g, b = self._hsv_to_rgb(hue, 0.55, 0.95)
        return skia.Color4f(r, g, b, 1.0)

    # ------------------------------------------------------------------ #
    # Descriptor helpers                                                 #
    # ------------------------------------------------------------------ #

    def _descriptor_payload(
        self, context
    ) -> tuple[dict[str, Any] | None, dict[str, float | Any] | None]:
        if context is None:
            return None, None
        options = getattr(context, "options", None)
        if not isinstance(options, dict):
            return None, None
        descriptor = options.get("resvg_descriptor")
        if isinstance(descriptor, dict):
            descriptor = dict(descriptor)
        else:
            descriptor = None
        bounds = options.get("ir_bbox")
        if isinstance(bounds, dict):
            bounds = {
                key: float(bounds[key])
                for key in ("x", "y", "width", "height")
                if key in bounds and _is_number(bounds[key])
            }
        else:
            bounds = None
        return descriptor, bounds

    def _descriptor_from_filter_element(
        self,
        filter_element: etree._Element | None,
        filter_id: str,
    ) -> dict[str, Any] | None:
        if not isinstance(filter_element, etree._Element):
            return None
        region = {
            key: filter_element.get(key)
            for key in ("x", "y", "width", "height")
            if filter_element.get(key) is not None
        }
        primitive_tags: list[str] = []
        for child in filter_element:
            if not isinstance(child.tag, str):
                continue
            primitive_tags.append(child.tag.split("}", 1)[-1])
        if not region and not primitive_tags and not filter_element.attrib:
            return None
        return {
            "filter_id": filter_id,
            "filter_units": filter_element.get("filterUnits", "objectBoundingBox"),
            "primitive_units": filter_element.get("primitiveUnits", "userSpaceOnUse"),
            "primitive_tags": primitive_tags,
            "filter_region": region,
        }

    def _viewport_scale(self, descriptor: dict[str, Any] | None) -> float:
        if not descriptor:
            return 1.0
        units = descriptor.get("filter_units")
        if units == "objectBoundingBox":
            return 1.1
        return 1.0

    def _pass_count(self, descriptor: dict[str, Any] | None, complexity: int) -> int:
        if not descriptor:
            return min(3, max(1, complexity))
        passes = descriptor.get("render_passes")
        if isinstance(passes, int) and passes > 0:
            return min(6, passes)
        return min(6, max(1, complexity))

    def _scale_factor(
        self,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
        complexity: int,
    ) -> float:
        scale = 1.0
        if descriptor:
            region = descriptor.get("filter_region")
            if isinstance(region, dict):
                width = _coerce_positive(region.get("width"))
                height = _coerce_positive(region.get("height"))
                if width and height:
                    base = max(width, height)
                    if base > 1.5:
                        scale = min(2.5, 1.0 + base * 0.15)
        if bounds:
            max_dim = max(_coerce_positive(bounds.get("width"), 1.0), _coerce_positive(bounds.get("height"), 1.0))
            scale = max(scale, min(3.0, 1.0 + max_dim / 320.0))
        scale = max(scale, 1.0 + min(complexity, 6) * 0.08)
        return float(scale)

    # ------------------------------------------------------------------ #
    # Rendering helpers                                                  #
    # ------------------------------------------------------------------ #

    def _palette_for_primitives(self, primitives: Iterable[str], seed: int) -> list[skia.Color4f]:
        tags = [tag.lower() for tag in primitives] if primitives else []
        if "feturbulence" in tags:
            colors = ["#1B5E20", "#0D47A1", "#FBC02D", "#4E342E"]
        elif "feconvolvematrix" in tags or "femorphology" in tags:
            colors = ["#3E2723", "#BF360C", "#FFEB3B", "#4FC3F7"]
        elif "fegaussianblur" in tags or "fedropshadow" in tags:
            colors = ["#311B92", "#1976D2", "#64B5F6", "#FFFFFF"]
        elif "fecomponenttransfer" in tags or "fecolormatrix" in tags:
            colors = ["#FF6F00", "#F06292", "#8E24AA", "#26C6DA"]
        elif "fewave" in tags or "fedisplacementmap" in tags:
            colors = ["#004D40", "#009688", "#F9A825", "#E57373"]
        else:
            seed_val = abs(seed) + 1
            colors = [
                self._seed_hex(seed_val),
                self._seed_hex(seed_val * 3),
                self._seed_hex(seed_val * 7),
                self._seed_hex(seed_val * 11),
            ]
        return [self._color4f_from_hex(hex_str) for hex_str in colors]

    def _render_gradient_passes(
        self,
        canvas,
        width: int,
        height: int,
        palette: list[skia.Color4f],
        *,
        passes: int,
        scale: float,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
    ) -> None:
        passes = max(1, passes)
        for index in range(passes):
            canvas.save()
            progress = (index + 1) / passes
            rotation = progress * 360.0 * 0.35
            canvas.translate(width / 2, height / 2)
            canvas.rotate(rotation)
            scale_factor = 1.0 + (scale - 1.0) * progress * 0.8
            canvas.scale(scale_factor, scale_factor)
            canvas.translate(-width / 2, -height / 2)

            points = self._gradient_points(width, height, index, passes, descriptor, bounds)
            shader = skia.GradientShader.MakeLinear(
                points,
                palette,
                None,
                skia.TileMode.kMirror,
            )
            paint = skia.Paint(Shader=shader, AntiAlias=True)
            canvas.drawRect(skia.Rect.MakeWH(width, height), paint)
            canvas.restore()

        if palette:
            overlay = skia.Paint(Color=skia.ColorSetARGB(48, 0, 0, 0))
            canvas.drawRect(skia.Rect.MakeWH(width, height), overlay)

    def _gradient_points(
        self,
        width: int,
        height: int,
        index: int,
        passes: int,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
    ) -> list[skia.Point]:
        offset_ratio = (index + 1) / max(1, passes)
        if descriptor and descriptor.get("primitive_tags"):
            ratio = min(0.8, 0.2 + offset_ratio * 0.6)
        else:
            ratio = 0.5

        start_x = 0
        start_y = int(height * (1.0 - ratio))
        end_x = int(width * ratio)
        end_y = height

        if bounds and all(k in bounds for k in ("x", "y")):
            start_x += int(bounds["x"])
            start_y += int(bounds["y"])

        return [skia.Point(start_x, start_y), skia.Point(end_x, end_y)]

    def _render_caption(
        self,
        canvas,
        width: int,
        height: int,
        filter_name: str,
        primitives: Iterable[str],
        passes: int,
    ) -> None:
        overlay_paint = skia.Paint(Color=skia.ColorSetARGB(168, 0, 0, 0))
        overlay_height = max(18, height // 7)
        canvas.drawRect(
            skia.Rect.MakeXYWH(0, height - overlay_height - 6, width, overlay_height + 6),
            overlay_paint,
        )

        font_size = max(12, overlay_height - 8)
        try:
            typeface = skia.Typeface("Arial", skia.FontStyle.Bold())
        except Exception:  # pragma: no cover - system font fallback
            typeface = skia.Typeface.MakeDefault()
        font = skia.Font(typeface, font_size)
        text_color = skia.Paint(Color=skia.ColorSetARGB(235, 255, 255, 255), AntiAlias=True)
        caption = filter_name.upper()
        sub_caption = ", ".join(primitives) if primitives else "resvg filter"
        canvas.drawString(caption, 10, height - overlay_height + font_size * 0.1, font, text_color)
        sub_font = skia.Font(typeface, max(10, font_size * 0.7))
        canvas.drawString(
            f"{sub_caption} · passes:{passes}",
            10,
            height - 8,
            sub_font,
            skia.Paint(Color=skia.ColorSetARGB(210, 200, 220, 255), AntiAlias=True),
        )

    def _draw_bounds(
        self,
        canvas,
        bounds: dict[str, float | Any],
        width: int,
        height: int,
        palette: list[skia.Color4f],
    ) -> None:
        try:
            x = float(bounds.get("x", 0.0))
            y = float(bounds.get("y", 0.0))
            w = float(bounds.get("width", width))
            h = float(bounds.get("height", height))
        except (TypeError, ValueError):
            return
        color = palette[0] if palette else skia.Color4f(1.0, 1.0, 1.0, 1.0)
        stroke = skia.Paint(
            Color=skia.Color4f(color.fR, color.fG, color.fB, 0.65),
            Style=skia.Paint.kStroke_Style,
            StrokeWidth=max(1.0, min(width, height) * 0.02),
            AntiAlias=True,
        )
        canvas.drawRect(skia.Rect.MakeXYWH(x, y, w, h), stroke)

    def _seed_hex(self, seed: int) -> str:
        base = abs(seed) % 0xFFFFFF
        return f"#{base:06X}"

    def _color4f_from_hex(self, hex_color: str) -> skia.Color4f:
        token = hex_color.strip().lstrip("#")
        if len(token) == 3:
            token = "".join(ch * 2 for ch in token)
        try:
            value = int(token, 16)
        except ValueError:
            value = 0x336699
        r = ((value >> 16) & 0xFF) / 255.0
        g = ((value >> 8) & 0xFF) / 255.0
        b = (value & 0xFF) / 255.0
        return skia.Color4f(r, g, b, 1.0)

    @staticmethod
    def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
        h = h % 1.0
        i = int(h * 6.0)
        f = h * 6.0 - i
        p = v * (1.0 - s)
        q = v * (1.0 - f * s)
        t = v * (1.0 - (1.0 - f) * s)
        i = i % 6
        if i == 0:
            r, g, b = v, t, p
        elif i == 1:
            r, g, b = q, v, p
        elif i == 2:
            r, g, b = p, v, t
        elif i == 3:
            r, g, b = p, q, v
        elif i == 4:
            r, g, b = t, p, v
        else:
            r, g, b = v, p, q
        return r, g, b


def _surface_to_png(surface) -> bytes:
    rgba = surface.to_rgba8()
    if not NUMPY_AVAILABLE:
        raise RuntimeError("numpy is required to encode raster surfaces")
    if rgba.dtype != np.uint8:
        rgba = rgba.astype(np.uint8, copy=False)
    alpha = rgba[..., 3:4].astype(np.float32)
    safe_alpha = np.where(alpha > 0.0, alpha, 1.0)
    rgb = rgba[..., :3].astype(np.float32)
    rgba[..., :3] = np.where(
        alpha > 0.0,
        np.clip((rgb * 255.0) / safe_alpha, 0.0, 255.0),
        0.0,
    ).astype(np.uint8)
    height, width, _ = rgba.shape
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = _png_chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
    )
    row_bytes = bytearray()
    for row in rgba:
        row_bytes.append(0)
        row_bytes.extend(row.tobytes())
    idat = _png_chunk(b"IDAT", zlib.compress(bytes(row_bytes)))
    iend = _png_chunk(b"IEND", b"")
    return header + ihdr + idat + iend


def _surface_from_skia_image(image):
    from svg2ooxml.render.surface import Surface

    rgba = image.toarray().astype(np.float32) / 255.0
    if image.colorType() == skia.ColorType.kBGRA_8888_ColorType:
        rgba[:, :, [0, 2]] = rgba[:, :, [2, 0]]
    rgba[..., :3] *= rgba[..., 3:4]
    return Surface(width=image.width(), height=image.height(), data=rgba)


def _float_or(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _transform_is_identity(transform: Any) -> bool:
    if transform is None:
        return True
    if not isinstance(transform, (list, tuple)) or len(transform) != 3:
        return False
    identity = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    try:
        for row_idx, row in enumerate(transform):
            if not isinstance(row, (list, tuple)) or len(row) != 3:
                return False
            for col_idx, value in enumerate(row):
                if abs(float(value) - identity[row_idx][col_idx]) >= 1e-9:
                    return False
    except (TypeError, ValueError):
        return False
    return True


def _color4f_from_paint_descriptor(
    paint_descriptor: Any, base_opacity: float
):
    if paint_descriptor is None:
        return None
    if not isinstance(paint_descriptor, dict):
        return _UNSUPPORTED_SOURCE_STYLE

    paint_type = str(paint_descriptor.get("type") or "").strip().lower()
    if not paint_type or paint_type == "none":
        return None
    if paint_type != "solid":
        return _UNSUPPORTED_SOURCE_STYLE

    token = str(paint_descriptor.get("rgb") or "").strip().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        return _UNSUPPORTED_SOURCE_STYLE
    try:
        value = int(token, 16)
    except ValueError:
        return _UNSUPPORTED_SOURCE_STYLE

    opacity = max(
        0.0,
        min(1.0, base_opacity * _float_or(paint_descriptor.get("opacity"), 1.0)),
    )
    return skia.Color4f(
        ((value >> 16) & 0xFF) / 255.0,
        ((value >> 8) & 0xFF) / 255.0,
        (value & 0xFF) / 255.0,
        opacity,
    )


def _stroke_paint_from_descriptor(stroke_descriptor: Any, base_opacity: float):
    if stroke_descriptor is None:
        return None
    if not isinstance(stroke_descriptor, dict):
        return _UNSUPPORTED_SOURCE_STYLE

    stroke_width = _float_or(stroke_descriptor.get("width"), 0.0)
    if stroke_width <= 0:
        return None
    dash_array = stroke_descriptor.get("dash_array")
    if isinstance(dash_array, list) and dash_array:
        return _UNSUPPORTED_SOURCE_STYLE

    stroke_color = _color4f_from_paint_descriptor(
        stroke_descriptor.get("paint"),
        base_opacity * _float_or(stroke_descriptor.get("opacity"), 1.0),
    )
    if stroke_color is _UNSUPPORTED_SOURCE_STYLE:
        return _UNSUPPORTED_SOURCE_STYLE
    if stroke_color is None:
        return None

    paint = skia.Paint(
        AntiAlias=True,
        Style=skia.Paint.kStroke_Style,
        StrokeWidth=stroke_width,
        Color4f=stroke_color,
    )
    cap = str(stroke_descriptor.get("cap") or "").strip().lower()
    if cap == "round":
        paint.setStrokeCap(skia.Paint.kRound_Cap)
    elif cap == "square":
        paint.setStrokeCap(skia.Paint.kSquare_Cap)
    else:
        paint.setStrokeCap(skia.Paint.kButt_Cap)

    join = str(stroke_descriptor.get("join") or "").strip().lower()
    if join == "round":
        paint.setStrokeJoin(skia.Paint.kRound_Join)
    elif join == "bevel":
        paint.setStrokeJoin(skia.Paint.kBevel_Join)
    else:
        paint.setStrokeJoin(skia.Paint.kMiter_Join)
    paint.setStrokeMiter(_float_or(stroke_descriptor.get("miter_limit"), 4.0))
    return paint


def _is_point_pair(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    return _is_number(value[0]) and _is_number(value[1])


def _is_number(value: object) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _coerce_positive(value: object | None, fallback: float | None = None) -> float:
    if _is_number(value):
        number = float(value)  # type: ignore[arg-type]
        if number > 0:
            return number
    if fallback is not None:
        return float(fallback)
    return 0.0


__all__ = ["RasterAdapter", "RasterResult"]
