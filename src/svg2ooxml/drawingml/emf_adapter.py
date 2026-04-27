"""Filter EMF adapter used by the DrawingML renderer."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from svg2ooxml.common.units import px_to_emu
from svg2ooxml.drawingml.emf_primitives import (
    DEFAULT_FILTER_PALETTE,
    PaletteResolver,
    adjust_lightness,
    colorref,
    ellipse_points,
    function_curve,
    kernel_value_color,
    matrix_value_color,
    normalise_value,
    polyline,
    rect_points,
    resolve_with_palette,
    rounded_rect,
    safe_float,
)
from svg2ooxml.io.emf import EMFBlob


@dataclass(slots=True)
class EMFResult:
    """Container describing a generated EMF asset."""

    emf_bytes: bytes
    relationship_id: str
    width_emu: int
    height_emu: int
    metadata: dict[str, Any]


class EMFAdapter:
    """Generate deterministic EMF assets for filter fallbacks."""

    _DEFAULT_SIZE_PX = (96.0, 64.0)

    def __init__(self, *, palette_resolver: PaletteResolver | None = None) -> None:
        self._counter = 0
        self._cache: dict[tuple[str, str], EMFResult] = {}
        self._palette_resolver: PaletteResolver | None = palette_resolver

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_filter(self, filter_type: str, metadata: dict[str, Any] | None = None) -> EMFResult:
        """Return an EMF asset for ``filter_type`` using the supplied metadata."""

        normalised_meta = metadata or {}
        key = self._cache_key(filter_type, normalised_meta)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        if filter_type == "composite":
            result = self._render_composite(normalised_meta)
        elif filter_type == "blend":
            result = self._render_blend(normalised_meta)
        elif filter_type == "component_transfer":
            result = self._render_component_transfer(normalised_meta)
        elif filter_type == "color_matrix":
            result = self._render_color_matrix(normalised_meta)
        elif filter_type == "displacement_map":
            result = self._render_displacement_map(normalised_meta)
        elif filter_type == "turbulence":
            result = self._render_turbulence(normalised_meta)
        elif filter_type == "convolve_matrix":
            result = self._render_convolve_matrix(normalised_meta)
        elif filter_type == "tile":
            result = self._render_tile(normalised_meta)
        elif filter_type == "diffuse_lighting":
            result = self._render_diffuse_lighting(normalised_meta)
        elif filter_type == "specular_lighting":
            result = self._render_specular_lighting(normalised_meta)
        else:
            result = self._render_placeholder(normalised_meta)

        self._cache[key] = result
        return result

    def set_palette_resolver(self, resolver: PaletteResolver | None) -> None:
        """Install a palette resolver that can override filter colours."""

        self._palette_resolver = resolver

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _render_composite(self, metadata: dict[str, Any]) -> EMFResult:
        operator = str(metadata.get("operator", "over")).lower()
        width_emu, height_emu = self._size_emu()

        blob = EMFBlob(width_emu, height_emu)
        background = blob.get_solid_brush(colorref(self._color("composite", "background", "#F5F6FF", metadata)))
        blob.fill_rectangle(0, 0, width_emu, height_emu, background)

        first = blob.get_solid_brush(colorref(self._color("composite", "primary_layer", "#4F83FF", metadata)))
        second = blob.get_solid_brush(colorref(self._color("composite", "secondary_layer", "#FF7A85", metadata)))
        outline = blob.get_pen(colorref(self._color("composite", "outline", "#203364", metadata)), max(1, width_emu // 120))

        blob.fill_polygon(rect_points(12, 14, 44, 28), brush_handle=first)
        blob.draw_polygon(rect_points(12, 14, 44, 28), brush_handle=None, pen_handle=outline)

        blob.fill_polygon(rect_points(40, 26, 44, 28), brush_handle=second)
        blob.draw_polygon(rect_points(40, 26, 44, 28), brush_handle=None, pen_handle=outline)

        if operator == "arithmetic":
            accent = blob.get_pen(colorref(self._color("composite", "accent", "#1B1B1B", metadata)), max(1, width_emu // 160))
            blob.stroke_polyline(polyline([(26, 26), (70, 44)]), pen_handle=accent)

        return self._finalise(blob, metadata | {"filter_type": "composite", "operator": operator})

    def _render_blend(self, metadata: dict[str, Any]) -> EMFResult:
        mode = str(metadata.get("mode", "normal")).lower()
        width_emu, height_emu = self._size_emu()

        blob = EMFBlob(width_emu, height_emu)
        background = blob.get_solid_brush(colorref(self._color("blend", "background", "#FDF3F8", metadata)))
        blob.fill_rectangle(0, 0, width_emu, height_emu, background)

        left = blob.get_solid_brush(colorref(self._color("blend", "left", "#FFBF69", metadata)))
        right = blob.get_solid_brush(colorref(self._color("blend", "right", "#5A8DEE", metadata)))
        overlap = blob.get_solid_brush(colorref(self._color("blend", "overlap", "#B57FD8", metadata)))

        blob.fill_polygon(rounded_rect(18, 18, 34, 28, radius=8), brush_handle=left)
        blob.fill_polygon(rounded_rect(44, 20, 34, 28, radius=8), brush_handle=right)
        blob.fill_polygon(rounded_rect(32, 24, 24, 20, radius=6), brush_handle=overlap)

        if mode in {"multiply", "screen", "darken", "lighten"}:
            accent = blob.get_pen(colorref(self._color("blend", "accent", "#3A3A3A", metadata)), max(1, width_emu // 200))
            blob.stroke_polyline(polyline([(30, 48), (48, 30)]), pen_handle=accent)

        return self._finalise(blob, metadata | {"filter_type": "blend", "mode": mode})

    def _render_placeholder(self, metadata: dict[str, Any]) -> EMFResult:
        width_emu, height_emu = self._size_emu()
        blob = EMFBlob(width_emu, height_emu)
        brush = blob.get_solid_brush(colorref("#6B6B6B"))
        blob.fill_rectangle(0, 0, width_emu, height_emu, brush)
        return self._finalise(blob, metadata | {"filter_type": "generic", "placeholder": True})

    def _render_component_transfer(self, metadata: dict[str, Any]) -> EMFResult:
        width_emu, height_emu = self._size_emu()
        blob = EMFBlob(width_emu, height_emu)
        background = blob.get_solid_brush(colorref(self._color("component_transfer", "background", "#F4F6FB", metadata)))
        blob.fill_rectangle(0, 0, width_emu, height_emu, background)

        axis_pen = blob.get_pen(colorref(self._color("component_transfer", "axis", "#203040", metadata)), max(1, width_emu // 320))
        graph_pen = blob.get_pen(colorref(self._color("component_transfer", "graph", "#1B1B1B", metadata)), max(1, width_emu // 360))
        grid_pen = blob.get_pen(colorref(self._color("component_transfer", "grid", "#314A72", metadata)), max(1, width_emu // 480))

        channel_order = ["r", "g", "b", "a"]
        base_channel_colors = {
            "r": "#ED6B6B",
            "g": "#5BB974",
            "b": "#4F83FF",
            "a": "#9E9E9E",
        }
        functions = metadata.get("functions") or []
        function_map = {entry.get("channel"): entry for entry in functions if isinstance(entry, dict)}

        column_width = 18.0
        column_height = 30.0
        top = 18.0
        left_margin = 10.0
        spacing = 6.0

        for index, channel in enumerate(channel_order):
            left = left_margin + index * (column_width + spacing)
            func = function_map.get(channel, {})
            base_color = self._color("component_transfer", f"channel_{channel}", base_channel_colors.get(channel, "#C0C0C0"), metadata)
            rect = rect_points(left, top, column_width, column_height)
            brush = blob.get_solid_brush(colorref(base_color))
            blob.draw_polygon(rect, brush_handle=brush, pen_handle=axis_pen)

            baseline = [(left, top + column_height), (left + column_width, top + column_height)]
            blob.stroke_polyline(polyline(baseline), pen_handle=grid_pen)
            vertical = [(left, top), (left, top + column_height)]
            blob.stroke_polyline(polyline(vertical), pen_handle=grid_pen)

            curve = function_curve(func, left, top, column_width, column_height)
            if curve:
                blob.stroke_polyline(polyline(curve), pen_handle=graph_pen)

        return self._finalise(blob, metadata | {"filter_type": "component_transfer"})

    def _render_color_matrix(self, metadata: dict[str, Any]) -> EMFResult:
        width_emu, height_emu = self._size_emu()
        blob = EMFBlob(width_emu, height_emu)

        background = blob.get_solid_brush(colorref(self._color("color_matrix", "background", "#F7F9FF", metadata)))
        blob.fill_rectangle(0, 0, width_emu, height_emu, background)

        values = list(metadata.get("values") or [])
        if not values:
            source = metadata.get("matrix_source")
            if isinstance(source, str):
                values = [safe_float(token) for token in source.replace(",", " ").split()]
        total = len(values)
        columns = 5
        rows = max(1, (total + columns - 1) // columns)
        left_px, top_px = 8.0, 12.0
        cell_w = 16.0
        cell_h = 12.0
        gap = 3.0

        pen = blob.get_pen(colorref(self._color("color_matrix", "grid", "#2F3E6B", metadata)), max(1, width_emu // 320))
        for index, value in enumerate(values[: rows * columns]):
            row = index // columns
            col = index % columns
            x = left_px + col * (cell_w + gap)
            y = top_px + row * (cell_h + gap)
            brush = blob.get_solid_brush(colorref(matrix_value_color(value)))
            rect = rect_points(x, y, cell_w, cell_h)
            blob.draw_polygon(rect, brush_handle=brush, pen_handle=pen)

        header_pen = blob.get_pen(colorref(self._color("color_matrix", "header", "#90A3DC", metadata)), max(1, width_emu // 360))
        width_total = columns * (cell_w + gap) - gap
        blob.stroke_polyline(
            polyline([(left_px - 2.0, top_px - 4.0), (left_px + width_total + 4.0, top_px - 1.0)]),
            pen_handle=header_pen,
        )

        return self._finalise(
            blob,
            {
                "filter_type": "color_matrix",
                "matrix_type": metadata.get("matrix_type", "matrix"),
                "value_count": total,
                "values": tuple(values[: rows * columns]),
            },
        )

    def _render_displacement_map(self, metadata: dict[str, Any]) -> EMFResult:
        width_emu, height_emu = self._size_emu()
        blob = EMFBlob(width_emu, height_emu)

        background = blob.get_solid_brush(colorref(self._color("displacement_map", "background", "#EDF2FF", metadata)))
        blob.fill_rectangle(0, 0, width_emu, height_emu, background)

        grid_pen = blob.get_pen(colorref(self._color("displacement_map", "grid", "#7C96FF", metadata)), max(1, width_emu // 280))
        warp_pen = blob.get_pen(colorref(self._color("displacement_map", "warp", "#203A84", metadata)), max(1, width_emu // 220))
        accent_pen = blob.get_pen(colorref(self._color("displacement_map", "accent", "#FF6B6B", metadata)), max(1, width_emu // 200))

        scale = float(metadata.get("scale") or 0.0)
        amplitude = max(3.0, min(18.0, abs(scale) * 1.5 + 4.0))
        rows, cols = 6, 6
        left_px, top_px = 10.0, 12.0
        width_px = 76.0
        height_px = 44.0
        step_x = width_px / (cols - 1)
        step_y = height_px / (rows - 1)

        def _warp_point(col: int, row: int) -> tuple[float, float]:
            base_x = left_px + col * step_x
            base_y = top_px + row * step_y
            offset_x = math.sin((col + 1) * 0.6 + scale * 0.05 * (row + 1))
            offset_y = math.cos((row + 1) * 0.7 + scale * 0.04 * (col + 1))
            return (
                base_x + offset_x * amplitude,
                base_y + offset_y * amplitude * 0.55,
            )

        for row in range(rows):
            row_points = [_warp_point(col, row) for col in range(cols)]
            blob.stroke_polyline(polyline(row_points), pen_handle=grid_pen)

        for col in range(cols):
            col_points = [_warp_point(col, row) for row in range(rows)]
            blob.stroke_polyline(polyline(col_points), pen_handle=warp_pen)

        arrow_y = top_px + height_px + 6.0
        arrow = [
            (left_px - 4.0, arrow_y + 4.0),
            (left_px + width_px * 0.35, arrow_y),
            (left_px + width_px * 0.7, arrow_y + 5.0),
            (left_px + width_px + 6.0, arrow_y - 2.0),
        ]
        blob.stroke_polyline(polyline(arrow), pen_handle=accent_pen)

        return self._finalise(blob, metadata | {"filter_type": "displacement_map"})

    def _render_turbulence(self, metadata: dict[str, Any]) -> EMFResult:
        width_emu, height_emu = self._size_emu()
        blob = EMFBlob(width_emu, height_emu)

        base_brush = blob.get_solid_brush(colorref(self._color("turbulence", "background", "#F2F6FF", metadata)))
        blob.fill_rectangle(0, 0, width_emu, height_emu, base_brush)

        base_fx = float(metadata.get("base_frequency_x") or 0.0)
        base_fy = float(metadata.get("base_frequency_y") or 0.0)
        seed = float(metadata.get("seed") or 0.0)
        octaves = max(1, int(metadata.get("num_octaves") or 1))
        stitch = bool(metadata.get("stitch_tiles"))

        left_px, top_px = 6.0, 10.0
        width_px = 86.0
        height_px = 44.0
        center_y = top_px + height_px * 0.5

        pens = [
            blob.get_pen(colorref(self._color("turbulence", "wave_0", "#6486FF", metadata)), max(1, width_emu // 260)),
            blob.get_pen(colorref(self._color("turbulence", "wave_1", "#314A8A", metadata)), max(1, width_emu // 280)),
            blob.get_pen(colorref(self._color("turbulence", "wave_2", "#90A4FF", metadata)), max(1, width_emu // 300)),
            blob.get_pen(colorref(self._color("turbulence", "wave_3", "#2A3563", metadata)), max(1, width_emu // 320)),
        ]

        base_amplitude = max(5.0, min(20.0, (base_fx + base_fy + 0.2) * 60.0))
        two_pi = 2.0 * math.pi

        for octave in range(octaves):
            pen = pens[octave % len(pens)]
            freq = max(0.3, (base_fx + base_fy + 0.05) * (octave + 1))
            amplitude = base_amplitude / (octave + 1.2)
            phase = seed * 0.25 + octave * 1.1
            points: list[tuple[float, float]] = []
            for step in range(101):
                t = step / 100.0
                x = left_px + t * width_px
                wave = math.sin(two_pi * freq * t + phase)
                blend = math.cos(two_pi * (freq * 0.5) * t + phase * 0.5)
                offset = wave * amplitude + blend * (amplitude * 0.25)
                if stitch:
                    offset *= math.sin(math.pi * t) ** 2
                y = center_y + offset
                points.append((x, y))
            blob.stroke_polyline(polyline(points), pen_handle=pen)

        return self._finalise(blob, metadata | {"filter_type": "turbulence"})

    def _render_convolve_matrix(self, metadata: dict[str, Any]) -> EMFResult:
        width_emu, height_emu = self._size_emu()
        blob = EMFBlob(width_emu, height_emu)

        background = blob.get_solid_brush(colorref(self._color("convolve_matrix", "background", "#F5F7FF", metadata)))
        blob.fill_rectangle(0, 0, width_emu, height_emu, background)

        order = metadata.get("order") or (3, 3)
        order_x, order_y = int(order[0]), int(order[1])
        kernel = list(metadata.get("kernel") or [])
        divisor = float(metadata.get("divisor") or 1.0)

        left_px, top_px = 12.0, 12.0
        cell = 14.0
        gap = 4.0
        pen = blob.get_pen(colorref(self._color("convolve_matrix", "grid", "#314074", metadata)), max(1, width_emu // 340))

        for row in range(order_y):
            for col in range(order_x):
                index = row * order_x + col
                value = float(kernel[index]) if index < len(kernel) else 0.0
                brush = blob.get_solid_brush(colorref(kernel_value_color(value)))
                rect = rect_points(left_px + col * (cell + gap), top_px + row * (cell + gap), cell, cell)
                blob.draw_polygon(rect, brush_handle=brush, pen_handle=pen)

        accent_pen = blob.get_pen(colorref(self._color("convolve_matrix", "accent", "#FF6A6A", metadata)), max(1, width_emu // 360))
        blob.stroke_polyline(
            polyline([(left_px - 3.0, top_px + order_y * (cell + gap) + 4.0), (left_px + order_x * (cell + gap), top_px - 2.0)]),
            pen_handle=accent_pen,
        )

        return self._finalise(
            blob,
            {
                "filter_type": "convolve_matrix",
                "order": (order_x, order_y),
                "divisor": divisor,
                "kernel": tuple(kernel[: order_x * order_y]),
                "kernel_source": metadata.get("kernel_source", ""),
            },
        )

    def _render_tile(self, metadata: dict[str, Any]) -> EMFResult:
        width_emu, height_emu = self._size_emu()
        blob = EMFBlob(width_emu, height_emu)

        background = blob.get_solid_brush(colorref(self._color("tile", "background", "#F1F4FF", metadata)))
        blob.fill_rectangle(0, 0, width_emu, height_emu, background)

        pen = blob.get_pen(colorref(self._color("tile", "grid", "#2F3E6B", metadata)), max(1, width_emu // 320))
        brushes = [
            blob.get_solid_brush(colorref(self._color("tile", "tile_0", "#6585F6", metadata))),
            blob.get_solid_brush(colorref(self._color("tile", "tile_1", "#FDBB5A", metadata))),
            blob.get_solid_brush(colorref(self._color("tile", "tile_2", "#8BD6FF", metadata))),
        ]

        left_px, top_px = 10.0, 10.0
        tile_w, tile_h = 16.0, 16.0
        gap = 4.0

        for row in range(3):
            for col in range(4):
                brush = brushes[(row + col) % len(brushes)]
                rect = rect_points(left_px + col * (tile_w + gap), top_px + row * (tile_h + gap), tile_w, tile_h)
                blob.draw_polygon(rect, brush_handle=brush, pen_handle=pen)

        return self._finalise(blob, metadata | {"filter_type": "tile"})

    def _render_diffuse_lighting(self, metadata: dict[str, Any]) -> EMFResult:
        width_emu, height_emu = self._size_emu()
        blob = EMFBlob(width_emu, height_emu)

        base_hex = metadata.get("lighting_color")
        override = resolve_with_palette(self._palette_resolver, "diffuse_lighting", "base", metadata)
        if override:
            base_hex = override
        if not base_hex:
            base_hex = DEFAULT_FILTER_PALETTE["diffuse_lighting"].get("base", "#E4EBFF")
        base_color = blob.get_solid_brush(colorref(base_hex))
        blob.fill_rectangle(0, 0, width_emu, height_emu, base_color)

        relief_color = blob.get_solid_brush(colorref(adjust_lightness(base_hex, 0.35, brighten=False)))
        highlight_color = blob.get_solid_brush(colorref(adjust_lightness(base_hex, 0.45, brighten=True)))
        contour_pen = blob.get_pen(colorref(adjust_lightness(base_hex, 0.25, brighten=False)), max(1, width_emu // 160))

        ridge = rounded_rect(18, 20, 52, 26, radius=10)
        blob.draw_polygon(ridge, brush_handle=relief_color, pen_handle=contour_pen)

        highlight = rounded_rect(26, 24, 32, 16, radius=6)
        blob.draw_polygon(highlight, brush_handle=highlight_color, pen_handle=None)

        light_type = (metadata.get("light_type") or "distant").lower()
        light_pen = blob.get_pen(colorref(self._color("diffuse_lighting", "accent", "#FFFFFF", metadata)), max(1, width_emu // 220))
        if light_type == "distant":
            arrow = polyline([(24, 12), (48, 8), (60, 4)])
            blob.stroke_polyline(arrow, pen_handle=light_pen)
        elif light_type == "spot":
            beam = polyline([(48, 10), (40, 28), (32, 42)])
            blob.stroke_polyline(beam, pen_handle=light_pen)
        else:
            cross = polyline([(18, 12), (18, 32)])
            blob.stroke_polyline(cross, pen_handle=light_pen)

        return self._finalise(blob, metadata | {"filter_type": "diffuse_lighting"})

    def _render_specular_lighting(self, metadata: dict[str, Any]) -> EMFResult:
        width_emu, height_emu = self._size_emu()
        blob = EMFBlob(width_emu, height_emu)

        base_hex = metadata.get("lighting_color")
        override = resolve_with_palette(self._palette_resolver, "specular_lighting", "base", metadata)
        if override:
            base_hex = override
        if not base_hex:
            base_hex = DEFAULT_FILTER_PALETTE["specular_lighting"].get("base", "#1E2A3D")
        base_color = blob.get_solid_brush(colorref(adjust_lightness(base_hex, 0.55, brighten=False)))
        blob.fill_rectangle(0, 0, width_emu, height_emu, base_color)

        halo_hex = adjust_lightness(base_hex, 0.65, brighten=True)
        core_hex = "#FFFFFF"

        halo_points = ellipse_points(42, 28, 22, 18, segments=24)
        halo_brush = blob.get_solid_brush(colorref(halo_hex))
        blob.fill_polygon(halo_points, brush_handle=halo_brush)

        core_points = ellipse_points(42, 28, 10, 8, segments=16)
        core_brush = blob.get_solid_brush(colorref(core_hex))
        blob.fill_polygon(core_points, brush_handle=core_brush)

        sparkle_pen = blob.get_pen(colorref(self._color("specular_lighting", "accent", "#FFFFFF", metadata)), max(1, width_emu // 200))
        sparkle = polyline([(32, 12), (42, 28), (56, 34)])
        blob.stroke_polyline(sparkle, pen_handle=sparkle_pen)

        g_pen = blob.get_pen(colorref(adjust_lightness(base_hex, 0.4, brighten=True)), max(1, width_emu // 240))
        ridge = rounded_rect(18, 40, 48, 12, radius=4)
        blob.draw_polygon(ridge, brush_handle=None, pen_handle=g_pen)

        return self._finalise(blob, metadata | {"filter_type": "specular_lighting"})

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _finalise(self, blob: EMFBlob, metadata: dict[str, Any]) -> EMFResult:
        emf_bytes = blob.finalize()
        width_emu = blob.width_emu
        height_emu = blob.height_emu
        self._counter += 1
        result = EMFResult(
            emf_bytes=emf_bytes,
            relationship_id=f"rIdEmfFilter{self._counter}",
            width_emu=width_emu,
            height_emu=height_emu,
            metadata=dict(metadata),
        )
        return result

    def _size_emu(self) -> tuple[int, int]:
        width_px, height_px = self._DEFAULT_SIZE_PX
        return (max(1, int(round(px_to_emu(width_px)))), max(1, int(round(px_to_emu(height_px)))))

    def _cache_key(self, filter_type: str, metadata: dict[str, Any]) -> tuple[str, str]:
        relevant_keys = (
            "operator",
            "mode",
            "inputs",
            "filter_type",
            "placeholder",
            "scale",
            "x_channel",
            "y_channel",
            "base_frequency_x",
            "base_frequency_y",
            "num_octaves",
            "seed",
            "turbulence_type",
            "stitch_tiles",
            "values",
            "matrix_source",
            "matrix_type",
            "kernel",
            "kernel_unit_length",
            "kernel_source",
            "order",
            "input",
        )
        relevant = {key: metadata.get(key) for key in relevant_keys if key in metadata}
        normalised = repr(normalise_value(relevant))
        digest = hashlib.blake2s(normalised.encode(), digest_size=8).hexdigest()
        return filter_type, digest

    def _color(self, filter_type: str, role: str, default: str, metadata: Mapping[str, Any]) -> str:
        override = resolve_with_palette(self._palette_resolver, filter_type, role, metadata)
        if override:
            return override
        return DEFAULT_FILTER_PALETTE.get(filter_type, {}).get(role, default)


__all__ = ["EMFAdapter", "EMFResult", "PaletteResolver"]
