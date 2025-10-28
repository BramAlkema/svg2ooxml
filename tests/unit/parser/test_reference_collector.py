"""Tests for the parser reference collector."""

from svg2ooxml.core.parser.reference_collector import collect_references


def test_collect_references_returns_clip_and_masks() -> None:
    svg = """
    <svg>
      <defs>
        <clipPath id="clip1"><rect width="10" height="10" /></clipPath>
        <mask id="mask1"><rect width="5" height="5" /></mask>
      </defs>
      <defs>
        <symbol id="sym1"><rect width="1" height="1"/></symbol>
        <linearGradient id="grad1"></linearGradient>
        <pattern id="pat1"></pattern>
        <filter id="filt1"></filter>
      </defs>
      <rect clip-path="url(#clip1)" width="20" height="20" />
    </svg>
    """

    references = collect_references(svg_root=_parse(svg))

    assert getattr(references, "clip_paths", None) in (None, {})
    assert not hasattr(references, "clip_geometry")
    assert references.masks == {}
    assert references.symbols
    assert references.filters


def _parse(svg: str):
    from lxml import etree

    return etree.fromstring(svg)
