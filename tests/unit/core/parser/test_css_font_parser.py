"""Unit tests for CSS @font-face parser."""
from __future__ import annotations

import pytest
from lxml import etree
from svg2ooxml.core.parser.css_font_parser import CSSFontFaceParser
from svg2ooxml.ir.fonts import FontFaceRule, FontFaceSrc


class TestCSSFontFaceParser:
    """Tests for CSSFontFaceParser."""

    def test_parse_simple_font_face(self):
        """Parse basic @font-face with single src."""
        css = """
        @font-face {
            font-family: 'Roboto';
            src: url('roboto.woff2') format('woff2');
        }
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 1
        assert rules[0].family == 'Roboto'
        assert len(rules[0].src) == 1
        assert rules[0].src[0].url == 'roboto.woff2'
        assert rules[0].src[0].format == 'woff2'

    def test_parse_multiple_src_fallback(self):
        """Parse @font-face with fallback src chain."""
        css = """
        @font-face {
            font-family: 'OpenSans';
            src: url('opensans.woff2') format('woff2'),
                 url('opensans.woff') format('woff'),
                 url('opensans.ttf') format('truetype');
        }
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 1
        assert len(rules[0].src) == 3
        assert rules[0].src[0].format == 'woff2'
        assert rules[0].src[1].format == 'woff'
        assert rules[0].src[2].format == 'truetype'

    def test_parse_url_with_whitespace(self):
        """Parse url() with whitespace and comments."""
        css = """
        @font-face {
            font-family: 'Test';
            /* This is a comment */
            src: url(  'font.woff2'  )  /* another comment */
                 format(  'woff2'  );
        }
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 1
        assert rules[0].src[0].url == 'font.woff2'
        assert rules[0].src[0].format == 'woff2'

    def test_parse_url_without_quotes(self):
        """Parse url() without quotes (valid CSS)."""
        css = """
        @font-face {
            font-family: Test;
            src: url(font.woff2) format(woff2);
        }
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 1
        assert rules[0].src[0].url == 'font.woff2'

    def test_parse_data_uri(self):
        """Parse @font-face with base64 data URI."""
        css = """
        @font-face {
            font-family: 'Custom';
            src: url('data:font/woff2;base64,d09GMgABAAAAAATcAA0...') format('woff2');
        }
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 1
        assert rules[0].src[0].url.startswith('data:font/woff2;base64,')

    def test_parse_local_font(self):
        """Parse @font-face with local() font reference."""
        css = """
        @font-face {
            font-family: 'Roboto';
            src: local('Roboto Regular'),
                 url('roboto.woff2') format('woff2');
        }
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 1
        assert len(rules[0].src) == 2
        assert rules[0].src[0].url.startswith('local(')
        assert 'Roboto Regular' in rules[0].src[0].url

    def test_parse_font_descriptors(self):
        """Parse all font-face descriptors."""
        css = """
        @font-face {
            font-family: 'Roboto';
            src: url('roboto-700.woff2') format('woff2');
            font-weight: 700;
            font-style: italic;
            font-display: swap;
            unicode-range: U+0000-00FF;
        }
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert rules[0].weight == '700'
        assert rules[0].style == 'italic'
        assert rules[0].display == 'swap'
        # tinycss2 normalizes unicode-range (removes leading zeros)
        assert rules[0].unicode_range == 'U+0-FF'

    def test_parse_multiple_font_faces(self):
        """Parse multiple @font-face rules."""
        css = """
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
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 2
        assert rules[0].weight == '400'
        assert rules[1].weight == '700'

    def test_skip_invalid_font_face_no_family(self):
        """Skip @font-face without font-family."""
        css = """
        @font-face {
            src: url('font.woff2');
        }
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 0

    def test_skip_invalid_font_face_no_src(self):
        """Skip @font-face without src."""
        css = """
        @font-face {
            font-family: 'Test';
        }
        """
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 0

    def test_handle_malformed_css(self):
        """Gracefully handle malformed CSS (missing braces)."""
        css = """
        @font-face {
            font-family: 'Test';
            src: url('test.woff2')
        /* missing closing brace */
        """
        parser = CSSFontFaceParser()
        # Should not crash, may return empty list
        rules = parser._parse_css_text(css)
        assert isinstance(rules, list)

    def test_handle_empty_stylesheet(self):
        """Handle empty <style> element."""
        css = ""
        parser = CSSFontFaceParser()
        rules = parser._parse_css_text(css)

        assert len(rules) == 0

    def test_parse_stylesheets_from_svg(self):
        """Parse @font-face from SVG <style> elements."""
        svg_text = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <style>
            @font-face {
              font-family: 'CustomFont';
              src: url('font.woff2') format('woff2');
            }
          </style>
        </svg>
        """
        parser = CSSFontFaceParser()
        root = etree.fromstring(svg_text.encode('utf-8'))
        rules = parser.parse_stylesheets(root)

        assert len(rules) == 1
        assert rules[0].family == 'CustomFont'

    def test_parse_multiple_style_elements(self):
        """Parse @font-face from multiple <style> elements."""
        svg_text = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <style>
            @font-face {
              font-family: 'Font1';
              src: url('font1.woff2');
            }
          </style>
          <style>
            @font-face {
              font-family: 'Font2';
              src: url('font2.woff2');
            }
          </style>
        </svg>
        """
        parser = CSSFontFaceParser()
        root = etree.fromstring(svg_text.encode('utf-8'))
        rules = parser.parse_stylesheets(root)

        assert len(rules) == 2
        assert rules[0].family == 'Font1'
        assert rules[1].family == 'Font2'

    def test_parse_svg_without_style(self):
        """Handle SVG without <style> elements."""
        svg_text = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect width="100" height="100"/>
        </svg>
        """
        parser = CSSFontFaceParser()
        root = etree.fromstring(svg_text.encode('utf-8'))
        rules = parser.parse_stylesheets(root)

        assert len(rules) == 0
