"""Enhanced Metafile (EMF) blob builder used for vector fallbacks."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .path import DashPattern, apply_dash_pattern


class EMFRecordType(IntEnum):
    """EMF record identifiers used when serialising records."""

    EMR_HEADER = 1
    EMR_POLYBEZIER = 2
    EMR_POLYGON = 3
    EMR_POLYLINE = 4
    EMR_POLYBEZIERTO = 5
    EMR_POLYLINETO = 6
    EMR_POLYPOLYGON = 8
    EMR_POLYPOLYLINE = 7
    EMR_SETPOLYFILLMODE = 19
    EMR_SETWORLDTRANSFORM = 35
    EMR_SAVEDC = 33
    EMR_RESTOREDC = 34
    EMR_INTERSECTCLIPRECT = 30
    EMR_BEGINPATH = 59
    EMR_ENDPATH = 60
    EMR_CLOSEFIGURE = 61
    EMR_FILLPATH = 62
    EMR_STROKEPATH = 64
    EMR_SELECTOBJECT = 37
    EMR_CREATEPEN = 38
    EMR_CREATEBRUSHINDIRECT = 39
    EMR_DELETEOBJECT = 40
    EMR_RECTANGLE = 43
    EMR_FILLRGN = 71
    EMR_CREATEDIBPATTERNBRUSHPT = 94
    EMR_STRETCHDIBITS = 65
    EMR_EOF = 14


class EMFBrushStyle(IntEnum):
    """Brush styles supported by the builder."""

    BS_SOLID = 0
    BS_NULL = 1
    BS_HATCHED = 2
    BS_PATTERN = 3
    BS_INDEXED = 4
    BS_DIBPATTERN = 5
    BS_DIBPATTERNPT = 6
    BS_PATTERN8X8 = 7
    BS_DIBPATTERN8X8 = 8
    BS_MONOPATTERN = 9


class EMFHatchStyle(IntEnum):
    """Hatch styles understood by PowerPoint."""

    HS_HORIZONTAL = 0
    HS_VERTICAL = 1
    HS_FDIAGONAL = 2
    HS_BDIAGONAL = 3
    HS_CROSS = 4
    HS_DIAGCROSS = 5


@dataclass(frozen=True)
class BrushSpec:
    color: int


@dataclass(frozen=True)
class PenSpec:
    color: int
    width_px: int
    line_cap: int = 0
    line_join: int = 0
    pen_style: int = 0


NULL_BRUSH_HANDLE = 0x80000005
NULL_PEN_HANDLE = 0x80000008
EMU_PER_INCH = 914400
HMM_PER_EMU = 2540 / EMU_PER_INCH  # hundredth of millimetres per EMU


class EMFBlob:
    """In-memory EMF builder that emits valid header + record streams."""

    def __init__(self, width_emu: int, height_emu: int, *, dpi: int = 96) -> None:
        if width_emu <= 0 or height_emu <= 0:
            raise ValueError("width_emu and height_emu must be positive integers")
        self.width_emu = int(width_emu)
        self.height_emu = int(height_emu)
        self.dpi = dpi
        self._scale = self.dpi / EMU_PER_INCH
        self.width_px = max(1, int(round(self.width_emu * self._scale)))
        self.height_px = max(1, int(round(self.height_emu * self._scale)))
        self._records: list[bytes] = []
        self._handles: list[int] = []
        self._next_handle = 1
        self._brush_cache: Dict[BrushSpec, int] = {}
        self._pen_cache: Dict[PenSpec, int] = {}
        self._dib_brush_cache: Dict[tuple[int, bytes], int] = {}
        self._clip_depth = 0
        self._poly_fill_mode = 1  # 1 = ALTERNATE, 2 = WINDING
        self._init_header()

    @staticmethod
    def _align4(value: int) -> int:
        return (value + 3) & ~3

    @staticmethod
    def _pad4(data: bytes) -> bytes:
        padding = (-len(data)) % 4
        if padding:
            data += b"\x00" * padding
        return data

    def _to_px(self, value: int | float) -> int:
        return int(round(value * self._scale))

    def _to_px_point(self, point: Tuple[int | float, int | float]) -> Tuple[int, int]:
        return (self._to_px(point[0]), self._to_px(point[1]))

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def create_solid_brush(self, rgb: int) -> int:
        """Create a solid brush; returns the EMF handle."""

        return self._create_brush(style=EMFBrushStyle.BS_SOLID, color=rgb, hatch=0)

    def create_hatch_brush(self, pattern: str, rgb: int) -> int:
        """Create a hatched brush using one of the supported hatch patterns."""

        hatch = {
            "horizontal": EMFHatchStyle.HS_HORIZONTAL,
            "vertical": EMFHatchStyle.HS_VERTICAL,
            "diagonal": EMFHatchStyle.HS_FDIAGONAL,
            "backward_diagonal": EMFHatchStyle.HS_BDIAGONAL,
            "cross": EMFHatchStyle.HS_CROSS,
            "diagcross": EMFHatchStyle.HS_DIAGCROSS,
        }.get(pattern, EMFHatchStyle.HS_HORIZONTAL)
        return self._create_brush(style=EMFBrushStyle.BS_HATCHED, color=rgb, hatch=int(hatch))

    def create_null_brush(self) -> None:
        """Select the stock NULL brush."""

        self._append_record(EMFRecordType.EMR_SELECTOBJECT, struct.pack("<I", NULL_BRUSH_HANDLE))

    def create_pen(
        self,
        rgb: int,
        width_px: int = 1,
        *,
        line_cap: int = 0,
        line_join: int = 0,
        pen_style: int = 0,
    ) -> int:
        """Create a cosmetic pen."""

        handle = self._allocate_handle()
        width_px = max(1, int(width_px))
        style = (pen_style & 0x0000000F) | (line_cap & 0x00000F00) | (line_join & 0x0000F000)
        payload = struct.pack("<I", handle) + struct.pack("<IiiI", style, width_px, 0, rgb)
        self._append_record(EMFRecordType.EMR_CREATEPEN, payload)
        return handle

    def get_solid_brush(self, rgb: int) -> int:
        """Return a cached solid brush handle."""

        spec = BrushSpec(rgb)
        handle = self._brush_cache.get(spec)
        if handle is None:
            handle = self.create_solid_brush(rgb)
            self._brush_cache[spec] = handle
        return handle

    def create_dib_pattern_brush(self, bmp_bytes: bytes, *, usage: int = 0) -> int:
        """Create a DIB pattern brush from a BMP payload."""

        if not bmp_bytes.startswith(b"BM"):
            raise ValueError("bmp_bytes must be a little-endian BMP payload")

        data_index = struct.unpack_from("<I", bmp_bytes, 10)[0]
        header_size = struct.unpack_from("<I", bmp_bytes, 14)[0]
        bmi = bmp_bytes[14 : 14 + header_size]
        bits = bmp_bytes[data_index:]

        bmi_padded = self._pad4(bmi)
        bits_padded = self._pad4(bits)

        handle = self._allocate_handle()
        off_bmi = 8 + 6 * 4  # header + payload fields
        off_bits = off_bmi + len(bmi_padded)
        payload = struct.pack(
            "<IIIIII",
            handle,
            usage,
            off_bmi,
            len(bmi),
            off_bits,
            len(bits),
        )
        payload += bmi_padded + bits_padded
        self._append_record(EMFRecordType.EMR_CREATEDIBPATTERNBRUSHPT, payload)
        return handle

    def get_dib_pattern_brush(self, bmp_bytes: bytes, *, usage: int = 0) -> int:
        """Return a cached DIB pattern brush, creating it if necessary."""

        digest = hashlib.sha1(bmp_bytes).digest()
        key = (usage, digest)
        handle = self._dib_brush_cache.get(key)
        if handle is None:
            handle = self.create_dib_pattern_brush(bmp_bytes, usage=usage)
            self._dib_brush_cache[key] = handle
        return handle

    def draw_bitmap(
        self,
        dest_left: int,
        dest_top: int,
        dest_width: int,
        dest_height: int,
        src_left: int,
        src_top: int,
        src_width: int,
        src_height: int,
        bmp_bytes: bytes,
        *,
        rop: int = 0x00CC0020,
    ) -> None:
        """Render a bitmap using EMR_STRETCHDIBITS."""

        if not bmp_bytes.startswith(b"BM"):
            raise ValueError("bmp_bytes must be a little-endian BMP payload")

        data_index = struct.unpack_from("<I", bmp_bytes, 10)[0]
        header_size = struct.unpack_from("<I", bmp_bytes, 14)[0]
        bmi = bmp_bytes[14 : 14 + header_size]
        bits = bmp_bytes[data_index:]

        bmi_padded = self._pad4(bmi)
        bits_padded = self._pad4(bits)

        off_bmi = 8 + 18 * 4
        off_bits = off_bmi + len(bmi_padded)

        dest_left_px = self._to_px(dest_left)
        dest_top_px = self._to_px(dest_top)
        dest_width_px = max(1, self._to_px(dest_width))
        dest_height_px = max(1, self._to_px(dest_height))

        payload = struct.pack(
            "<" + "i" * 18,
            int(dest_left_px),
            int(dest_top_px),
            int(dest_left_px + dest_width_px),
            int(dest_top_px + dest_height_px),
            int(dest_left_px),
            int(dest_top_px),
            int(src_left),
            int(src_top),
            int(src_width),
            int(src_height),
            int(off_bmi),
            int(len(bmi)),
            int(off_bits),
            int(len(bits)),
            0,
            int(rop),
            int(dest_width_px),
            int(dest_height_px),
        )
        payload += bmi_padded + bits_padded
        self._append_record(EMFRecordType.EMR_STRETCHDIBITS, payload)

    def get_pen(
        self,
        rgb: int,
        width_px: int = 1,
        *,
        line_cap: int = 0,
        line_join: int = 0,
        pen_style: int = 0,
    ) -> int:
        """Return a cached pen handle."""

        scaled_width = max(1, self._to_px(width_px))
        spec = PenSpec(rgb, scaled_width, line_cap, line_join, pen_style)
        handle = self._pen_cache.get(spec)
        if handle is None:
            handle = self.create_pen(
                rgb,
                spec.width_px,
                line_cap=spec.line_cap,
                line_join=spec.line_join,
                pen_style=spec.pen_style,
            )
            self._pen_cache[spec] = handle
        return handle

    def stroke_polyline(
        self,
        points: Sequence[Tuple[int, int]],
        *,
        pen_handle: Optional[int] = None,
        pen_color: Optional[int] = None,
        pen_width_px: int = 1,
        dash_pattern: DashPattern | None = None,
        line_cap: int = 0,
        line_join: int = 0,
        pen_style: int = 0,
    ) -> None:
        """Stroke a polyline, optionally applying a dash pattern."""

        if len(points) < 2:
            return
        if pen_handle is None:
            if pen_color is None:
                raise ValueError("pen_color is required when pen_handle is not supplied")
            pen_handle = self.get_pen(
                pen_color,
                pen_width_px,
                line_cap=line_cap,
                line_join=line_join,
                pen_style=pen_style,
            )

        segments = [list(points)]
        if dash_pattern is not None and not dash_pattern.is_solid():
            float_points = [(float(x), float(y)) for x, y in points]
            segments = [
                [(px, py) for px, py in segment]
                for segment in apply_dash_pattern(float_points, dash_pattern)
            ]
            segments = [segment for segment in segments if len(segment) >= 2]

        if not segments:
            return

        self._select_brush(None)
        self._select_pen(pen_handle)
        for segment in segments:
            payload = _polyline_payload(self._ensure_int_points(segment))
            self._append_record(EMFRecordType.EMR_POLYLINE, payload)

    def fill_polygon(
        self,
        points: Sequence[Tuple[int, int]],
        *,
        brush_handle: Optional[int] = None,
        brush_color: Optional[int] = None,
    ) -> None:
        """Fill a polygon using the supplied brush."""

        if len(points) < 3:
            return
        if brush_handle is None:
            if brush_color is None:
                raise ValueError("brush_color is required when brush_handle is not supplied")
            brush_handle = self.get_solid_brush(brush_color)

        self._select_brush(brush_handle)
        self._select_pen(None)
        payload = _polygon_payload(self._ensure_int_points(points))
        self._append_record(EMFRecordType.EMR_POLYGON, payload)

    def push_clip_rect(self, left: int, top: int, right: int, bottom: int) -> None:
        """Intersect the current clip region with the supplied rectangle."""

        self._append_record(EMFRecordType.EMR_SAVEDC, b"")
        rect_payload = struct.pack(
            "<4l",
            self._to_px(left),
            self._to_px(top),
            self._to_px(right),
            self._to_px(bottom),
        )
        self._append_record(EMFRecordType.EMR_INTERSECTCLIPRECT, rect_payload)
        self._clip_depth += 1

    def pop_clip(self) -> None:
        """Restore the previous clip region."""

        if self._clip_depth <= 0:
            return
        self._append_record(EMFRecordType.EMR_RESTOREDC, struct.pack("<i", -1))
        self._clip_depth -= 1

    def select_object(self, handle: int | None) -> None:
        """Select an EMF object into the device context."""

        if handle is None:
            return
        self._append_record(EMFRecordType.EMR_SELECTOBJECT, struct.pack("<I", handle))

    def delete_object(self, handle: int | None) -> None:
        """Delete a previously created EMF object."""

        if handle is None:
            return
        self._append_record(EMFRecordType.EMR_DELETEOBJECT, struct.pack("<I", handle))

    def draw_polygon(
        self,
        points: Sequence[Tuple[int, int]],
        *,
        brush_handle: int | None,
        pen_handle: int | None,
    ) -> None:
        """Draw a filled polygon using the supplied brush/pen handles."""

        coord_list = self._ensure_int_points(points)
        if len(coord_list) < 3:
            return
        self._select_brush(brush_handle)
        self._select_pen(pen_handle)
        payload = _polygon_payload(coord_list)
        self._append_record(EMFRecordType.EMR_POLYGON, payload)

    def draw_polyline(
        self,
        points: Sequence[Tuple[int, int]],
        *,
        pen_handle: int | None,
    ) -> None:
        """Draw a stroked polyline using the supplied pen handle."""

        coord_list = self._ensure_int_points(points)
        if len(coord_list) < 2:
            return
        self._select_pen(pen_handle)
        payload = _polyline_payload(coord_list)
        self._append_record(EMFRecordType.EMR_POLYLINE, payload)

    def fill_rectangle(self, left: int, top: int, width: int, height: int, brush_handle: int | None) -> None:
        """Fill rectangle bounds using the currently selected brush."""

        if brush_handle is None:
            self.create_null_brush()
        else:
            self.select_object(brush_handle)
        left_px = self._to_px(left)
        top_px = self._to_px(top)
        width_px = max(1, self._to_px(width))
        height_px = max(1, self._to_px(height))
        rect = struct.pack("<4l", left_px, top_px, left_px + width_px, top_px + height_px)
        self._append_record(EMFRecordType.EMR_RECTANGLE, rect)

    def finalize(self) -> bytes:
        """Serialise header + records into a single EMF byte stream."""

        self._append_record(EMFRecordType.EMR_EOF, struct.pack("<III", 0, 0, 0))
        total_size = sum(len(record) for record in self._records)
        record_count = len(self._records)

        header = bytearray(self._records[0])
        struct.pack_into("<I", header, 48, total_size)
        struct.pack_into("<I", header, 52, record_count)
        struct.pack_into("<H", header, 56, len(self._handles))
        self._records[0] = bytes(header)

        eof_payload = struct.pack("<III", 0, 0, total_size)
        self._records[-1] = (
            struct.pack("<II", int(EMFRecordType.EMR_EOF), 8 + len(eof_payload)) + eof_payload
        )

        return b"".join(self._records)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_brush(self, *, style: EMFBrushStyle, color: int, hatch: int) -> int:
        handle = self._allocate_handle()
        payload = struct.pack("<I", handle) + struct.pack("<III", int(style), color, hatch)
        self._append_record(EMFRecordType.EMR_CREATEBRUSHINDIRECT, payload)
        return handle

    def _allocate_handle(self) -> int:
        handle = self._next_handle
        self._handles.append(handle)
        self._next_handle += 1
        return handle

    def _append_record(self, record_type: EMFRecordType, payload: bytes) -> None:
        size = 8 + len(payload)
        self._records.append(struct.pack("<II", int(record_type), size) + payload)

    def _select_pen(self, handle: int | None) -> None:
        if handle is None:
            self._append_record(EMFRecordType.EMR_SELECTOBJECT, struct.pack("<I", NULL_PEN_HANDLE))
        else:
            self.select_object(handle)

    def _select_brush(self, handle: int | None) -> None:
        if handle is None:
            self._append_record(EMFRecordType.EMR_SELECTOBJECT, struct.pack("<I", NULL_BRUSH_HANDLE))
        else:
            self.select_object(handle)

    def set_poly_fill_mode(self, mode: int) -> None:
        """Set polygon fill mode (1 = alternate, 2 = winding)."""

        if mode == self._poly_fill_mode:
            return
        if mode not in (1, 2):
            raise ValueError("poly fill mode must be 1 (alternate) or 2 (winding)")
        self._append_record(EMFRecordType.EMR_SETPOLYFILLMODE, struct.pack("<I", mode))
        self._poly_fill_mode = mode

    def fill_polypolygon(
        self,
        polygons: Sequence[Sequence[Tuple[int, int]]],
        *,
        brush_handle: Optional[int] = None,
        brush_color: Optional[int] = None,
        pen_handle: Optional[int] = None,
        pen_color: Optional[int] = None,
    ) -> None:
        """Fill multiple polygons in one record."""

        normalised: list[list[Tuple[int, int]]] = []
        for polygon in polygons:
            points = self._ensure_int_points(polygon)
            if len(points) >= 3:
                # Avoid duplicate closing point; EMF closes polygons automatically.
                if points[0] == points[-1]:
                    points = points[:-1]
                if len(points) >= 3:
                    normalised.append(points)

        if not normalised:
            return

        if brush_handle is None and brush_color is not None:
            brush_handle = self.get_solid_brush(brush_color)

        if pen_handle is None and pen_color is not None:
            pen_handle = self.get_pen(pen_color, 1)

        self._select_brush(brush_handle)
        self._select_pen(pen_handle)

        all_points = [point for polygon in normalised for point in polygon]
        min_x, min_y, max_x, max_y = _bounds(all_points)
        polygon_count = len(normalised)
        total_points = sum(len(polygon) for polygon in normalised)
        counts_blob = b"".join(struct.pack("<I", len(polygon)) for polygon in normalised)
        points_blob = b"".join(struct.pack("<ii", x, y) for polygon in normalised for x, y in polygon)
        header = struct.pack("<4l", min_x, min_y, max_x, max_y)
        payload = header + struct.pack("<II", polygon_count, total_points) + counts_blob + points_blob
        self._append_record(EMFRecordType.EMR_POLYPOLYGON, payload)

    def _ensure_int_points(self, points: Iterable[Tuple[int | float, int | float]]) -> List[Tuple[int, int]]:
        return [self._to_px_point((x, y)) for x, y in points]

    def _init_header(self) -> None:
        width_hmm = int(round(self.width_emu * HMM_PER_EMU))
        height_hmm = int(round(self.height_emu * HMM_PER_EMU))
        width_mm = max(1, int(round(width_hmm / 100)))
        height_mm = max(1, int(round(height_hmm / 100)))
        width_device = self.width_px
        height_device = self.height_px

        header_size = 108
        payload = bytearray(header_size)
        struct.pack_into("<I", payload, 0, int(EMFRecordType.EMR_HEADER))
        struct.pack_into("<I", payload, 4, header_size)
        struct.pack_into("<4l", payload, 8, 0, 0, width_device, height_device)
        struct.pack_into("<4l", payload, 24, 0, 0, width_hmm, height_hmm)
        struct.pack_into("<I", payload, 40, 0x464D4520)  # " EMF"
        struct.pack_into("<I", payload, 44, 0x00010000)
        struct.pack_into("<I", payload, 48, 0)  # nBytes placeholder
        struct.pack_into("<I", payload, 52, 0)  # nRecords placeholder
        struct.pack_into("<H", payload, 56, 0)  # nHandles placeholder
        struct.pack_into("<H", payload, 58, 0)  # reserved
        struct.pack_into("<I", payload, 60, 0)  # nDescription
        struct.pack_into("<I", payload, 64, 0)  # offDescription
        struct.pack_into("<I", payload, 68, 0)  # nPalEntries
        struct.pack_into("<II", payload, 72, width_device, height_device)
        struct.pack_into("<II", payload, 80, width_mm, height_mm)
        struct.pack_into("<I", payload, 88, 0)  # cbPixelFormat
        struct.pack_into("<I", payload, 92, 0)  # offPixelFormat
        struct.pack_into("<I", payload, 96, 0)  # bOpenGL
        struct.pack_into("<II", payload, 100, max(1, width_hmm * 10), max(1, height_hmm * 10))
        self._records.append(bytes(payload))


PointList = Sequence[Tuple[int, int]] | Iterable[Tuple[int, int]]


def _normalise_points(points: PointList) -> list[Tuple[int, int]]:
    result: list[Tuple[int, int]] = []
    for x, y in points:
        result.append((int(round(x)), int(round(y))))
    return result


def _polygon_payload(points: Sequence[Tuple[int, int]]) -> bytes:
    min_x, min_y, max_x, max_y = _bounds(points)
    bounds = struct.pack("<4l", min_x, min_y, max_x, max_y)
    count = len(points)
    data = b"".join(struct.pack("<ii", x, y) for x, y in points)
    return bounds + struct.pack("<I", count) + data


def _polyline_payload(points: Sequence[Tuple[int, int]]) -> bytes:
    min_x, min_y, max_x, max_y = _bounds(points)
    bounds = struct.pack("<4l", min_x, min_y, max_x, max_y)
    count = len(points)
    data = b"".join(struct.pack("<ii", x, y) for x, y in points)
    return bounds + struct.pack("<I", count) + data


def _bounds(points: Sequence[Tuple[int, int]]) -> Tuple[int, int, int, int]:
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


__all__ = [
    "EMFBlob",
    "EMFRecordType",
    "EMFBrushStyle",
    "EMFHatchStyle",
    "NULL_BRUSH_HANDLE",
    "NULL_PEN_HANDLE",
]
