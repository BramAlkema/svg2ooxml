"""Tests for the CSS style resolver."""

import pytest
from lxml import etree

from svg2ooxml.core.parser.units import UnitConverter
from svg2ooxml.core.styling.use_expander import _apply_computed_presentation
from svg2ooxml.css import StyleContext, StyleResolver


def _make_context(width: float = 200.0, height: float = 100.0) -> tuple[UnitConverter, StyleContext]:
    converter = UnitConverter()
    conversion = converter.create_context(
        width=width,
        height=height,
        font_size=12.0,
        parent_width=width,
        parent_height=height,
    )
    return converter, StyleContext(conversion=conversion, viewport_width=width, viewport_height=height)


def test_style_resolver_applies_attributes() -> None:
    resolver = StyleResolver()
    element = etree.fromstring(
        "<text font-family='Calibri' font-size='16pt' font-weight='700'>Hello</text>"
    )

    style = resolver.compute_text_style(element)

    assert style["font_family"] == "Calibri"
    assert style["font_size_pt"] == pytest.approx(16.0)
    assert style["font_weight"] == "bold"


def test_style_resolver_applies_text_anchor_attribute() -> None:
    resolver = StyleResolver()
    element = etree.fromstring("<text text-anchor='middle'>Hello</text>")

    style = resolver.compute_text_style(element)

    assert style["text_anchor"] == "middle"


def test_style_resolver_inherits_text_anchor_from_parent() -> None:
    resolver = StyleResolver()
    group = etree.fromstring("<g text-anchor='end'><text>Hello</text></g>")
    text_node = group.find("text")
    assert text_node is not None

    parent_style = resolver.compute_text_style(group)
    child_style = resolver.compute_text_style(text_node, parent_style=parent_style)

    assert child_style["text_anchor"] == "end"


def test_style_resolver_parses_inline_styles() -> None:
    resolver = StyleResolver()
    element = etree.fromstring(
        "<text style='font-style: italic; fill: #ff0000'>Hello</text>"
    )

    style = resolver.compute_text_style(element)

    assert style["font_style"] == "italic"
    assert style["fill"] == "#FF0000"


def test_style_resolver_supports_percentage_font_size() -> None:
    resolver = StyleResolver()
    parent = resolver.default_text_style()
    parent["font_size_pt"] = 10.0
    element = etree.fromstring("<text style='font-size: 150%'>Hello</text>")

    style = resolver.compute_text_style(element, parent_style=parent)

    assert style["font_size_pt"] == pytest.approx(15.0)


def test_style_resolver_supports_calc_font_size() -> None:
    resolver = StyleResolver()
    parent = resolver.default_text_style()
    parent["font_size_pt"] = 10.0
    element = etree.fromstring("<text style='font-size: calc(150% + 2pt)'>Hello</text>")

    style = resolver.compute_text_style(element, parent_style=parent)

    assert style["font_size_pt"] == pytest.approx(17.0)


def test_style_resolver_invalid_inherited_font_size_uses_default_base() -> None:
    resolver = StyleResolver()
    parent = resolver.default_text_style()
    parent["font_size_pt"] = "bad"
    element = etree.fromstring("<text style='font-size: 150%'>Hello</text>")

    style = resolver.compute_text_style(element, parent_style=parent)

    assert style["font_size_pt"] == pytest.approx(18.0)


def test_style_resolver_scales_unitless_font_size() -> None:
    resolver = StyleResolver(unitless_font_size_scale=0.875)
    element = etree.fromstring("<text style='font-size: 32'>Hello</text>")

    style = resolver.compute_text_style(element)

    assert style["font_size_pt"] == pytest.approx(28.0)


def test_style_resolver_resolves_current_color() -> None:
    resolver = StyleResolver()
    parent = resolver.default_text_style()
    parent["color"] = "#112233"
    parent["fill"] = "#FF0000"
    element = etree.fromstring("<text style='fill: currentColor'>Hello</text>")

    style = resolver.compute_text_style(element, parent_style=parent)

    assert style["fill"] == "#112233"


def test_paint_style_handles_url_and_percentage_width() -> None:
    resolver = StyleResolver()
    _, context = _make_context(width=200.0, height=100.0)
    element = etree.fromstring(
        "<rect fill='url(#grad)' stroke='none' stroke-width='50%' opacity='0.5'/>"
    )

    paint = resolver.compute_paint_style(element, context=context)

    assert paint["fill"] == "url(#grad)"
    assert paint["stroke"] is None
    assert paint["stroke_width_px"] == pytest.approx(100.0)
    assert paint["opacity"] == pytest.approx(0.5)


def test_paint_style_resolves_current_color_from_color_not_fill() -> None:
    resolver = StyleResolver()
    group = etree.fromstring("<g color='#112233' fill='#ff0000'><rect fill='currentColor'/></g>")
    rect = group.find("rect")
    assert rect is not None

    parent_style = resolver.compute_paint_style(group)
    paint = resolver.compute_paint_style(rect, parent_style=parent_style)

    assert paint["fill"] == "#112233"


def test_paint_style_resolves_percentage_opacity_values() -> None:
    resolver = StyleResolver()
    element = etree.fromstring(
        "<rect opacity='50%' fill-opacity='25%' stroke-opacity='75%'/>"
    )

    paint = resolver.compute_paint_style(element)

    assert paint["opacity"] == pytest.approx(0.5)
    assert paint["fill_opacity"] == pytest.approx(0.25)
    assert paint["stroke_opacity"] == pytest.approx(0.75)


def test_paint_style_resolves_context_dependent_length_units() -> None:
    resolver = StyleResolver()
    _, context = _make_context(width=200.0, height=100.0)
    element = etree.fromstring("<rect stroke-width='10vw'/>")

    paint = resolver.compute_paint_style(element, context=context)

    assert paint["stroke_width_px"] == pytest.approx(20.0)


def test_media_queries_resolve_length_units() -> None:
    resolver = StyleResolver()
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                @media (min-width: 2cm) { rect { fill: #008000; } }
                @media (max-width: 1cm) { rect { stroke: #ff0000; } }
            </style>
            <rect width='10' height='10'/>
        </svg>
    """
    root = etree.fromstring(svg_markup)
    resolver.collect_css(root, viewport_width=100.0, viewport_height=100.0)
    rect = root.find("{http://www.w3.org/2000/svg}rect")
    assert rect is not None

    paint = resolver.compute_paint_style(rect, context=_make_context(width=100.0)[1])

    assert paint["fill"] == "#008000"
    assert paint["stroke"] is None


def test_media_queries_resolve_calc_length_units() -> None:
    resolver = StyleResolver()
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                @media (min-width: calc(2cm + 5px)) { rect { fill: #008000; } }
                @media (max-width: calc(1cm + 5px)) { rect { stroke: #ff0000; } }
            </style>
            <rect width='10' height='10'/>
        </svg>
    """
    root = etree.fromstring(svg_markup)
    resolver.collect_css(root, viewport_width=100.0, viewport_height=100.0)
    rect = root.find("{http://www.w3.org/2000/svg}rect")
    assert rect is not None

    paint = resolver.compute_paint_style(rect, context=_make_context(width=100.0)[1])

    assert paint["fill"] == "#008000"
    assert paint["stroke"] is None


def test_stylesheet_rules_apply_to_use_clones() -> None:
    resolver = StyleResolver()
    converter, context = _make_context()
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                .parent > rect { fill: #008000; stroke: #006400; stroke-width: 5; }
            </style>
            <g class='parent'>
                <rect id='original' width='100' height='100'/>
            </g>
        </svg>
    """
    root = etree.fromstring(svg_markup)

    resolver.collect_css(root)
    rect = root.find("{http://www.w3.org/2000/svg}g/{http://www.w3.org/2000/svg}rect")
    assert rect is not None

    paint = resolver.compute_paint_style(rect, context=context)
    assert paint["fill"] == "#008000"
    assert paint["stroke"] == "#006400"

    clone = etree.fromstring(etree.tostring(rect))

    dummy_converter = type("Dummy", (), {"_style_resolver": resolver, "_css_context": context})()
    _apply_computed_presentation(dummy_converter, rect, clone)

    clone_paint = resolver.compute_paint_style(clone, context=context)
    assert clone_paint["fill"] == "#008000"
    assert clone_paint["stroke"] == "#006400"


def test_stylesheet_rules_apply_to_text_elements() -> None:
    resolver = StyleResolver()
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                .title { fill: #008000; font-weight: 700; }
            </style>
            <text class='title'>Hello</text>
        </svg>
    """
    root = etree.fromstring(svg_markup)
    resolver.collect_css(root)

    text_node = root.find("{http://www.w3.org/2000/svg}text")
    assert text_node is not None

    style = resolver.compute_text_style(text_node)

    assert style["fill"] == "#008000"
    assert style["font_weight"] == "bold"


def test_stylesheet_important_beats_more_specific_normal_rule() -> None:
    resolver = StyleResolver()
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                rect { fill: #008000 !important; }
                #target { fill: #ff0000; }
            </style>
            <rect id='target'/>
        </svg>
    """
    root = etree.fromstring(svg_markup)
    resolver.collect_css(root)
    rect = root.find("{http://www.w3.org/2000/svg}rect")
    assert rect is not None

    paint = resolver.compute_paint_style(rect)

    assert paint["fill"] == "#008000"


def test_stylesheet_color_feeds_current_color_fill() -> None:
    resolver = StyleResolver()
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                .target { color: #112233; fill: currentColor; }
            </style>
            <rect class='target' fill='#ff0000'/>
        </svg>
    """
    root = etree.fromstring(svg_markup)
    resolver.collect_css(root)
    rect = root.find("{http://www.w3.org/2000/svg}rect")
    assert rect is not None

    paint = resolver.compute_paint_style(rect)

    assert paint["fill"] == "#112233"


def test_collect_css_resets_custom_properties_between_roots() -> None:
    resolver = StyleResolver()
    first = etree.fromstring(
        """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                :root { --accent: #008000; }
                rect { fill: var(--accent); }
            </style>
            <rect/>
        </svg>
        """
    )
    resolver.collect_css(first)
    first_rect = first.find("{http://www.w3.org/2000/svg}rect")
    assert first_rect is not None
    assert resolver.compute_paint_style(first_rect)["fill"] == "#008000"

    second = etree.fromstring(
        """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                rect { fill: var(--accent, #112233); }
            </style>
            <rect/>
        </svg>
        """
    )
    resolver.collect_css(second)
    second_rect = second.find("{http://www.w3.org/2000/svg}rect")
    assert second_rect is not None

    paint = resolver.compute_paint_style(second_rect)

    assert paint["fill"] == "#112233"


def test_text_stylesheet_important_beats_more_specific_normal_rule() -> None:
    resolver = StyleResolver()
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                text { fill: #008000 !important; }
                #target { fill: #ff0000; }
            </style>
            <text id='target'>Hello</text>
        </svg>
    """
    root = etree.fromstring(svg_markup)
    resolver.collect_css(root)
    text_node = root.find("{http://www.w3.org/2000/svg}text")
    assert text_node is not None

    style = resolver.compute_text_style(text_node)

    assert style["fill"] == "#008000"


def test_inline_style_respects_stylesheet_important() -> None:
    resolver = StyleResolver()
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                text { fill: #008000 !important; }
            </style>
            <text style='fill: #ff0000'>Hello</text>
        </svg>
    """
    root = etree.fromstring(svg_markup)
    resolver.collect_css(root)

    text_node = root.find("{http://www.w3.org/2000/svg}text")
    assert text_node is not None

    style = resolver.compute_text_style(text_node)

    assert style["fill"] == "#008000"


def test_inline_important_overrides_stylesheet_important() -> None:
    resolver = StyleResolver()
    svg_markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <style>
                text { fill: #008000 !important; }
            </style>
            <text style='fill: #ff0000 !important'>Hello</text>
        </svg>
    """
    root = etree.fromstring(svg_markup)
    resolver.collect_css(root)

    text_node = root.find("{http://www.w3.org/2000/svg}text")
    assert text_node is not None

    style = resolver.compute_text_style(text_node)

    assert style["fill"] == "#FF0000"
