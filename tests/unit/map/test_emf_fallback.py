"""Unit tests for EMF geometry fallbacks."""

from __future__ import annotations

import struct

from lxml import etree

from svg2ooxml.io.emf import EMFRecordType
from svg2ooxml.ir.geometry import LineSegment, Point
from svg2ooxml.ir.paint import SolidPaint, Stroke, StrokeCap, StrokeJoin
from svg2ooxml.map.converter.coordinate_space import CoordinateSpace
from svg2ooxml.map.converter.fallbacks import render_emf_fallback
from svg2ooxml.map.converter.styles import StyleResult
from svg2ooxml.units.conversion import UnitConverter


def _records(data: bytes) -> list[tuple[int, bytes]]:
    records: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        record_type, size = struct.unpack_from("<II", data, offset)
        payload = data[offset + 8 : offset + size]
        records.append((record_type, payload))
        offset += size
    return records


def test_emf_fallback_polypolygon_evenodd_fill() -> None:
    element = etree.fromstring("<path fill-rule='evenodd' />")
    segments = [
        LineSegment(Point(0, 0), Point(10, 0)),
        LineSegment(Point(10, 0), Point(10, 10)),
        LineSegment(Point(10, 10), Point(0, 10)),
        LineSegment(Point(0, 10), Point(0, 0)),
        LineSegment(Point(3, 3), Point(7, 3)),
        LineSegment(Point(7, 3), Point(7, 7)),
        LineSegment(Point(7, 7), Point(3, 7)),
        LineSegment(Point(3, 7), Point(3, 3)),
    ]

    style = StyleResult(
        fill=SolidPaint("336699"),
        stroke=None,
        opacity=1.0,
        effects=[],
        metadata={},
    )
    image = render_emf_fallback(
        element=element,
        style=style,
        segments=segments,
        coord_space=CoordinateSpace(),
        clip_ref=None,
        mask_ref=None,
        mask_instance=None,
        metadata={},
        unit_converter=UnitConverter(),
        conversion_context=None,
    )

    assert image is not None
    assert image.format == "emf"
    assert image.origin.x == 0
    assert image.origin.y == 0
    assert image.size.width == 10
    assert image.size.height == 10

    emf_meta = image.metadata.get("emf_asset")
    assert isinstance(emf_meta, dict)
    assert emf_meta.get("fill_rule") == "evenodd"

    record_types = [EMFRecordType(code) for code, _ in _records(image.data)]
    assert EMFRecordType.EMR_POLYPOLYGON in record_types


def test_emf_fallback_stroke_captures_pen_style() -> None:
    element = etree.fromstring("<path />")
    segments = [
        LineSegment(Point(0, 0), Point(20, 0)),
        LineSegment(Point(20, 0), Point(20, 10)),
    ]

    stroke = Stroke(
        paint=SolidPaint("FF0000"),
        width=2.5,
        join=StrokeJoin.BEVEL,
        cap=StrokeCap.ROUND,
        dash_array=[4.0, 2.0],
        dash_offset=1.0,
    )
    style = StyleResult(
        fill=None,
        stroke=stroke,
        opacity=1.0,
        effects=[],
        metadata={},
    )

    metadata: dict[str, object] = {}
    image = render_emf_fallback(
        element=element,
        style=style,
        segments=segments,
        coord_space=CoordinateSpace(),
        clip_ref=None,
        mask_ref=None,
        mask_instance=None,
        metadata=metadata,
        unit_converter=UnitConverter(),
        conversion_context=None,
    )

    assert image is not None
    records = _records(image.data)
    pen_record = next(payload for code, payload in records if code == EMFRecordType.EMR_CREATEPEN)
    style_bits, width_emu = struct.unpack_from("<Ii", pen_record, 4)
    assert style_bits & 0x00001000  # PS_JOIN_BEVEL
    assert style_bits & 0x00000000 == 0  # PS_ENDCAP_ROUND contributes zero bits
    assert width_emu >= 1

    polyline_records = [payload for code, payload in records if code == EMFRecordType.EMR_POLYLINE]
    assert len(polyline_records) >= 1

    emf_meta = metadata.get("emf_asset")
    assert isinstance(emf_meta, dict)
    assert emf_meta.get("stroke_color") == "FF0000"
    assert emf_meta.get("stroke_cap") == StrokeCap.ROUND.value
    assert emf_meta.get("stroke_join") == StrokeJoin.BEVEL.value
