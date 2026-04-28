"""Skia surface rendering and image operations for raster fallbacks."""

from __future__ import annotations

import struct
import zlib
from collections.abc import Iterable
from typing import Any

try:  # pragma: no cover - skia optional during transition
    import skia  # type: ignore
except Exception:  # pragma: no cover - gracefully degrade without skia
    skia = None

from svg2ooxml.common.numpy_compat import NUMPY_AVAILABLE, REAL_NUMPY
from svg2ooxml.drawingml.paint_converter import (
    _UNSUPPORTED_SOURCE_STYLE,
    _color4f_from_paint_descriptor,
    _float_or,
    _is_point_pair,
    _stroke_paint_from_descriptor,
    _transform_is_identity,
)
from svg2ooxml.render.rgba import encode_rgba8_png, png_chunk

np = REAL_NUMPY

# ------------------------------------------------------------------ #
# PNG encoding                                                       #
# ------------------------------------------------------------------ #


def _solid_gray_png(width: int, height: int, gray: int) -> bytes:
    width = max(1, width)
    height = max(1, height)
    gray = max(0, min(255, gray))
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = png_chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0),
    )
    row = bytes([0]) + bytes([gray] * width)
    pixel_rows = row * height
    idat = png_chunk(b"IDAT", zlib.compress(pixel_rows))
    iend = png_chunk(b"IEND", b"")
    return header + ihdr + idat + iend


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
    return encode_rgba8_png(rgba.tobytes(), width, height)


def _surface_from_skia_image(image):
    from svg2ooxml.render.surface import Surface

    rgba = image.toarray().astype(np.float32) / 255.0
    if image.colorType() == skia.ColorType.kBGRA_8888_ColorType:
        rgba[:, :, [0, 2]] = rgba[:, :, [2, 0]]
    rgba[..., :3] *= rgba[..., 3:4]
    return Surface(width=image.width(), height=image.height(), data=rgba)


# ------------------------------------------------------------------ #
# Skia path from descriptor                                         #
# ------------------------------------------------------------------ #


def descriptor_to_skia_path(descriptor: dict[str, Any]):
    """Convert a geometry descriptor to a skia Path, or None."""
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


# ------------------------------------------------------------------ #
# Surface rendering from descriptor                                  #
# ------------------------------------------------------------------ #


def render_surface_from_descriptor(
    *,
    descriptor: dict[str, Any],
    bounds: dict[str, float | Any] | None,
    width_px: int,
    height_px: int,
):
    """Render a source graphic descriptor into a skia Surface, or None."""
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

    path = descriptor_to_skia_path(descriptor)
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


# ------------------------------------------------------------------ #
# Palette and color helpers                                          #
# ------------------------------------------------------------------ #


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
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


def color_from_seed(seed: int):
    hue = (seed % 360) / 360.0
    r, g, b = hsv_to_rgb(hue, 0.55, 0.95)
    return skia.Color4f(r, g, b, 1.0)


def seed_hex(seed: int) -> str:
    base = abs(seed) % 0xFFFFFF
    return f"#{base:06X}"


def color4f_from_hex(hex_color: str):
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


def palette_for_primitives(primitives: Iterable[str], seed: int) -> list:
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
            seed_hex(seed_val),
            seed_hex(seed_val * 3),
            seed_hex(seed_val * 7),
            seed_hex(seed_val * 11),
        ]
    return [color4f_from_hex(hex_str) for hex_str in colors]


# ------------------------------------------------------------------ #
# Canvas rendering helpers                                           #
# ------------------------------------------------------------------ #


def render_gradient_passes(
    canvas,
    width: int,
    height: int,
    palette: list,
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

        points = _gradient_points(width, height, index, passes, descriptor, bounds)
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
    width: int,
    height: int,
    index: int,
    passes: int,
    descriptor: dict[str, Any] | None,
    bounds: dict[str, float | Any] | None,
) -> list:
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


def render_caption(
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


def draw_bounds(
    canvas,
    bounds: dict[str, float | Any],
    width: int,
    height: int,
    palette: list,
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
