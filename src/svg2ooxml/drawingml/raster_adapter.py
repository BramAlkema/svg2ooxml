"""Raster fallback adapter with optional skia rendering."""

from __future__ import annotations

import re
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from lxml import etree

try:  # pragma: no cover - skia optional during transition
    import skia  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade without skia
    skia = None

from svg2ooxml.drawingml.paint_converter import _coerce_positive, _is_number
from svg2ooxml.drawingml.skia_bridge import (
    NUMPY_AVAILABLE,
    _solid_gray_png,
    _surface_to_png,
    color_from_seed,
    draw_bounds,
    palette_for_primitives,
    render_caption,
    render_gradient_passes,
    render_surface_from_descriptor,
)

_URL_REF_RE = re.compile(r"url\(\s*#([^)]+?)\s*\)")


@dataclass
class RasterResult:
    image_bytes: bytes
    relationship_id: str
    width_px: int
    height_px: int
    metadata: dict[str, Any]


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
            surface = render_surface_from_descriptor(
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

        palette = palette_for_primitives(primitive_tags, seed=hash(filter_id))
        render_gradient_passes(
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
            draw_bounds(canvas, bounds, width_px, height_px, palette)

        filter_tag = getattr(filter_element, "tag", "")
        filter_name = filter_tag.split("}")[-1] if isinstance(filter_tag, str) else "filter"
        render_caption(canvas, width_px, height_px, filter_name, primitive_tags, passes)

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


__all__ = ["RasterAdapter", "RasterResult"]
