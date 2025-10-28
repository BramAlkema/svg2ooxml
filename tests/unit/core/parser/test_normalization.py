from __future__ import annotations

from lxml import etree

from svg2ooxml.core.parser import (
    NormalizationSettings,
    SafeSVGNormalizer,
    compute_statistics,
    load_dom,
)


def test_load_dom_parses_svg() -> None:
    svg_text = "<svg xmlns='http://www.w3.org/2000/svg'><rect width='1' height='1'/></svg>"
    root = load_dom(svg_text)
    assert root.tag.endswith('svg')


def test_safe_normalizer_adds_missing_attributes_and_filters_comments() -> None:
    svg = etree.fromstring(
        """
        <svg>
            <!--comment-->
            <g id='group'>   <title> Example </title>   </g>
        </svg>
        """
    )
    normalizer = SafeSVGNormalizer(NormalizationSettings())
    normalized, changes = normalizer.normalize(svg)

    assert normalized.get('version') == '1.1'
    assert normalized.nsmap.get(None) == 'http://www.w3.org/2000/svg'
    # Ensure the comment was removed
    assert not any(isinstance(node, etree._Comment) for node in normalized.iter())
    assert changes['whitespace_normalized'] is True


def test_compute_statistics_counts_elements_and_namespaces() -> None:
    svg_text = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <g><rect width='1' height='1'/></g>
            <foreignObject xmlns:xhtml='http://www.w3.org/1999/xhtml'>
                <xhtml:div></xhtml:div>
            </foreignObject>
        </svg>
    """
    root = load_dom(svg_text)
    stats = compute_statistics(root)
    assert stats['element_count'] == 5  # svg, g, rect, foreignObject, div
    assert stats['namespace_count'] == 2
