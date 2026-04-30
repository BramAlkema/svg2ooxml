"""Enhanced Metafile (EMF) blob builder used for vector fallbacks."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Iterable, Sequence
from enum import IntEnum

from .path import DashPattern, apply_dash_pattern

EMFRecordType = IntEnum(
    "EMFRecordType",
    dict(
        EMR_HEADER=1,
        EMR_POLYBEZIER=2,
        EMR_POLYGON=3,
        EMR_POLYLINE=4,
        EMR_POLYBEZIERTO=5,
        EMR_POLYLINETO=6,
        EMR_POLYPOLYLINE=7,
        EMR_POLYPOLYGON=8,
        EMR_EOF=14,
        EMR_SETPOLYFILLMODE=19,
        EMR_INTERSECTCLIPRECT=30,
        EMR_SAVEDC=33,
        EMR_RESTOREDC=34,
        EMR_SETWORLDTRANSFORM=35,
        EMR_SELECTOBJECT=37,
        EMR_CREATEPEN=38,
        EMR_CREATEBRUSHINDIRECT=39,
        EMR_DELETEOBJECT=40,
        EMR_RECTANGLE=43,
        EMR_BEGINPATH=59,
        EMR_ENDPATH=60,
        EMR_CLOSEFIGURE=61,
        EMR_FILLPATH=62,
        EMR_STROKEPATH=64,
        EMR_STRETCHDIBITS=65,
        EMR_FILLRGN=71,
        EMR_CREATEDIBPATTERNBRUSHPT=94,
    ),
)
EMFBrushStyle = IntEnum(
    "EMFBrushStyle",
    dict(
        BS_SOLID=0,
        BS_NULL=1,
        BS_HATCHED=2,
        BS_PATTERN=3,
        BS_INDEXED=4,
        BS_DIBPATTERN=5,
        BS_DIBPATTERNPT=6,
        BS_PATTERN8X8=7,
        BS_DIBPATTERN8X8=8,
        BS_MONOPATTERN=9,
    ),
)
EMFHatchStyle = IntEnum(
    "EMFHatchStyle",
    dict(
        HS_HORIZONTAL=0,
        HS_VERTICAL=1,
        HS_FDIAGONAL=2,
        HS_BDIAGONAL=3,
        HS_CROSS=4,
        HS_DIAGCROSS=5,
    ),
)


NULL_BRUSH_HANDLE = 0x80000005
NULL_PEN_HANDLE = 0x80000008
EMU_PER_INCH = 914400
HMM_PER_EMU = 2540 / EMU_PER_INCH  # hundredth of millimetres per EMU
I32_MIN = -(2**31)
I32_MAX = 2**31 - 1
U16_MAX = 2**16 - 1
U32_MAX = 2**32 - 1
MAX_EMF_BYTES = 256 * 1024 * 1024
MAX_DPI = 9600

_REC = struct.Struct("<II")
_U32 = struct.Struct("<I")
_I32 = struct.Struct("<i")
_PT = struct.Struct("<ii")
_RECT = struct.Struct("<4l")
_HATCH = {
    "horizontal": EMFHatchStyle.HS_HORIZONTAL,
    "vertical": EMFHatchStyle.HS_VERTICAL,
    "diagonal": EMFHatchStyle.HS_FDIAGONAL,
    "backward_diagonal": EMFHatchStyle.HS_BDIAGONAL,
    "cross": EMFHatchStyle.HS_CROSS,
    "diagcross": EMFHatchStyle.HS_DIAGCROSS,
}


class EMFBlob:
    """In-memory EMF builder that emits valid header + record streams."""

    def __init__(self, width_emu: int, height_emu: int, *, dpi: int = 96) -> None:
        self.width_emu = _positive_int(width_emu, "width_emu")
        self.height_emu = _positive_int(height_emu, "height_emu")
        self.dpi = _positive_int(dpi, "dpi")
        if self.dpi > MAX_DPI:
            raise ValueError(f"dpi must be <= {MAX_DPI}")
        self._scale = self.dpi / EMU_PER_INCH
        self.width_px = max(1, _i32(round(self.width_emu * self._scale), "width_px"))
        self.height_px = max(1, _i32(round(self.height_emu * self._scale), "height_px"))
        self._records: list[bytes] = []
        self._handles: list[int] = []
        self._next_handle = 1
        self._brush_cache: dict[int, int] = {}
        self._pen_cache: dict[tuple[int, int, int, int, int], int] = {}
        self._dib_brush_cache: dict[tuple[int, bytes], int] = {}
        self._clip_depth = 0
        self._poly_fill_mode = 1  # 1 = ALTERNATE, 2 = WINDING
        self._finalized: bytes | None = None
        self._init_header()

    @staticmethod
    def _pad4(data: bytes) -> bytes:
        padding = (-len(data)) % 4
        if padding:
            data += b"\x00" * padding
        return data

    def _to_px(self, value: int | float) -> int:
        return _i32(
            round(_finite_number(value, "coordinate") * self._scale), "coordinate"
        )

    def _to_px_point(self, point: tuple[int | float, int | float]) -> tuple[int, int]:
        return (self._to_px(point[0]), self._to_px(point[1]))

    def create_solid_brush(self, rgb: int) -> int:
        return self._create_brush(
            style=EMFBrushStyle.BS_SOLID, color=_u32(rgb, "rgb"), hatch=0
        )

    def create_hatch_brush(self, pattern: str, rgb: int) -> int:
        hatch = _HATCH.get(pattern, EMFHatchStyle.HS_HORIZONTAL)
        return self._create_brush(
            style=EMFBrushStyle.BS_HATCHED, color=_u32(rgb, "rgb"), hatch=int(hatch)
        )

    def create_null_brush(self) -> None:
        self._append_record(
            EMFRecordType.EMR_SELECTOBJECT, _U32.pack(NULL_BRUSH_HANDLE)
        )

    def create_pen(
        self,
        rgb: int,
        width_px: int = 1,
        *,
        line_cap: int = 0,
        line_join: int = 0,
        pen_style: int = 0,
    ) -> int:
        handle = self._allocate_handle()
        width_px = max(1, int(width_px))
        style = (
            (pen_style & 0x0000000F)
            | (line_cap & 0x00000F00)
            | (line_join & 0x0000F000)
        )
        payload = _U32.pack(handle) + struct.pack(
            "<IiiI", style, _i32(width_px, "width_px"), 0, _u32(rgb, "rgb")
        )
        self._append_record(EMFRecordType.EMR_CREATEPEN, payload)
        return handle

    def get_solid_brush(self, rgb: int) -> int:
        rgb = _u32(rgb, "rgb")
        handle = self._brush_cache.get(rgb)
        if handle is None:
            handle = self.create_solid_brush(rgb)
            self._brush_cache[rgb] = handle
        return handle

    def create_dib_pattern_brush(self, bmp_bytes: bytes, *, usage: int = 0) -> int:
        bmi, bits = _split_bmp_payload(bmp_bytes)
        bmi_padded = self._pad4(bmi)
        bits_padded = self._pad4(bits)
        handle = self._allocate_handle()
        off_bmi = 8 + 6 * 4  # header + payload fields
        off_bits = off_bmi + len(bmi_padded)
        payload = struct.pack(
            "<IIIIII",
            handle,
            _u32(usage, "usage"),
            off_bmi,
            len(bmi),
            off_bits,
            len(bits),
        )
        payload += bmi_padded + bits_padded
        self._append_record(EMFRecordType.EMR_CREATEDIBPATTERNBRUSHPT, payload)
        return handle

    def get_dib_pattern_brush(self, bmp_bytes: bytes, *, usage: int = 0) -> int:
        usage = _u32(usage, "usage")
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
        bmi, bits = _split_bmp_payload(bmp_bytes)
        bmi_padded = self._pad4(bmi)
        bits_padded = self._pad4(bits)
        off_bmi = 8 + 18 * 4
        off_bits = off_bmi + len(bmi_padded)
        dest_left_px = self._to_px(dest_left)
        dest_top_px = self._to_px(dest_top)
        dest_width_px = max(1, self._to_px(dest_width))
        dest_height_px = max(1, self._to_px(dest_height))

        payload = struct.pack(
            "<" + "i" * 15 + "Iii",
            int(dest_left_px),
            int(dest_top_px),
            _i32(dest_left_px + dest_width_px, "right"),
            _i32(dest_top_px + dest_height_px, "bottom"),
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
            _u32(rop, "rop"),
            int(dest_width_px),
            int(dest_height_px),
        )
        payload += bmi_padded + bits_padded
        self._append_record(EMFRecordType.EMR_STRETCHDIBITS, payload)

    def get_pen(
        self,
        rgb: int,
        width_emu: int = 1,
        *,
        line_cap: int = 0,
        line_join: int = 0,
        pen_style: int = 0,
    ) -> int:
        scaled_width = max(1, self._to_px(width_emu))
        spec = (_u32(rgb, "rgb"), scaled_width, line_cap, line_join, pen_style)
        handle = self._pen_cache.get(spec)
        if handle is None:
            handle = self.create_pen(
                spec[0],
                spec[1],
                line_cap=spec[2],
                line_join=spec[3],
                pen_style=spec[4],
            )
            self._pen_cache[spec] = handle
        return handle

    def stroke_polyline(
        self,
        points: Sequence[tuple[int, int]],
        *,
        pen_handle: int | None = None,
        pen_color: int | None = None,
        pen_width_emu: int = 1,
        pen_width_px: int | None = None,
        dash_pattern: DashPattern | None = None,
        line_cap: int = 0,
        line_join: int = 0,
        pen_style: int = 0,
    ) -> None:
        if len(points) < 2:
            return
        if pen_handle is None:
            if pen_color is None:
                raise ValueError(
                    "pen_color is required when pen_handle is not supplied"
                )
            if pen_width_px is not None:
                pen_width_emu = pen_width_px
            pen_handle = self.get_pen(
                pen_color,
                pen_width_emu,
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
            payload = _poly_payload(self._ensure_int_points(segment))
            self._append_record(EMFRecordType.EMR_POLYLINE, payload)

    def fill_polygon(
        self,
        points: Sequence[tuple[int, int]],
        *,
        brush_handle: int | None = None,
        brush_color: int | None = None,
    ) -> None:
        if len(points) < 3:
            return
        if brush_handle is None:
            if brush_color is None:
                raise ValueError(
                    "brush_color is required when brush_handle is not supplied"
                )
            brush_handle = self.get_solid_brush(brush_color)

        self._select_brush(brush_handle)
        self._select_pen(None)
        payload = _poly_payload(self._ensure_int_points(points))
        self._append_record(EMFRecordType.EMR_POLYGON, payload)

    def push_clip_rect(self, left: int, top: int, right: int, bottom: int) -> None:
        self._append_record(EMFRecordType.EMR_SAVEDC, b"")
        rect_payload = _RECT.pack(
            self._to_px(left),
            self._to_px(top),
            self._to_px(right),
            self._to_px(bottom),
        )
        self._append_record(EMFRecordType.EMR_INTERSECTCLIPRECT, rect_payload)
        self._clip_depth += 1

    def pop_clip(self) -> None:
        if self._clip_depth <= 0:
            return
        self._append_record(EMFRecordType.EMR_RESTOREDC, _I32.pack(-1))
        self._clip_depth -= 1

    def select_object(self, handle: int | None) -> None:
        if handle is None:
            return
        self._append_record(
            EMFRecordType.EMR_SELECTOBJECT, _U32.pack(_u32(handle, "handle"))
        )

    def delete_object(self, handle: int | None) -> None:
        if handle is None:
            return
        self._append_record(
            EMFRecordType.EMR_DELETEOBJECT, _U32.pack(_u32(handle, "handle"))
        )

    def draw_polygon(
        self,
        points: Sequence[tuple[int, int]],
        *,
        brush_handle: int | None,
        pen_handle: int | None,
    ) -> None:
        coord_list = self._ensure_int_points(points)
        if len(coord_list) < 3:
            return
        self._select_brush(brush_handle)
        self._select_pen(pen_handle)
        payload = _poly_payload(coord_list)
        self._append_record(EMFRecordType.EMR_POLYGON, payload)

    def draw_polyline(
        self,
        points: Sequence[tuple[int, int]],
        *,
        pen_handle: int | None,
    ) -> None:
        coord_list = self._ensure_int_points(points)
        if len(coord_list) < 2:
            return
        self._select_pen(pen_handle)
        payload = _poly_payload(coord_list)
        self._append_record(EMFRecordType.EMR_POLYLINE, payload)

    def fill_rectangle(
        self, left: int, top: int, width: int, height: int, brush_handle: int | None
    ) -> None:
        if brush_handle is None:
            self.create_null_brush()
        else:
            self.select_object(brush_handle)
        left_px = self._to_px(left)
        top_px = self._to_px(top)
        width_px = max(1, self._to_px(width))
        height_px = max(1, self._to_px(height))
        rect = _RECT.pack(
            left_px,
            top_px,
            _i32(left_px + width_px, "right"),
            _i32(top_px + height_px, "bottom"),
        )
        self._append_record(EMFRecordType.EMR_RECTANGLE, rect)

    def finalize(self) -> bytes:
        if self._finalized is not None:
            return self._finalized

        while self._clip_depth > 0:
            self.pop_clip()

        self._append_record(EMFRecordType.EMR_EOF, struct.pack("<III", 0, 0, 0))
        total_size = sum(len(record) for record in self._records)
        record_count = len(self._records)
        _u32(total_size, "EMF byte size")
        _u32(record_count, "EMF record count")

        header = bytearray(self._records[0])
        struct.pack_into("<I", header, 48, total_size)
        struct.pack_into("<I", header, 52, record_count)
        struct.pack_into("<H", header, 56, len(self._handles))
        self._records[0] = bytes(header)

        eof_payload = struct.pack("<III", 0, 0, total_size)
        self._records[-1] = (
            _REC.pack(int(EMFRecordType.EMR_EOF), 8 + len(eof_payload)) + eof_payload
        )

        self._finalized = b"".join(self._records)
        return self._finalized

    def _create_brush(self, *, style: EMFBrushStyle, color: int, hatch: int) -> int:
        handle = self._allocate_handle()
        payload = _U32.pack(handle) + struct.pack(
            "<III", int(style), _u32(color, "color"), _u32(hatch, "hatch")
        )
        self._append_record(EMFRecordType.EMR_CREATEBRUSHINDIRECT, payload)
        return handle

    def _allocate_handle(self) -> int:
        if self._next_handle > U16_MAX:
            raise ValueError("EMF handle table exhausted")
        handle = self._next_handle
        self._handles.append(handle)
        self._next_handle += 1
        return handle

    def _append_record(self, record_type: EMFRecordType, payload: bytes) -> None:
        if self._finalized is not None:
            raise RuntimeError("cannot append EMF records after finalize()")
        payload = self._pad4(payload)
        size = 8 + len(payload)
        if size > MAX_EMF_BYTES:
            raise ValueError("EMF record exceeds configured safety limit")
        self._records.append(
            _REC.pack(int(record_type), _u32(size, "record size")) + payload
        )

    def _select_pen(self, handle: int | None) -> None:
        if handle is None:
            self._append_record(
                EMFRecordType.EMR_SELECTOBJECT, _U32.pack(NULL_PEN_HANDLE)
            )
        else:
            self.select_object(handle)

    def _select_brush(self, handle: int | None) -> None:
        if handle is None:
            self._append_record(
                EMFRecordType.EMR_SELECTOBJECT, _U32.pack(NULL_BRUSH_HANDLE)
            )
        else:
            self.select_object(handle)

    def set_poly_fill_mode(self, mode: int) -> None:
        if mode == self._poly_fill_mode:
            return
        if mode not in (1, 2):
            raise ValueError("poly fill mode must be 1 (alternate) or 2 (winding)")
        self._append_record(EMFRecordType.EMR_SETPOLYFILLMODE, struct.pack("<I", mode))
        self._poly_fill_mode = mode

    def fill_polypolygon(
        self,
        polygons: Sequence[Sequence[tuple[int, int]]],
        *,
        brush_handle: int | None = None,
        brush_color: int | None = None,
        pen_handle: int | None = None,
        pen_color: int | None = None,
    ) -> None:
        normalised: list[list[tuple[int, int]]] = []
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

        polygon_count = len(normalised)
        total_points = sum(len(polygon) for polygon in normalised)
        min_x, min_y, max_x, max_y = _multi_bounds(normalised)
        counts_blob = b"".join(_U32.pack(len(polygon)) for polygon in normalised)
        points_blob = _pack_points(point for polygon in normalised for point in polygon)
        payload = (
            _RECT.pack(min_x, min_y, max_x, max_y)
            + struct.pack("<II", polygon_count, total_points)
            + counts_blob
            + points_blob
        )
        self._append_record(EMFRecordType.EMR_POLYPOLYGON, payload)

    def _ensure_int_points(
        self, points: Iterable[tuple[int | float, int | float]]
    ) -> list[tuple[int, int]]:
        return [self._to_px_point((x, y)) for x, y in points]

    def _init_header(self) -> None:
        width_hmm = _i32(round(self.width_emu * HMM_PER_EMU), "width_hmm")
        height_hmm = _i32(round(self.height_emu * HMM_PER_EMU), "height_hmm")
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
        struct.pack_into(
            "<II",
            payload,
            100,
            _u32(max(1, width_hmm * 10), "micrometer width"),
            _u32(max(1, height_hmm * 10), "micrometer height"),
        )
        self._records.append(bytes(payload))


def _poly_payload(points: Sequence[tuple[int, int]]) -> bytes:
    min_x, min_y, max_x, max_y = _bounds(points)
    return (
        _RECT.pack(min_x, min_y, max_x, max_y)
        + _U32.pack(len(points))
        + _pack_points(points)
    )


def _pack_points(points: Iterable[tuple[int, int]]) -> bytes:
    data = bytearray()
    pack = _PT.pack
    for x, y in points:
        data += pack(_i32(x, "x"), _i32(y, "y"))
    return bytes(data)


def _bounds(points: Sequence[tuple[int, int]]) -> tuple[int, int, int, int]:
    min_x = max_x = _i32(points[0][0], "x")
    min_y = max_y = _i32(points[0][1], "y")
    for x, y in points[1:]:
        x = _i32(x, "x")
        y = _i32(y, "y")
        if x < min_x:
            min_x = x
        elif x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        elif y > max_y:
            max_y = y
    return min_x, min_y, max_x, max_y


def _multi_bounds(
    polygons: Sequence[Sequence[tuple[int, int]]],
) -> tuple[int, int, int, int]:
    min_x, min_y, max_x, max_y = _bounds(polygons[0])
    for polygon in polygons[1:]:
        p_min_x, p_min_y, p_max_x, p_max_y = _bounds(polygon)
        min_x = min(min_x, p_min_x)
        min_y = min(min_y, p_min_y)
        max_x = max(max_x, p_max_x)
        max_y = max(max_y, p_max_y)
    return min_x, min_y, max_x, max_y


def _split_bmp_payload(bmp_bytes: bytes) -> tuple[bytes, bytes]:
    if not isinstance(bmp_bytes, (bytes, bytearray)) or not bmp_bytes.startswith(b"BM"):
        raise ValueError("bmp_bytes must be a little-endian BMP payload")
    if len(bmp_bytes) < 18:
        raise ValueError("BMP payload is truncated")
    data_index = struct.unpack_from("<I", bmp_bytes, 10)[0]
    header_size = struct.unpack_from("<I", bmp_bytes, 14)[0]
    bmi_end = 14 + header_size
    if header_size < 12 or bmi_end > len(bmp_bytes):
        raise ValueError("BMP info header is invalid or truncated")
    if data_index < bmi_end or data_index > len(bmp_bytes):
        raise ValueError("BMP pixel data offset is invalid")
    bits = bytes(bmp_bytes[data_index:])
    if not bits:
        raise ValueError("BMP payload has no pixel data")
    return bytes(bmp_bytes[14:bmi_end]), bits


def _finite_number(value: int | float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_int(value: int | float, name: str) -> int:
    result = int(round(_finite_number(value, name)))
    if result <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return result


def _i32(value: int | float, name: str) -> int:
    result = int(round(_finite_number(value, name)))
    if result < I32_MIN or result > I32_MAX:
        raise ValueError(f"{name} is outside signed 32-bit range")
    return result


def _u32(value: int | float, name: str) -> int:
    result = int(round(_finite_number(value, name)))
    if result < 0 or result > U32_MAX:
        raise ValueError(f"{name} is outside unsigned 32-bit range")
    return result


__all__ = [
    "EMFBlob",
    "EMFRecordType",
    "EMFBrushStyle",
    "EMFHatchStyle",
    "NULL_BRUSH_HANDLE",
    "NULL_PEN_HANDLE",
]
