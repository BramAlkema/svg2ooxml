"""Tests for the filter EMF adapter."""

from __future__ import annotations

import struct

from svg2ooxml.drawingml.emf_adapter import EMFAdapter
from svg2ooxml.io.emf import EMFRecordType


def _records(data: bytes) -> list[tuple[int, bytes]]:
    records: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        record_type, size = struct.unpack_from("<II", data, offset)
        payload = data[offset + 8 : offset + size]
        records.append((record_type, payload))
        offset += size
    return records


def test_render_composite_generates_repeatable_emf() -> None:
    adapter = EMFAdapter()
    result = adapter.render_filter("composite", {"operator": "over"})

    assert result.relationship_id.startswith("rIdEmfFilter")
    assert result.width_emu > 0 and result.height_emu > 0
    records = _records(result.emf_bytes)
    assert records[0][0] == EMFRecordType.EMR_HEADER
    assert EMFRecordType.EMR_POLYGON in {code for code, _ in records}
    assert records[-1][0] == EMFRecordType.EMR_EOF


def test_render_filter_is_cached_by_metadata() -> None:
    adapter = EMFAdapter()
    first = adapter.render_filter("blend", {"mode": "multiply", "inputs": ["a", "b"]})
    second = adapter.render_filter("blend", {"mode": "multiply", "inputs": ["a", "b"]})

    assert first.relationship_id == second.relationship_id
    assert first.emf_bytes == second.emf_bytes
    assert first.metadata == second.metadata


def test_unknown_filter_produces_placeholder_asset() -> None:
    adapter = EMFAdapter()
    result = adapter.render_filter("mystery", {})

    assert result.metadata.get("filter_type") == "generic"
    records = _records(result.emf_bytes)
    assert records[-1][0] == EMFRecordType.EMR_EOF


def test_component_transfer_renders_channel_columns() -> None:
    adapter = EMFAdapter()
    metadata = {
        "functions": [
            {"channel": "r", "type": "linear", "params": {"slope": 1.2, "intercept": 0.1}},
            {"channel": "g", "type": "gamma", "params": {"amplitude": 0.9, "exponent": 2.0}},
            {"channel": "b", "type": "table", "params": {"values": [0.0, 0.3, 0.7, 1.0]}},
        ]
    }
    result = adapter.render_filter("component_transfer", metadata)

    assert result.metadata.get("filter_type") == "component_transfer"
    records = _records(result.emf_bytes)
    assert any(code == EMFRecordType.EMR_POLYGON for code, _ in records)
    assert any(code == EMFRecordType.EMR_POLYLINE for code, _ in records)


def test_diffuse_lighting_renders_relief_panel() -> None:
    adapter = EMFAdapter()
    metadata = {"lighting_color": "#9BB8FF", "light_type": "distant"}
    result = adapter.render_filter("diffuse_lighting", metadata)

    assert result.metadata.get("filter_type") == "diffuse_lighting"
    records = _records(result.emf_bytes)
    assert any(code == EMFRecordType.EMR_POLYGON for code, _ in records)
    assert any(code == EMFRecordType.EMR_POLYLINE for code, _ in records)


def test_specular_lighting_renders_highlighted_halo() -> None:
    adapter = EMFAdapter()
    metadata = {"lighting_color": "#304060", "light_type": "spot"}
    result = adapter.render_filter("specular_lighting", metadata)

    assert result.metadata.get("filter_type") == "specular_lighting"
    records = _records(result.emf_bytes)
    assert any(code == EMFRecordType.EMR_POLYGON for code, _ in records)
    assert any(code == EMFRecordType.EMR_POLYLINE for code, _ in records)


def test_displacement_map_renders_warp_grid() -> None:
    adapter = EMFAdapter()
    metadata = {"scale": 18.0, "x_channel": "R", "y_channel": "G"}
    result = adapter.render_filter("displacement_map", metadata)

    assert result.metadata.get("filter_type") == "displacement_map"
    records = _records(result.emf_bytes)
    assert any(code == EMFRecordType.EMR_POLYLINE for code, _ in records)


def test_turbulence_renders_noise_layers() -> None:
    adapter = EMFAdapter()
    metadata = {
        "base_frequency_x": 0.05,
        "base_frequency_y": 0.1,
        "num_octaves": 3,
        "seed": 4.2,
        "stitch_tiles": True,
    }
    result = adapter.render_filter("turbulence", metadata)

    assert result.metadata.get("filter_type") == "turbulence"
    records = _records(result.emf_bytes)
    assert any(code == EMFRecordType.EMR_POLYLINE for code, _ in records)


def test_palette_resolver_overrides_colors() -> None:
    override_hex = "#123456"

    def resolver(filter_type, role, metadata):
        if filter_type == "displacement_map" and role == "background":
            return override_hex
        return None

    adapter = EMFAdapter(palette_resolver=resolver)
    result = adapter.render_filter("displacement_map", {"scale": 10})

    records = _records(result.emf_bytes)
    create_brush = next(payload for code, payload in records if code == EMFRecordType.EMR_CREATEBRUSHINDIRECT)
    color_value = struct.unpack_from("<III", create_brush, 4)[1]
    expected_bgr = int(override_hex[5:7], 16) << 16 | int(override_hex[3:5], 16) << 8 | int(override_hex[1:3], 16)
    assert color_value == expected_bgr
