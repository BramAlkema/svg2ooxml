from __future__ import annotations

from svg2ooxml.drawingml.mask_writer import _fallback_sequence, _tuple_from_rect
from svg2ooxml.ir.geometry import Rect


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


def test_tuple_from_rect_accepts_rect_and_finite_tuple_values() -> None:
    assert _tuple_from_rect(Rect(1.0, 2.0, 3.0, 4.0)) == (1.0, 2.0, 3.0, 4.0)
    assert _tuple_from_rect(("1", "2", "3", "4")) == (1.0, 2.0, 3.0, 4.0)


def test_tuple_from_rect_rejects_invalid_and_nonfinite_tuple_values() -> None:
    assert _tuple_from_rect(("1", "2", "nan", "4")) is None
    assert _tuple_from_rect(("1", "2", "bad", "4")) is None
