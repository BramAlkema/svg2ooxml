"""Smoke tests for the resvg-backed normalizer stage."""

from __future__ import annotations

from svg2ooxml.core.resvg.normalizer import NormalizationResult, normalize_svg_string


def test_normalize_svg_string_round_trips_basic_tree() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
            <rect id="box" x="1" y="2" width="3" height="4" fill="#ff0000"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    assert isinstance(result, NormalizationResult)
    assert result.document.root.tag.endswith("svg")
    rect = next(
        (child for child in result.tree.root.children if child.tag.endswith("rect")),
        None,
    )
    assert rect is not None, "expected rectangle node to be present"
    assert rect.fill is not None and rect.fill.color is not None
    assert rect.attributes["width"] == "3"

