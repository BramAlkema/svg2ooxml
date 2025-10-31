"""Tests for the DrawingML EMF path adapter bridge."""

from __future__ import annotations

import struct

from svg2ooxml.drawingml.bridges import EMFPathAdapter, PathStyle
from svg2ooxml.io.emf import EMFRecordType
from svg2ooxml.ir.geometry import LineSegment, Point
from svg2ooxml.ir.paint import SolidPaint, Stroke, StrokeCap, StrokeJoin
from svg2ooxml.common.units import ConversionContext, UnitConverter


def _records(data: bytes) -> list[tuple[int, bytes]]:
    records: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        record_type, size = struct.unpack_from("<II", data, offset)
        payload = data[offset + 8 : offset + size]
        records.append((record_type, payload))
        offset += size
    return records


def _rectangle_segments(width: float = 20.0, height: float = 10.0) -> list[LineSegment]:
    p0 = Point(0.0, 0.0)
    p1 = Point(width, 0.0)
    p2 = Point(width, height)
    p3 = Point(0.0, height)
    return [
        LineSegment(p0, p1),
        LineSegment(p1, p2),
        LineSegment(p2, p3),
        LineSegment(p3, p0),
    ]


def test_render_generates_filled_polygon() -> None:
    adapter = EMFPathAdapter()
    segments = _rectangle_segments()
    style = PathStyle(fill=SolidPaint("ff3366"), fill_rule="nonzero", stroke=None)
    unit_converter = UnitConverter()
    context = ConversionContext(width=100.0, height=100.0, dpi=unit_converter.dpi)

    result = adapter.render(
        segments=segments,
        style=style,
        unit_converter=unit_converter,
        conversion_context=context,
        dpi=int(context.dpi),
    )

    assert result is not None
    assert result.width_emu > 0 and result.height_emu > 0
    assert result.size == (20.0, 10.0)
    assert result.origin == (0.0, 0.0)
    records = _records(result.emf_bytes)
    assert records[0][0] == EMFRecordType.EMR_HEADER
    assert any(
        code in {EMFRecordType.EMR_POLYGON, EMFRecordType.EMR_POLYPOLYGON}
        for code, _ in records
    )
    assert records[-1][0] == EMFRecordType.EMR_EOF


def test_render_with_stroke_emits_polyline() -> None:
    adapter = EMFPathAdapter()
    segments = _rectangle_segments()
    stroke = Stroke(
        paint=SolidPaint("112233"),
        width=2.0,
        cap=StrokeCap.BUTT,
        join=StrokeJoin.MITER,
        opacity=1.0,
    )
    style = PathStyle(fill=None, fill_rule="evenodd", stroke=stroke)
    unit_converter = UnitConverter()

    result = adapter.render(
        segments=segments,
        style=style,
        unit_converter=unit_converter,
        conversion_context=ConversionContext(width=50.0, height=50.0, dpi=unit_converter.dpi),
        dpi=int(unit_converter.dpi),
    )

    assert result is not None
    records = _records(result.emf_bytes)
    assert any(code == EMFRecordType.EMR_POLYLINE for code, _ in records)


def test_render_returns_none_for_empty_segments() -> None:
    adapter = EMFPathAdapter()
    unit_converter = UnitConverter()
    result = adapter.render(
        segments=[],
        style=PathStyle(fill=None, fill_rule="nonzero", stroke=None),
        unit_converter=unit_converter,
        conversion_context=ConversionContext(width=10.0, height=10.0, dpi=unit_converter.dpi),
        dpi=int(unit_converter.dpi),
    )

    assert result is None
