from __future__ import annotations

from svg2ooxml.drawingml.filter_renderer_assets import FilterRendererAssetMixin


def test_filter_renderer_asset_coerce_int_rejects_nonfinite_values() -> None:
    assert FilterRendererAssetMixin._coerce_int("12.9") == 12
    assert FilterRendererAssetMixin._coerce_int("nan") is None
    assert FilterRendererAssetMixin._coerce_int("bad") is None
