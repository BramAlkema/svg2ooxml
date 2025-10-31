from __future__ import annotations

from svg2ooxml.drawingml.mask_writer import _fallback_sequence


def test_fallback_sequence_respects_priority_order() -> None:
    mask_meta = {
        "fallback_order": ["raster", "native", "emf", "mimic"],
    }

    order = _fallback_sequence(mask_meta)
    assert order == ("native", "mimic", "emf", "raster")


def test_fallback_sequence_allows_policy_extensions() -> None:
    mask_meta = {
        "policy": {"fallback_order": ["policy_raster", "policy_emf", "native"]},
    }

    order = _fallback_sequence(mask_meta)

    assert order == ("native", "policy_raster", "policy_emf")
