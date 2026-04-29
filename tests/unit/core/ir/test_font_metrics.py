from __future__ import annotations

import pytest

from svg2ooxml.core.ir.text.font_metrics import create_run_from_style


def test_create_run_from_style_parses_opacity_tokens_and_bad_font_size() -> None:
    seen_font_sizes: list[float] = []

    def resolve_text_length(value, *, axis: str, font_size_pt: float) -> float:
        assert axis == "x"
        assert value == "2"
        seen_font_sizes.append(font_size_pt)
        return 2.0

    run = create_run_from_style(
        "Hello",
        {
            "fill": "#123456",
            "fill_opacity": "calc(25% + 25%)",
            "font_size_pt": "bad",
            "stroke": "#654321",
            "stroke_opacity": "50%",
            "stroke_width": "2",
        },
        resolve_text_length_fn=resolve_text_length,
    )

    assert run.font_size_pt == 12.0
    assert seen_font_sizes == [12.0]
    assert run.fill_opacity == pytest.approx(0.5)
    assert run.stroke_opacity == pytest.approx(0.5)
    assert run.stroke_width_px == pytest.approx(2.0)
