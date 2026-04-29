"""Preview SVG, placeholder, and bounds helpers for raster fallbacks."""

from __future__ import annotations

from typing import Any

from lxml import etree

from svg2ooxml.drawingml.raster_adapter_optional import (
    _DEFAULT_PLACEHOLDER_SIZE,
    adapter_skia,
)
from svg2ooxml.drawingml.raster_bounds import resolved_filter_bounds
from svg2ooxml.drawingml.skia_bridge import (
    draw_bounds,
    palette_for_primitives,
    render_caption,
    render_gradient_passes,
)


class RasterAdapterPreviewRuntimeMixin:
    """Build preview markup and generated raster placeholders."""

    def _build_preview_svg_markup(
        self,
        *,
        filter_clone: etree._Element,
        preview_filter_id: str,
        width_px: int,
        height_px: int,
        context,
    ) -> str:
        width_px, height_px = self._safe_raster_size(
            (width_px, height_px),
            default=_DEFAULT_PLACEHOLDER_SIZE,
        )
        descriptor, bounds = self._descriptor_payload(context)
        resolved_bounds = self._resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=width_px,
            default_height=height_px,
        )
        return self._preview_builder.build_preview_svg_markup(
            filter_clone=filter_clone,
            preview_filter_id=preview_filter_id,
            width_px=width_px,
            height_px=height_px,
            context=context,
            resolved_bounds=resolved_bounds,
        )

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
        width_px, height_px = self._safe_raster_size(
            (width_px, height_px),
            default=_DEFAULT_PLACEHOLDER_SIZE,
        )
        resolved_bounds = self._resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=width_px,
            default_height=height_px,
        )
        return self._preview_builder.build_source_svg_markup(
            source_element=source_element,
            source_root=source_root,
            resolved_bounds=resolved_bounds,
            width_px=width_px,
            height_px=height_px,
        )

    def _source_element_from_context(self, context) -> etree._Element | None:
        return self._preview_builder.source_element_from_context(context)

    def _iter_defs_children(self, source_root: etree._Element) -> list[etree._Element]:
        return self._preview_builder.iter_defs_children(source_root)

    def _build_source_subtree(
        self,
        *,
        source_element: etree._Element | None,
        source_root: etree._Element | None,
        preview_filter_id: str | None,
        svg_ns: str,
    ) -> etree._Element | None:
        return self._preview_builder.build_source_subtree(
            source_element=source_element,
            source_root=source_root,
            preview_filter_id=preview_filter_id,
            svg_ns=svg_ns,
        )

    def _rewrite_filter_reference(
        self, element: etree._Element, preview_filter_id: str | None
    ) -> None:
        self._preview_builder.rewrite_filter_reference(element, preview_filter_id)

    def _preview_viewbox(
        self,
        *,
        bounds: dict[str, float | Any] | None,
        width_px: int,
        height_px: int,
        preserve_user_space: bool = False,
    ) -> str:
        return self._preview_builder.preview_viewbox(
            bounds=bounds,
            width_px=width_px,
            height_px=height_px,
            preserve_user_space=preserve_user_space,
        )

    def _localize_source_subtree(
        self,
        source_subtree: etree._Element,
        bounds: dict[str, float | Any] | None,
        svg_ns: str,
        *,
        preserve_user_space: bool = False,
    ) -> etree._Element:
        del svg_ns
        return self._preview_builder.localize_source_subtree(
            source_subtree,
            bounds,
            preserve_user_space=preserve_user_space,
        )

    def _flatten_transforms_in_place(
        self,
        element: etree._Element,
        inherited_transform: str = "",
    ) -> None:
        self._preview_builder.flatten_transforms_in_place(element, inherited_transform)

    def _requires_original_user_space(
        self,
        source_subtree: etree._Element,
        source_root: etree._Element | None,
    ) -> bool:
        return self._preview_builder.requires_original_user_space(
            source_subtree,
            source_root,
        )

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
    ):
        skia = adapter_skia()
        default_size = self._safe_raster_size(
            default_size,
            default=_DEFAULT_PLACEHOLDER_SIZE,
        )
        width_px, height_px = self._safe_raster_size(
            (width_px, height_px),
            default=default_size,
        )
        if skia is None:
            return self._generate_filter_placeholder(
                filter_id=filter_id,
                primitive_tags=primitive_tags,
                filter_units=filter_units,
                primitive_units=primitive_units,
                complexity=complexity,
                default_size=default_size,
            )

        try:
            surface = skia.Surface(int(max(1, width_px)), int(max(1, height_px)))
        except Exception:  # pragma: no cover - defensive
            return self._generate_filter_placeholder(
                filter_id=filter_id,
                primitive_tags=primitive_tags,
                filter_units=filter_units,
                primitive_units=primitive_units,
                complexity=complexity,
                default_size=default_size,
            )

        canvas = surface.getCanvas()
        canvas.clear(skia.Color4f(0.0, 0.0, 0.0, 0.0))

        palette = palette_for_primitives(
            primitive_tags,
            seed=self._stable_seed(filter_id),
        )
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
        filter_name = (
            filter_tag.split("}")[-1] if isinstance(filter_tag, str) else "filter"
        )
        render_caption(canvas, width_px, height_px, filter_name, primitive_tags, passes)

        image = surface.makeImageSnapshot()
        if image is None:
            return self._generate_filter_placeholder(
                filter_id=filter_id,
                primitive_tags=primitive_tags,
                filter_units=filter_units,
                primitive_units=primitive_units,
                complexity=complexity,
                default_size=default_size,
            )

        encoded = image.encodeToData()
        if encoded is None:
            return self._generate_filter_placeholder(
                filter_id=filter_id,
                primitive_tags=primitive_tags,
                filter_units=filter_units,
                primitive_units=primitive_units,
                complexity=complexity,
                default_size=default_size,
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
        return self._raster_result(
            image_bytes=bytes(encoded),
            relationship_id=relationship_id,
            width_px=width_px,
            height_px=height_px,
            metadata=metadata,
        )

    def _resolved_filter_bounds(
        self,
        *,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
        default_width: float,
        default_height: float,
    ) -> dict[str, float] | None:
        return resolved_filter_bounds(
            descriptor=descriptor,
            bounds=bounds,
            default_width=default_width,
            default_height=default_height,
        )


__all__ = ["RasterAdapterPreviewRuntimeMixin"]
