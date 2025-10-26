"""Tests for the EMF blob builder."""

from __future__ import annotations

import struct

import pytest

from svg2ooxml.io.emf import DashPattern, EMFBlob, EMFRecordType


def _records(data: bytes) -> list[tuple[int, bytes]]:
    records: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        record_type, size = struct.unpack_from("<II", data, offset)
        payload = data[offset + 8 : offset + size]
        records.append((record_type, payload))
        offset += size
    return records


def test_emf_blob_finalise_produces_header_and_eof() -> None:
    blob = EMFBlob(914400, 914400)
    brush = blob.create_solid_brush(0x00FF00)
    blob.fill_rectangle(0, 0, 914400, 914400, brush)
    emf_bytes = blob.finalize()

    assert emf_bytes
    records = _records(emf_bytes)
    assert records[0][0] == EMFRecordType.EMR_HEADER
    assert records[-1][0] == EMFRecordType.EMR_EOF


def test_emf_blob_accepts_null_brush() -> None:
    blob = EMFBlob(914400, 914400)
    blob.fill_rectangle(0, 0, 914400, 914400, None)
    emf_bytes = blob.finalize()
    assert emf_bytes


def test_emf_blob_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError):
        EMFBlob(0, 10)
    with pytest.raises(ValueError):
        EMFBlob(10, -1)


def test_emf_blob_pen_cache_reused() -> None:
    blob = EMFBlob(914400, 914400)
    pen1 = blob.get_pen(0x000000, 2)
    pen2 = blob.get_pen(0x000000, 2)
    assert pen1 == pen2


def test_emf_blob_clip_stack_records() -> None:
    blob = EMFBlob(914400, 914400)
    blob.push_clip_rect(0, 0, 100, 100)
    blob.pop_clip()
    emf_bytes = blob.finalize()
    records = _records(emf_bytes)
    codes = [rec[0] for rec in records]
    assert EMFRecordType.EMR_SAVEDC in codes
    assert EMFRecordType.EMR_INTERSECTCLIPRECT in codes
    assert EMFRecordType.EMR_RESTOREDC in codes


def test_emf_blob_stroke_polyline_with_dash() -> None:
    blob = EMFBlob(914400, 914400)
    dash = DashPattern((2.0, 1.0))
    pen = blob.get_pen(0x000000, 1)
    blob.stroke_polyline([(0, 0), (100, 0)], pen_handle=pen, dash_pattern=dash)
    emf_bytes = blob.finalize()
    records = _records(emf_bytes)
    polyline_records = [rec for rec in records if rec[0] == EMFRecordType.EMR_POLYLINE]
    assert len(polyline_records) >= 1


def test_emf_blob_draw_polygon_writes_point_count() -> None:
    blob = EMFBlob(914400, 914400)
    brush = blob.create_solid_brush(0x0000FF)
    pen = blob.create_pen(0x0000FF, 1000)
    blob.draw_polygon([(0, 0), (1000, 0), (1000, 1000)], brush_handle=brush, pen_handle=pen)
    emf_bytes = blob.finalize()

    polygon_record = next(entry for entry in _records(emf_bytes) if entry[0] == EMFRecordType.EMR_POLYGON)
    payload = polygon_record[1]
    count = struct.unpack_from("<I", payload, 16)[0]
    assert count == 3


def test_emf_blob_draw_polyline_requires_two_points() -> None:
    blob = EMFBlob(914400, 914400)
    pen = blob.create_pen(0x000000, 500)
    blob.draw_polyline([(0, 0), (1000, 1000)], pen_handle=pen)
    emf_bytes = blob.finalize()
    records = [record_type for record_type, _ in _records(emf_bytes)]
    assert EMFRecordType.EMR_POLYLINE in records


def test_emf_blob_fill_polypolygon_writes_record() -> None:
    blob = EMFBlob(914400, 914400)
    brush = blob.create_solid_brush(0x0000FF)
    blob.fill_polypolygon([
        [(0, 0), (100, 0), (100, 100)],
        [(200, 200), (300, 200), (300, 300)],
    ], brush_handle=brush)
    emf_bytes = blob.finalize()
    records = [record_type for record_type, _ in _records(emf_bytes)]
    assert EMFRecordType.EMR_POLYPOLYGON in records


def test_emf_blob_set_poly_fill_mode_emits_record_once() -> None:
    blob = EMFBlob(914400, 914400)
    blob.set_poly_fill_mode(2)
    blob.set_poly_fill_mode(2)  # second call should be a no-op
    emf_bytes = blob.finalize()
    codes = [record_type for record_type, _ in _records(emf_bytes)]
    assert codes.count(EMFRecordType.EMR_SETPOLYFILLMODE) == 1
