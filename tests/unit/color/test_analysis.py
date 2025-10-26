from svg2ooxml.color import Color, summarize_palette


def test_summarize_palette_from_strings() -> None:
    summary = summarize_palette(["#ff0000", "#00ff00", "#0000ff"])
    assert summary["unique"] == 3
    assert summary["palette"] == ["#FF0000", "#00FF00", "#0000FF".upper()]
    assert summary["complexity"] > 0


def test_summarize_palette_accepts_color_objects() -> None:
    summary = summarize_palette([Color(0.1, 0.2, 0.3), Color(0.1, 0.2, 0.3, 0.5)])
    assert summary["unique"] == 1
    assert summary["has_transparency"] is True
