"""Shape renderer guardrail tests."""

from __future__ import annotations

from svg2ooxml.drawingml.shape_renderer import _is_invalid_custom_effect_xml


def test_fill_overlay_effect_is_not_rejected_for_nested_solid_fill() -> None:
    xml = (
        "<a:effectLst>"
        '<a:fillOverlay blend="screen">'
        "<a:solidFill><a:srgbClr val=\"EFF9FF\"><a:alpha val=\"48800\"/></a:srgbClr></a:solidFill>"
        "</a:fillOverlay>"
        "<a:glow rad=\"26669\"><a:srgbClr val=\"EFF9FF\"><a:alpha val=\"16592\"/></a:srgbClr></a:glow>"
        "</a:effectLst>"
    )

    assert (
        _is_invalid_custom_effect_xml(
            xml,
            invalid_substrings=(
                "svg2ooxml:sourcegraphic",
                "svg2ooxml:sourcealpha",
                "svg2ooxml:emf",
                "svg2ooxml:raster",
            ),
        )
        is False
    )


def test_bare_solid_fill_fragment_is_rejected() -> None:
    xml = "<a:solidFill><a:srgbClr val=\"FF0000\"/></a:solidFill>"

    assert (
        _is_invalid_custom_effect_xml(
            xml,
            invalid_substrings=(
                "svg2ooxml:sourcegraphic",
                "svg2ooxml:sourcealpha",
                "svg2ooxml:emf",
                "svg2ooxml:raster",
            ),
        )
        is True
    )
