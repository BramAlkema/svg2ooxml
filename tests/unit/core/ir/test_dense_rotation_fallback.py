from __future__ import annotations

from lxml import etree

from svg2ooxml.core.ir.text.dense_rotation_fallback import source_text_svg_payload
from svg2ooxml.core.ir.text.positioning_metadata import has_rotate_tree


def test_source_text_svg_payload_preserves_root_inherited_styles() -> None:
    root = etree.fromstring(
        """
        <svg xmlns="http://www.w3.org/2000/svg"
             width="120" height="80" viewBox="0 0 120 80"
             font-family="Arial" fill="red" style="font-weight:bold">
          <text x="10" y="20" rotate="0 20">AB</text>
        </svg>
        """
    )
    text = root.find("{http://www.w3.org/2000/svg}text")
    assert text is not None

    payload = source_text_svg_payload(text, viewport_size=(120.0, 80.0))

    assert payload is not None
    svg = etree.fromstring(payload[0])
    assert svg.get("font-family") == "Arial"
    assert svg.get("fill") == "red"
    assert svg.get("style") == "font-weight:bold"
    assert svg.get("width") == "120"
    assert svg.get("height") == "80"
    assert svg.get("viewBox") == "0 0 120 80"


def test_has_rotate_tree_ignores_zero_angles() -> None:
    root = etree.fromstring(
        """
        <svg xmlns="http://www.w3.org/2000/svg">
          <text rotate="0 0 0">AB</text>
        </svg>
        """
    )

    assert not has_rotate_tree(root)
