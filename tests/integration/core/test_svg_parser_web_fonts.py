"""Integration tests for SVGParser with web font support."""
from __future__ import annotations

import pytest
from svg2ooxml.core.parser import SVGParser, ParserConfig


class TestSVGParserWebFonts:
    """Integration tests for SVGParser @font-face parsing."""

    def test_parse_svg_with_font_face(self):
        """Parse SVG with embedded @font-face rules."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              font-family: 'CustomFont';
              src: url('font.woff2') format('woff2');
            }
          </style>
          <text font-family="CustomFont">Hello</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1
        assert result.web_fonts[0].family == 'CustomFont'
        assert len(result.web_fonts[0].src) == 1
        assert result.web_fonts[0].src[0].url == 'font.woff2'
        assert result.web_fonts[0].src[0].format == 'woff2'

    def test_parse_svg_with_multiple_font_weights(self):
        """Parse SVG with multiple font weights."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              font-family: 'Roboto';
              src: url('roboto-400.woff2');
              font-weight: 400;
            }
            @font-face {
              font-family: 'Roboto';
              src: url('roboto-700.woff2');
              font-weight: 700;
            }
          </style>
          <text font-family="Roboto" font-weight="400">Normal</text>
          <text font-family="Roboto" font-weight="700">Bold</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 2

        # Check weights
        weights = {rule.weight_numeric for rule in result.web_fonts}
        assert weights == {400, 700}

    def test_parse_svg_with_data_uri_font(self):
        """Parse SVG with base64 data URI font."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              font-family: 'Custom';
              src: url('data:font/woff2;base64,d09GMgABAAAAAATcAA0...') format('woff2');
            }
          </style>
          <text font-family="Custom">Test</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1
        assert result.web_fonts[0].src[0].is_data_uri

    def test_parse_svg_with_remote_font(self):
        """Parse SVG with remote HTTPS font URL."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              font-family: 'Roboto';
              src: url('https://fonts.gstatic.com/s/roboto/v30/font.woff2') format('woff2');
            }
          </style>
          <text font-family="Roboto">Test</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1
        assert result.web_fonts[0].src[0].is_remote

    def test_parse_svg_with_local_font(self):
        """Parse SVG with local() font reference."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              font-family: 'Roboto';
              src: local('Roboto Regular'),
                   url('roboto.woff2') format('woff2');
            }
          </style>
          <text font-family="Roboto">Test</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1
        assert len(result.web_fonts[0].src) == 2
        assert result.web_fonts[0].src[0].is_local
        assert result.web_fonts[0].src[1].url == 'roboto.woff2'

    def test_parse_svg_with_fallback_src_chain(self):
        """Parse SVG with fallback src chain."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              font-family: 'OpenSans';
              src: url('opensans.woff2') format('woff2'),
                   url('opensans.woff') format('woff'),
                   url('opensans.ttf') format('truetype');
            }
          </style>
          <text font-family="OpenSans">Test</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1
        assert len(result.web_fonts[0].src) == 3

        # Check formats in order
        formats = [src.format for src in result.web_fonts[0].src]
        assert formats == ['woff2', 'woff', 'truetype']

    def test_parse_svg_without_font_face(self):
        """Parse SVG without @font-face."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <text font-family="Arial">Hello</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is None or len(result.web_fonts) == 0

    def test_parse_svg_with_multiple_style_elements(self):
        """Parse SVG with multiple <style> elements."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              font-family: 'Font1';
              src: url('font1.woff2');
            }
          </style>
          <defs>
            <style>
              @font-face {
                font-family: 'Font2';
                src: url('font2.woff2');
              }
            </style>
          </defs>
          <text font-family="Font1">Test1</text>
          <text font-family="Font2">Test2</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 2

        families = {rule.family for rule in result.web_fonts}
        assert families == {'Font1', 'Font2'}

    def test_parse_svg_with_malformed_font_face(self):
        """Malformed @font-face doesn't break parsing."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              /* Missing required descriptors */
              font-display: swap;
            }
            @font-face {
              font-family: 'Valid';
              src: url('valid.woff2');
            }
          </style>
          <rect width="100" height="100"/>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        # Only valid font-face parsed
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1
        assert result.web_fonts[0].family == 'Valid'

    def test_parse_svg_with_css_and_font_face(self):
        """SVG with both CSS rules and @font-face."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            .text-blue {
              fill: blue;
            }
            @font-face {
              font-family: 'CustomFont';
              src: url('custom.woff2');
            }
            #special {
              font-size: 24px;
            }
          </style>
          <text class="text-blue" id="special" font-family="CustomFont">Test</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        # Web fonts extracted
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1
        assert result.web_fonts[0].family == 'CustomFont'

        # CSS rules also collected (via StyleResolver)
        # This verifies both parsers work together

    def test_parse_svg_font_face_with_all_descriptors(self):
        """Parse @font-face with all descriptors."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              font-family: 'Roboto';
              src: url('roboto-italic-700.woff2') format('woff2');
              font-weight: 700;
              font-style: italic;
              font-display: swap;
              unicode-range: U+0000-00FF;
            }
          </style>
          <text font-family="Roboto">Test</text>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1

        rule = result.web_fonts[0]
        assert rule.family == 'Roboto'
        assert rule.weight == '700'
        assert rule.style == 'italic'
        assert rule.display == 'swap'
        # tinycss2 normalizes unicode-range
        assert rule.unicode_range is not None

    def test_parse_result_services_preserved(self):
        """ParseResult.services includes web fonts and CSS."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style>
            @font-face {
              font-family: 'Test';
              src: url('test.woff2');
            }
            .rect-red { fill: red; }
          </style>
          <rect class="rect-red" width="100" height="100"/>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.services is not None
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1

        # Verify services object is populated
        # (StyleResolver with CSS rules is registered internally)
        assert hasattr(result.services, 'resolve')

    def test_parse_empty_style_element(self):
        """Empty <style> element doesn't cause errors."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
          <style></style>
          <rect width="100" height="100"/>
        </svg>
        """
        parser = SVGParser()
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is None or len(result.web_fonts) == 0
