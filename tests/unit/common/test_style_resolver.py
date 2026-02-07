from __future__ import annotations

from lxml import etree

from svg2ooxml.common.style.resolver import StyleContext, StyleResolver
from svg2ooxml.core.parser.units import UnitConverter
from svg2ooxml.core.styling.use_expander import _apply_computed_presentation


def _make_context(width: float = 200.0, height: float = 100.0) -> StyleContext:
    converter = UnitConverter()
    conversion = converter.create_context(
        width=width,
        height=height,
        font_size=12.0,
        parent_width=width,
        parent_height=height,
    )
    return StyleContext(conversion=conversion, viewport_width=width, viewport_height=height)


def test_stylesheet_cascade_prefers_important() -> None:
    resolver = StyleResolver()
    svg = etree.fromstring(
        """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>rect { fill: #00ff00 !important; }</style>
            <rect id='r' style='fill:#ff0000'/>
        </svg>
        """
    )
    resolver.collect_css(svg)
    rect = svg.find("{http://www.w3.org/2000/svg}rect")
    assert rect is not None

    paint = resolver.compute_paint_style(rect, context=_make_context())
    assert paint["fill"] == "#00FF00"


def test_uses_clone_inherits_computed_paint() -> None:
    resolver = StyleResolver()
    svg = etree.fromstring(
        """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>.source { stroke: #006400; }</style>
            <defs>
                <rect id='base' class='source' width='10' height='10'/>
            </defs>
            <use id='clone' xlink:href='#base' xmlns:xlink='http://www.w3.org/1999/xlink'/>
        </svg>
        """
    )
    resolver.collect_css(svg)
    rect = svg.xpath(".//svg:rect", namespaces={'svg': 'http://www.w3.org/2000/svg'})[0]
    use = svg.xpath(".//svg:use", namespaces={'svg': 'http://www.w3.org/2000/svg'})[0]

    clone = etree.fromstring(etree.tostring(rect))
    def _make_namespaced_tag(ref, local):
        tag = getattr(ref, 'tag', '')
        if isinstance(tag, str) and '}' in tag:
            namespace = tag.split('}', 1)[0][1:]
            return f'{{{namespace}}}{local}'
        return local

    dummy_converter = type('Dummy', (), {
        '_style_resolver': resolver,
        '_css_context': _make_context(),
        '_local_name': lambda self, tag: tag.split('}', 1)[-1],
        '_make_namespaced_tag': staticmethod(_make_namespaced_tag),
        '_normalize_href_reference': staticmethod(lambda href: href[1:] if href and href.startswith('#') else href),
        '_symbol_definitions': {},
    })()

    _apply_computed_presentation(dummy_converter, rect, clone)
    resolver.compute_paint_style(use)  # ensure clone flag handling
    paint = resolver.compute_paint_style(clone)
    assert paint["stroke"] == "#006400"


def test_parent_style_inheritance() -> None:
    resolver = StyleResolver()
    svg = etree.fromstring(
        """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <g fill='#123456'>
                <rect id='target' width='10' height='10'/>
            </g>
        </svg>
        """
    )
    rect = svg.find("{http://www.w3.org/2000/svg}g/{http://www.w3.org/2000/svg}rect")
    assert rect is not None

    paint = resolver.compute_paint_style(rect, parent_style={'fill': '#123456'})
    assert paint['fill'] == '#123456'


def test_text_stylesheet_application() -> None:
    resolver = StyleResolver()
    svg = etree.fromstring(
        """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>.headline { font-weight: 700; }</style>
            <text class='headline'>Hello</text>
        </svg>
        """
    )
    resolver.collect_css(svg)
    text_node = svg.find("{http://www.w3.org/2000/svg}text")
    assert text_node is not None

    style = resolver.compute_text_style(text_node)
    assert style['font_weight'] == 'bold'
