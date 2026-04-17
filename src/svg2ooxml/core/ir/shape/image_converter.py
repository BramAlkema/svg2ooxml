"""Image extraction and embedding methods for shape conversion."""

from __future__ import annotations

import io
from pathlib import Path as FsPath
from typing import Any

from lxml import etree

from svg2ooxml.core.ir.shape_converters_utils import (
    _compute_bbox,
    _guess_image_format,
    _parse_float,
)
from svg2ooxml.core.styling import style_runtime as styles_runtime
from svg2ooxml.core.traversal.viewbox import (
    ViewportEngine,
    parse_preserve_aspect_ratio,
    resolve_viewbox_dimensions,
)
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.scene import Image, MaskInstance, MaskRef
from svg2ooxml.services.image_service import ImageResource, ImageService


class ShapeImageMixin:
    """Mixin housing image conversion helpers."""

    def _convert_image(self, *, element: etree._Element, coord_space):
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
        href = self._normalize_image_href(href)
        if not href:
            return None
        width = _parse_float(element.get("width"))
        height = _parse_float(element.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            return None
        x = _parse_float(element.get("x"), default=0.0) or 0.0
        y = _parse_float(element.get("y"), default=0.0) or 0.0

        image_policy = self._policy_options("image")
        style = styles_runtime.extract_style(self, element)

        image_service = self._services.image_service
        resource: ImageResource | None = None
        if href and image_service:
            resource = image_service.resolve(href)
        if resource is None and href:
            resource = ImageService._data_uri_resolver(href)
        if resource is None and href:
            resource = self._resolve_image_from_source_path(href)

        color_service = getattr(self._services, "color_space_service", None)
        color_result = None
        if resource and color_service and image_policy:
            normalization = image_policy.get("colorspace_normalization", "rgb")
            color_result = color_service.normalize_resource(
                resource, normalization=normalization
            )
            resource = color_result.resource

        format_hint = _guess_image_format(
            href,
            resource.data if resource else None,
            resource.mime_type if resource else None,
        )

        viewport_rect = Rect(x, y, width, height)
        visible_rect, image_layout = self._resolve_image_layout(
            element=element,
            viewport_rect=viewport_rect,
            resource=resource,
            format_hint=format_hint,
        )
        rect_points = [
            (visible_rect.x, visible_rect.y),
            (visible_rect.x + visible_rect.width, visible_rect.y),
            (
                visible_rect.x + visible_rect.width,
                visible_rect.y + visible_rect.height,
            ),
            (visible_rect.x, visible_rect.y + visible_rect.height),
        ]
        transformed_points = [
            coord_space.apply_point(px, py) for (px, py) in rect_points
        ]
        bbox = _compute_bbox(transformed_points)
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        metadata: dict[str, Any] = dict(style.metadata)
        if resource and resource.source:
            metadata["image_source"] = resource.source
        if href:
            metadata["href"] = href
        metadata["image_layout"] = image_layout
        self._attach_policy_metadata(metadata, "image")
        if image_policy:
            self._attach_policy_metadata(metadata, "image", extra=image_policy)
        if color_result:
            policy_meta = metadata.setdefault("policy", {}).setdefault("image", {})
            if color_result.result.converted:
                policy_meta["colorspace_mode"] = color_result.result.mode
                if color_result.result.warnings:
                    policy_meta["colorspace_warnings"] = list(
                        color_result.result.warnings
                    )
            if color_result.result.metadata:
                policy_meta.setdefault(
                    "colorspace_metadata", color_result.result.metadata
                )

        image = Image(
            origin=Point(bbox.x, bbox.y),
            size=bbox,
            data=resource.data if resource else None,
            format=format_hint,
            href=href,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            transform=None,
            metadata=metadata,
        )
        self._process_mask_metadata(image)
        self._trace_geometry_decision(element, "native", image.metadata)
        self._trace_stage(
            "image_embedded",
            stage="image",
            metadata={
                "format": format_hint,
                "embedded_data": bool(resource and resource.data),
                "href": href if href else None,
            },
            subject=element.get("id"),
        )
        return image

    def _resolve_image_layout(
        self,
        *,
        element: etree._Element,
        viewport_rect: Rect,
        resource: ImageResource | None,
        format_hint: str,
    ) -> tuple[Rect, dict[str, Any]]:
        """Resolve the actual painted image box inside the SVG image viewport."""

        layout = {
            "viewport": {
                "x": float(viewport_rect.x),
                "y": float(viewport_rect.y),
                "width": float(viewport_rect.width),
                "height": float(viewport_rect.height),
            },
            "content_offset": {"x": 0.0, "y": 0.0},
            "content_size": {
                "width": float(viewport_rect.width),
                "height": float(viewport_rect.height),
            },
            "preserve_aspect_ratio": element.get("preserveAspectRatio") or "",
        }

        intrinsic_size = self._resolve_intrinsic_image_size(resource, format_hint)
        if intrinsic_size is None:
            return viewport_rect, layout

        intrinsic_width, intrinsic_height = intrinsic_size
        if intrinsic_width <= 0 or intrinsic_height <= 0:
            return viewport_rect, layout

        preserve = parse_preserve_aspect_ratio(element.get("preserveAspectRatio"))
        if preserve.is_none or preserve.meet_or_slice.lower() == "slice":
            return viewport_rect, layout

        engine = ViewportEngine()
        result = engine.compute(
            (0.0, 0.0, intrinsic_width, intrinsic_height),
            (float(viewport_rect.width), float(viewport_rect.height)),
            preserve,
        )

        content_rect = Rect(
            viewport_rect.x + result.translate_x,
            viewport_rect.y + result.translate_y,
            intrinsic_width * result.scale_x,
            intrinsic_height * result.scale_y,
        )
        layout["content_offset"] = {
            "x": float(content_rect.x - viewport_rect.x),
            "y": float(content_rect.y - viewport_rect.y),
        }
        layout["content_size"] = {
            "width": float(content_rect.width),
            "height": float(content_rect.height),
        }
        return content_rect, layout

    def _resolve_intrinsic_image_size(
        self,
        resource: ImageResource | None,
        format_hint: str,
    ) -> tuple[float, float] | None:
        if resource is None or not resource.data:
            return None
        if format_hint == "svg":
            return self._resolve_svg_intrinsic_image_size(resource.data)
        return self._resolve_raster_intrinsic_image_size(resource.data)

    def _resolve_svg_intrinsic_image_size(
        self,
        payload: bytes,
    ) -> tuple[float, float] | None:
        try:
            root = etree.fromstring(payload)
        except (etree.XMLSyntaxError, ValueError, TypeError):
            return None
        if not isinstance(root.tag, str) or root.tag.split("}", 1)[-1] != "svg":
            return None

        unit_converter = getattr(self._services, "unit_converter", None)
        if unit_converter is None:
            return None

        try:
            width_px, height_px, _, _ = resolve_viewbox_dimensions(root, unit_converter)
        except (TypeError, ValueError):
            return None
        if width_px <= 0 or height_px <= 0:
            return None
        return (float(width_px), float(height_px))

    @staticmethod
    def _resolve_raster_intrinsic_image_size(
        payload: bytes,
    ) -> tuple[float, float] | None:
        try:
            from PIL import Image as PILImage
        except ImportError:
            return None

        try:
            with PILImage.open(io.BytesIO(payload)) as image:
                width, height = image.size
        except (OSError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return (float(width), float(height))

    @staticmethod
    def _normalize_image_href(href: str | None) -> str | None:
        if href is None:
            return None
        token = href.strip()
        if token.lower().startswith("url(") and token.endswith(")"):
            token = token[4:-1].strip()
            if (token.startswith("'") and token.endswith("'")) or (
                token.startswith('"') and token.endswith('"')
            ):
                token = token[1:-1]
        return token or None

    def _resolve_image_from_source_path(self, href: str) -> ImageResource | None:
        token = href.strip().lower()
        if token.startswith(("http://", "https://", "ftp://", "#")):
            return None
        source_path = None
        if hasattr(self._services, "resolve"):
            source_path = self._services.resolve("source_path")
        if not isinstance(source_path, str) or not source_path:
            return None
        try:
            base_dir = FsPath(source_path).expanduser().resolve().parent
            target = FsPath(href).expanduser()
            if not target.is_absolute():
                target = (base_dir / target).resolve()
            else:
                target = target.resolve()
            if not target.is_file():
                return None
            return ImageResource(data=target.read_bytes(), source="file")
        except Exception:
            return None
