"""Raster fallback adapter with optional skia rendering."""

from __future__ import annotations

import math
import struct
import zlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Tuple

import numpy as np
from lxml import etree

try:  # pragma: no cover - skia optional during transition
    import skia  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade without skia
    skia = None


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
        default_size: Tuple[int, int] = (192, 128),
    ) -> RasterResult:
        """Render a PNG fallback for ``filter_id`` using skia when available."""

        descriptor, bounds = self._descriptor_payload(context)
        primitive_tags = tuple(descriptor.get("primitive_tags", ())) if descriptor else ()
        filter_units = (descriptor or {}).get("filter_units")
        primitive_units = (descriptor or {}).get("primitive_units")
        complexity = max(1, len(primitive_tags)) if primitive_tags else 1

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

        width_px, height_px = self._derive_dimensions(context, default_size, descriptor, bounds)
        passes = self._pass_count(descriptor, complexity)
        scale = self._scale_factor(descriptor, bounds, complexity)

        surface = self._render_preview_with_resvg(filter_element, filter_id, width_px, height_px, context=context)
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
            if bounds:
                metadata["bounds"] = bounds
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
        if skia is None:
            return None
        try:
            from svg2ooxml.core.resvg.normalizer import normalize_svg_string
            from svg2ooxml.render.pipeline import render
            from svg2ooxml.core.resvg.parser.options import Options
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

        svg_root = etree.Element(
            f"{{{svg_ns}}}svg",
            nsmap={None: svg_ns},
            attrib={
                "width": str(max(1, int(width_px))),
                "height": str(max(1, int(height_px))),
                "viewBox": f"0 0 {max(1, int(width_px))} {max(1, int(height_px))}",
            },
        )
        defs = etree.SubElement(svg_root, f"{{{svg_ns}}}defs")
        defs.append(filter_clone)
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

        svg_markup = etree.tostring(svg_root, encoding="unicode")

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
            options = Options(resources_dir=resources_dir) if resources_dir else None
            normalized = normalize_svg_string(svg_markup, options=options)
            return render(normalized.tree)
        except Exception:  # pragma: no cover - renderer failure
            return None

    def _render_placeholder_preview(
        self,
        *,
        filter_id: str,
        filter_element,
        primitive_tags: Tuple[str, ...],
        filter_units,
        primitive_units,
        complexity: int,
        width_px: int,
        height_px: int,
        passes: int,
        scale: float,
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
        default_size: Tuple[int, int],
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
        defaults: Tuple[int, int],
        descriptor: dict[str, Any] | None,
        bounds: dict[str, float | Any] | None,
    ) -> Tuple[int, int]:
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
        region = (descriptor or {}).get("filter_region") if descriptor else None
        if isinstance(region, dict):
            try:
                reg_width = _coerce_positive(region.get("width"))
                reg_height = _coerce_positive(region.get("height"))
                units = (descriptor or {}).get("filter_units")
                if units == "objectBoundingBox" and bounds:
                    reg_width = reg_width * _coerce_positive(bounds.get("width"), defaults[0])
                    reg_height = reg_height * _coerce_positive(bounds.get("height"), defaults[1])
                width = max(width, reg_width or width)
                height = max(height, reg_height or height)
            except (TypeError, ValueError):
                pass

        width *= self._viewport_scale(descriptor)
        height *= self._viewport_scale(descriptor)
        return int(min(width, 1024)), int(min(height, 1024))

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
    def _hsv_to_rgb(h: float, s: float, v: float) -> Tuple[float, float, float]:
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
    if rgba.dtype != np.uint8:
        rgba = rgba.astype(np.uint8, copy=False)
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
