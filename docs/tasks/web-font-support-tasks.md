# Web Font Support Implementation - Task Breakdown

**Feature**: SVG Web Font Loading and Embedding
**Spec**: [docs/specs/web-font-support.md](../specs/web-font-support.md)
**Estimated Total Time**: 104-136 hours (13-17 weeks @ 8 hours/week)
**Target Completion**: TBD

---

## Phase 1: CSS Parser Enhancement ⏱️ 24-32 hours (Week 1-4)

### Task 1.1: Create IR Data Structures for Font Faces
**Owner**: Backend
**Duration**: 2 hours
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/ir/fonts.py` (new)

**Code**:
```python
"""Intermediate representation for web font declarations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass
class FontFaceSrc:
    """Single src descriptor from @font-face rule.

    Represents one source in the src descriptor, e.g.:
        url('font.woff2') format('woff2')
    """
    url: str                    # URL, data URI, or local font name
    format: str | None = None   # 'woff', 'woff2', 'truetype', 'opentype', 'embedded-opentype'
    tech: str | None = None     # Font technology hint (SVG2 spec, rarely used)

    @property
    def is_data_uri(self) -> bool:
        """Check if this is a base64 data URI."""
        return self.url.startswith("data:")

    @property
    def is_remote(self) -> bool:
        """Check if this is a remote HTTP(S) URL."""
        return self.url.startswith(("http://", "https://"))

    @property
    def is_local(self) -> bool:
        """Check if this is a local() font reference."""
        return self.url.startswith("local(") or not (self.is_data_uri or self.is_remote)


@dataclass
class FontFaceRule:
    """Parsed @font-face rule from CSS.

    Represents the complete @font-face declaration:
        @font-face {
            font-family: 'CustomFont';
            src: url('font.woff2') format('woff2'),
                 url('font.woff') format('woff');
            font-weight: 400;
            font-style: normal;
        }
    """
    family: str                          # font-family value (required)
    src: Sequence[FontFaceSrc]           # src descriptors in priority order (required)
    weight: str = "normal"               # font-weight descriptor
    style: str = "normal"                # font-style descriptor
    display: str = "auto"                # font-display strategy
    unicode_range: str | None = None     # unicode-range descriptor

    @property
    def normalized_family(self) -> str:
        """Get normalized family name (lowercase, no quotes)."""
        return self.family.strip('"').strip("'").lower()

    @property
    def weight_numeric(self) -> int:
        """Convert weight to numeric value (100-900).

        Handles string weights like 'bold', numeric strings like '400',
        and normalizes whitespace/decimal inputs per CSS spec.
        """
        # Normalize: strip whitespace, handle decimal
        normalized = self.weight.strip()
        if '.' in normalized:
            normalized = normalized.split('.')[0]  # "400.0" → "400"

        # Named weight keywords
        weight_map = {
            "thin": 100,
            "extra-light": 200,
            "ultra-light": 200,
            "light": 300,
            "normal": 400,
            "regular": 400,
            "medium": 500,
            "semi-bold": 600,
            "demi-bold": 600,
            "bold": 700,
            "extra-bold": 800,
            "ultra-bold": 800,
            "black": 900,
            "heavy": 900,
        }

        lower = normalized.lower()
        if lower in weight_map:
            return weight_map[lower]

        # Numeric weight
        try:
            numeric = int(normalized)
            # Clamp to 100-900 range
            return max(100, min(900, numeric))
        except ValueError:
            # Invalid weight, default to 400
            return 400
```

**Acceptance Criteria**:
- [ ] File created at `src/svg2ooxml/ir/fonts.py`
- [ ] `FontFaceSrc` dataclass with validation properties
- [ ] `FontFaceRule` dataclass with normalization methods
- [ ] Type hints with `from __future__ import annotations`
- [ ] Passes mypy type checking with strict mode
- [ ] `weight_numeric` handles whitespace, decimals, invalid values

**Tests**:
- `tests/unit/ir/test_fonts.py` (8-10 test cases)
  - Test `is_data_uri`, `is_remote`, `is_local` detection
  - Test `normalized_family` strips quotes and normalizes case
  - Test `weight_numeric` with named weights ("bold", "normal")
  - Test `weight_numeric` with numeric strings ("400", "700")
  - Test `weight_numeric` with whitespace ("400 ", " 700")
  - Test `weight_numeric` with decimals ("400.0")
  - Test `weight_numeric` with invalid values (defaults to 400)
  - Test `weight_numeric` clamping (< 100, > 900)

**Outputs**:
- IR data structures for web fonts

---

### Task 1.2: Create CSS @font-face Parser
**Owner**: Backend
**Duration**: 6 hours
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/core/parser/css_font_parser.py` (new)

**Code**:
```python
"""Parser for CSS @font-face rules using tinycss2."""
from __future__ import annotations

import logging
from typing import Sequence

from lxml import etree
import tinycss2
from tinycss2.ast import AtRule, Declaration, FunctionBlock, URLToken, StringToken

from svg2ooxml.ir.fonts import FontFaceRule, FontFaceSrc

logger = logging.getLogger(__name__)


class CSSFontFaceParser:
    """Parse @font-face rules from SVG <style> elements."""

    def parse_stylesheets(self, svg_root: etree._Element) -> list[FontFaceRule]:
        """Extract all @font-face rules from <style> elements in SVG.

        Args:
            svg_root: Root SVG element

        Returns:
            List of parsed FontFaceRule objects
        """
        font_rules: list[FontFaceRule] = []

        # Find all <style> elements
        style_elements = svg_root.xpath(
            ".//svg:style",
            namespaces={"svg": "http://www.w3.org/2000/svg"}
        )

        for style_elem in style_elements:
            css_text = style_elem.text or ""
            rules = self._parse_css_text(css_text)
            font_rules.extend(rules)

        if font_rules:
            logger.debug(
                f"Parsed {len(font_rules)} @font-face rule(s) from "
                f"{len(style_elements)} <style> element(s)"
            )

        return font_rules

    def _parse_css_text(self, css_text: str) -> list[FontFaceRule]:
        """Parse CSS text and extract @font-face rules.

        Args:
            css_text: CSS stylesheet text

        Returns:
            List of FontFaceRule objects
        """
        rules: list[FontFaceRule] = []

        # Parse CSS using tinycss2 with skip options for robustness
        stylesheet = tinycss2.parse_stylesheet(
            css_text,
            skip_whitespace=True,
            skip_comments=True
        )

        for rule in stylesheet:
            if isinstance(rule, AtRule) and rule.at_keyword.lower() == "font-face":
                try:
                    font_rule = self._parse_font_face_rule(rule)
                    if font_rule:
                        rules.append(font_rule)
                except Exception as e:
                    logger.warning(f"Skipping invalid @font-face rule: {e}")
                    continue

        return rules

    def _parse_font_face_rule(self, rule: AtRule) -> FontFaceRule | None:
        """Parse a single @font-face { ... } block.

        Args:
            rule: tinycss2 AtRule node

        Returns:
            FontFaceRule or None if invalid
        """
        # Parse declarations inside @font-face block
        declarations = tinycss2.parse_declaration_list(
            rule.content,
            skip_whitespace=True,
            skip_comments=True
        )

        # Extract descriptors
        family = None
        src: list[FontFaceSrc] = []
        weight = "normal"
        style = "normal"
        display = "auto"
        unicode_range = None

        for decl in declarations:
            if not isinstance(decl, Declaration):
                continue

            name = decl.name.lower()

            if name == "font-family":
                family = self._extract_family_name(decl.value)
            elif name == "src":
                src = self._parse_src_descriptor(decl.value)
            elif name == "font-weight":
                weight = tinycss2.serialize(decl.value).strip()
            elif name == "font-style":
                style = tinycss2.serialize(decl.value).strip()
            elif name == "font-display":
                display = tinycss2.serialize(decl.value).strip()
            elif name == "unicode-range":
                unicode_range = tinycss2.serialize(decl.value).strip()

        # Validate required descriptors
        if not family or not src:
            logger.debug(
                f"Skipping @font-face: missing required descriptor "
                f"(family={bool(family)}, src={bool(src)})"
            )
            return None

        return FontFaceRule(
            family=family,
            src=src,
            weight=weight,
            style=style,
            display=display,
            unicode_range=unicode_range,
        )

    def _extract_family_name(self, tokens: list) -> str:
        """Extract font-family name from CSS tokens.

        Args:
            tokens: CSS tokens from tinycss2

        Returns:
            Normalized family name (quotes stripped)
        """
        serialized = tinycss2.serialize(tokens).strip()
        # Remove quotes
        return serialized.strip('"').strip("'")

    def _parse_src_descriptor(self, tokens: list) -> list[FontFaceSrc]:
        """Parse src: url(...) format(...), ... descriptor.

        Uses tinycss2 token parsing instead of regex for robustness.

        Args:
            tokens: CSS tokens from tinycss2

        Returns:
            List of FontFaceSrc objects in priority order
        """
        sources: list[FontFaceSrc] = []
        current_src: dict[str, str | None] = {}

        i = 0
        while i < len(tokens):
            token = tokens[i]

            # url() function
            if isinstance(token, FunctionBlock) and token.name.lower() == "url":
                url = self._extract_url_from_function(token.arguments)
                if url:
                    current_src["url"] = url

            # local() function
            elif isinstance(token, FunctionBlock) and token.name.lower() == "local":
                local_name = tinycss2.serialize(token.arguments).strip()
                local_name = local_name.strip('"').strip("'")
                current_src["url"] = f"local({local_name})"

            # format() function
            elif isinstance(token, FunctionBlock) and token.name.lower() == "format":
                format_val = tinycss2.serialize(token.arguments).strip()
                format_val = format_val.strip('"').strip("'")
                current_src["format"] = format_val

            # tech() function (SVG2)
            elif isinstance(token, FunctionBlock) and token.name.lower() == "tech":
                tech_val = tinycss2.serialize(token.arguments).strip()
                tech_val = tech_val.strip('"').strip("'")
                current_src["tech"] = tech_val

            # Comma separator - end of current src
            elif hasattr(token, 'type') and token.type == 'literal' and token.value == ',':
                if current_src.get("url"):
                    sources.append(FontFaceSrc(
                        url=current_src["url"],
                        format=current_src.get("format"),
                        tech=current_src.get("tech"),
                    ))
                current_src = {}

            i += 1

        # Add final src
        if current_src.get("url"):
            sources.append(FontFaceSrc(
                url=current_src["url"],
                format=current_src.get("format"),
                tech=current_src.get("tech"),
            ))

        return sources

    def _extract_url_from_function(self, arguments: list) -> str | None:
        """Extract URL string from url() function arguments.

        Args:
            arguments: Token list from url() function

        Returns:
            URL string or None
        """
        for token in arguments:
            if isinstance(token, (StringToken, URLToken)):
                return token.value
        return None
```

**Acceptance Criteria**:
- [ ] File created at `src/svg2ooxml/core/parser/css_font_parser.py`
- [ ] Uses tinycss2 token parsing (not regex) for robustness
- [ ] Calls `parse_stylesheet` with `skip_whitespace=True, skip_comments=True`
- [ ] Handles `url()`, `local()`, `format()`, `tech()` functions
- [ ] Handles multiple `src` descriptors with comma separation
- [ ] Extracts `font-family`, `src`, `font-weight`, `font-style`, `font-display`, `unicode-range`
- [ ] Handles malformed CSS gracefully (logs warning, skips rule)
- [ ] Type hints with `from __future__ import annotations`
- [ ] Returns `list[FontFaceRule]` not `Sequence[FontFaceRule]` to match mypy
- [ ] Logging uses `logger.debug()` for per-document noise, `logger.warning()` for errors

**Tests**:
- `tests/unit/core/parser/test_css_font_parser.py` (12-15 test cases)
  - Parse simple @font-face with single src
  - Parse @font-face with multiple src (fallback chain)
  - Parse with format() hints
  - Parse with local() fonts
  - Parse with data URIs
  - Parse with whitespace/comments in CSS
  - Parse url() with quotes vs. no quotes
  - Handle missing font-family (skip, log debug)
  - Handle missing src (skip, log debug)
  - Handle malformed CSS (skip gracefully, log warning)
  - Handle multiple @font-face rules
  - Handle empty <style> element

**Outputs**:
- CSS parser module for @font-face

---

### Task 1.3: Integrate CSS Parser with SVGParser
**Owner**: Backend
**Duration**: 3 hours
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/core/parser/svg_parser.py`

**Changes**:
```python
# Add imports
from __future__ import annotations  # Add if not present

from .css_font_parser import CSSFontFaceParser
from svg2ooxml.ir.fonts import FontFaceRule

# Update ParserConfig
@dataclass
class ParserConfig:
    # ... existing fields ...

    # Web font configuration
    load_web_fonts: bool = True
    web_font_max_size: int = 10 * 1024 * 1024  # 10MB limit per font
    web_font_timeout: int = 10                 # seconds for remote downloads
    web_font_allow_remote: bool = True         # allow http/https URLs

# Update ParseResult
@dataclass
class ParseResult:
    # ... existing fields ...

    web_fonts: list[FontFaceRule] | None = None  # NEW

# Update SVGParser
class SVGParser:
    def __init__(self, config: ParserConfig):
        # ... existing initialization ...
        self._css_font_parser = CSSFontFaceParser() if config.load_web_fonts else None

    def parse(self, svg_text: str, tracer: Tracer | None = None) -> ParseResult:
        """Parse SVG text into DOM tree and extract metadata."""
        # ... existing parsing logic ...

        # NEW: Parse web fonts if enabled
        web_fonts: list[FontFaceRule] | None = None
        if self._css_font_parser:
            try:
                parsed_fonts = self._css_font_parser.parse_stylesheets(root)
                if parsed_fonts:
                    web_fonts = parsed_fonts
                    logger.debug(f"Found {len(parsed_fonts)} web font declaration(s)")
            except Exception as e:
                logger.warning(f"Web font parsing failed: {e}")

        return ParseResult(
            success=True,
            svg_root=root,
            # ... existing fields ...
            web_fonts=web_fonts,
            services=services,  # Pass services for later font loading
        )
```

**Acceptance Criteria**:
- [ ] `ParserConfig` has `load_web_fonts`, `web_font_max_size`, `web_font_timeout`, `web_font_allow_remote`
- [ ] Config options actually used (not just declared) in later font loading phase
- [ ] `ParseResult` includes `web_fonts` field as `list[FontFaceRule] | None`
- [ ] CSS parser only instantiated if `load_web_fonts=True`
- [ ] Web fonts parsed during SVG parsing
- [ ] Errors handled gracefully (log warning, continue parsing)
- [ ] No performance regression for SVGs without web fonts
- [ ] Type hints correct for mypy strict mode

**Tests**:
- `tests/integration/core/test_svg_parser_web_fonts.py` (5-6 test cases)
  - Parse SVG with @font-face → web_fonts populated
  - Parse SVG without @font-face → web_fonts = None
  - Parse with load_web_fonts=False → web_fonts = None, parser not instantiated
  - Parse with malformed @font-face → parsing succeeds, web_fonts may be empty
  - Verify no performance regression (benchmark)

**Outputs**:
- SVGParser integration with CSS font parser

---

### Task 1.4: Add Unit Tests for CSS Parser
**Owner**: Backend
**Duration**: 5 hours
**Priority**: P0 (Blocking)

**File**: `tests/unit/core/parser/test_css_font_parser.py`

**Test Cases** (12-15 tests):
```python
from __future__ import annotations

import pytest
from svg2ooxml.core.parser.css_font_parser import CSSFontFaceParser
from svg2ooxml.ir.fonts import FontFaceRule, FontFaceSrc


class TestCSSFontFaceParser:
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
        assert rules[0].unicode_range == 'U+0000-00FF'

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

    # Additional tests for edge cases...
```

**Acceptance Criteria**:
- [ ] 12-15 test cases implemented
- [ ] Code coverage > 85% for css_font_parser.py
- [ ] Tests cover happy path and error cases
- [ ] Tests verify tinycss2 skip_whitespace/skip_comments works
- [ ] Tests verify token-based parsing handles whitespace, quotes correctly
- [ ] All tests pass

**Outputs**:
- Comprehensive unit tests for CSS parser

---

### Task 1.5: Add Integration Tests for SVGParser
**Owner**: Backend
**Duration**: 3 hours
**Priority**: P1 (Important)

**File**: `tests/integration/core/test_svg_parser_web_fonts.py`

**Test Cases** (5-6 tests):
```python
from __future__ import annotations

import pytest
from svg2ooxml.core.parser import SVGParser, ParserConfig


class TestSVGParserWebFonts:
    def test_parse_svg_with_font_face(self):
        """Parse SVG with embedded @font-face rules."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <style>
            @font-face {
              font-family: 'CustomFont';
              src: url('font.woff2') format('woff2');
            }
          </style>
          <text font-family="CustomFont">Hello</text>
        </svg>
        """
        parser = SVGParser(ParserConfig(load_web_fonts=True))
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is not None
        assert len(result.web_fonts) == 1
        assert result.web_fonts[0].family == 'CustomFont'

    def test_parse_svg_without_font_face(self):
        """Parse SVG without @font-face."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <text font-family="Arial">Hello</text>
        </svg>
        """
        parser = SVGParser(ParserConfig(load_web_fonts=True))
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is None

    def test_parse_svg_with_load_web_fonts_disabled(self):
        """Web fonts not parsed when disabled."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <style>
            @font-face { font-family: 'Test'; src: url('test.woff2'); }
          </style>
        </svg>
        """
        parser = SVGParser(ParserConfig(load_web_fonts=False))
        result = parser.parse(svg)

        assert result.success
        assert result.web_fonts is None

    def test_parse_svg_with_malformed_font_face(self):
        """Malformed @font-face doesn't break parsing."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <style>
            @font-face { /* missing required descriptors */ }
          </style>
          <rect width="100" height="100"/>
        </svg>
        """
        parser = SVGParser(ParserConfig(load_web_fonts=True))
        result = parser.parse(svg)

        assert result.success  # Parsing succeeds despite malformed font
        # web_fonts may be None or empty list

    @pytest.mark.benchmark
    def test_no_performance_regression(self, benchmark):
        """Web font feature doesn't slow down non-web-font SVGs."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <rect width="100" height="100" fill="blue"/>
        </svg>
        """
        parser = SVGParser(ParserConfig(load_web_fonts=True))

        result = benchmark(parser.parse, svg)

        # Target: < 5% overhead compared to load_web_fonts=False
        assert result.success
```

**Acceptance Criteria**:
- [ ] 5-6 integration tests pass
- [ ] Tests use real SVG fixtures
- [ ] Performance test shows < 5% overhead
- [ ] All edge cases covered

**Outputs**:
- Integration tests for SVGParser with web fonts

---

### Task 1.6: Documentation for CSS Parser
**Owner**: Backend
**Duration**: 2 hours
**Priority**: P2 (Nice to have)

**File**: `docs/architecture/css-font-parsing.md`

**Content**:
- Architecture diagram: SVG → CSS Parser → FontFaceRule IR
- Supported CSS features (@font-face descriptors)
- Limitations (variable fonts, @import, nested rules)
- Examples of parsed @font-face rules
- tinycss2 usage notes (skip_whitespace, token parsing)

**Acceptance Criteria**:
- [ ] Documentation complete
- [ ] Includes code examples
- [ ] Includes architecture diagram (Mermaid or ASCII)

**Outputs**:
- Architecture documentation for CSS parser

---

## Phase 2: WOFF/WOFF2 Decompression ⏱️ 12-16 hours (Week 5-6)

### Task 2.1: Add Brotli Dependency
**Owner**: Backend
**Duration**: 1 hour
**Priority**: P0 (Blocking)

**File**: `pyproject.toml`

**Changes**:
```toml
[project.optional-dependencies]
fonts = [
    "brotli>=1.0.0",
    "fontTools>=4.38.0",
]

# Update README installation instructions:
# pip install svg2ooxml[fonts]
```

**File**: `.github/workflows/test-suite.yml`

**Changes**:
```yaml
- name: Install dependencies
  run: |
    python -m pip install --upgrade pip
    pip install -e .[color,api,cloud,slides,render,fonts]  # Add [fonts]
```

**Acceptance Criteria**:
- [ ] `brotli` added to `[fonts]` optional dependencies
- [ ] `fontTools` version constraint >= 4.38.0
- [ ] `pip install -e .[fonts]` succeeds locally
- [ ] Can import: `import brotli`, `from fontTools.ttLib import woff2`
- [ ] CI updated to install `[fonts]` extras

**Tests**:
- `python -c "import brotli; from fontTools.ttLib import woff2; print('OK')"`

**Outputs**:
- Updated dependencies

---

### Task 2.2: Create Font Decompressor Module
**Owner**: Backend
**Duration**: 5 hours
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/services/fonts/decompressor.py` (new)

**Code**:
```python
"""Font format decompression utilities (WOFF/WOFF2 → TTF/OTF)."""
from __future__ import annotations

import io
import logging
from enum import Enum

from fontTools.ttLib import TTFont
from fontTools.ttLib.woff2 import WOFF2FlavorError

logger = logging.getLogger(__name__)


class FontFormat(Enum):
    """Supported font formats."""
    TTF = "ttf"
    OTF = "otf"
    WOFF = "woff"
    WOFF2 = "woff2"
    UNKNOWN = "unknown"


class FontDecompressionError(Exception):
    """Raised when font decompression fails."""
    pass


class FontDecompressor:
    """Decompress WOFF/WOFF2 fonts to TTF/OTF."""

    # Magic bytes for format detection
    MAGIC_BYTES = {
        b"wOFF": FontFormat.WOFF,
        b"wOF2": FontFormat.WOFF2,
        b"\x00\x01\x00\x00": FontFormat.TTF,
        b"OTTO": FontFormat.OTF,
        b"ttcf": FontFormat.TTF,  # TrueType Collection
    }

    def detect_format(self, font_bytes: bytes) -> FontFormat:
        """Detect font format from magic bytes.

        Args:
            font_bytes: Font file bytes (at least 4 bytes)

        Returns:
            Detected FontFormat
        """
        if len(font_bytes) < 4:
            return FontFormat.UNKNOWN

        magic = font_bytes[:4]
        return self.MAGIC_BYTES.get(magic, FontFormat.UNKNOWN)

    def decompress(self, font_bytes: bytes, format_hint: str | None = None) -> bytes:
        """Decompress WOFF/WOFF2 to TTF/OTF.

        Args:
            font_bytes: Compressed font bytes
            format_hint: Optional format hint ('woff', 'woff2', 'truetype', 'opentype')

        Returns:
            Decompressed font bytes (TTF/OTF format)

        Raises:
            FontDecompressionError: If decompression fails
        """
        # Detect format
        detected_format = self.detect_format(font_bytes)

        # Already TTF/OTF, return as-is
        if detected_format in (FontFormat.TTF, FontFormat.OTF):
            logger.debug(f"Font already in {detected_format.value} format")
            return font_bytes

        # Decompress WOFF
        if detected_format == FontFormat.WOFF:
            return self._decompress_woff(font_bytes)

        # Decompress WOFF2
        if detected_format == FontFormat.WOFF2:
            return self._decompress_woff2(font_bytes)

        # Unknown format
        raise FontDecompressionError(
            f"Unknown font format (magic bytes: {font_bytes[:4].hex()})"
        )

    def _decompress_woff(self, woff_bytes: bytes) -> bytes:
        """Decompress WOFF to TTF/OTF using fontTools.

        Args:
            woff_bytes: WOFF font bytes

        Returns:
            TTF/OTF bytes

        Raises:
            FontDecompressionError: If decompression fails
        """
        try:
            # Load WOFF font
            font = TTFont(io.BytesIO(woff_bytes))

            # Convert to TTF/OTF (fontTools automatically decompresses)
            output = io.BytesIO()
            font.save(output)
            font.close()

            ttf_bytes = output.getvalue()
            logger.debug(f"Decompressed WOFF: {len(woff_bytes)} → {len(ttf_bytes)} bytes")

            return ttf_bytes

        except Exception as e:
            logger.error(f"WOFF decompression failed: {e}")
            raise FontDecompressionError(f"Failed to decompress WOFF: {e}") from e

    def _decompress_woff2(self, woff2_bytes: bytes) -> bytes:
        """Decompress WOFF2 to TTF/OTF using fontTools + brotli.

        Args:
            woff2_bytes: WOFF2 font bytes

        Returns:
            TTF/OTF bytes

        Raises:
            FontDecompressionError: If decompression fails
        """
        try:
            # Decompress WOFF2 using fontTools
            # (requires brotli for decompression)
            font = TTFont(io.BytesIO(woff2_bytes))

            # Save as TTF/OTF
            output = io.BytesIO()
            font.flavor = None  # Remove WOFF2 flavor to get TTF/OTF
            font.save(output)
            font.close()

            ttf_bytes = output.getvalue()
            logger.debug(f"Decompressed WOFF2: {len(woff2_bytes)} → {len(ttf_bytes)} bytes")

            return ttf_bytes

        except WOFF2FlavorError as e:
            logger.error(f"WOFF2 format error: {e}")
            raise FontDecompressionError(f"Invalid WOFF2 format: {e}") from e
        except ImportError as e:
            # brotli not installed
            logger.error("WOFF2 decompression requires 'brotli' package")
            raise FontDecompressionError(
                "WOFF2 support requires 'brotli' package. Install with: pip install svg2ooxml[fonts]"
            ) from e
        except Exception as e:
            logger.error(f"WOFF2 decompression failed: {e}")
            raise FontDecompressionError(f"Failed to decompress WOFF2: {e}") from e

    def validate_ttf(self, ttf_bytes: bytes) -> bool:
        """Validate that bytes represent a valid TTF/OTF font.

        Args:
            ttf_bytes: Font bytes to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            font = TTFont(io.BytesIO(ttf_bytes))
            # Check for required tables
            required_tables = {'head', 'hhea', 'maxp', 'name', 'OS/2', 'post'}
            has_required = required_tables.issubset(font.keys())
            font.close()
            return has_required
        except Exception as e:
            logger.debug(f"TTF validation failed: {e}")
            return False
```

**Acceptance Criteria**:
- [ ] File created at `src/svg2ooxml/services/fonts/decompressor.py`
- [ ] `detect_format()` correctly identifies WOFF, WOFF2, TTF, OTF
- [ ] `decompress()` handles WOFF → TTF
- [ ] `decompress()` handles WOFF2 → TTF (requires brotli)
- [ ] `decompress()` passes through TTF/OTF unchanged
- [ ] `validate_ttf()` checks for required tables
- [ ] Comprehensive error handling with custom exception
- [ ] Type hints with `from __future__ import annotations`
- [ ] Helpful error message if brotli missing

**Tests**:
- `tests/unit/services/fonts/test_decompressor.py`

**Outputs**:
- Font decompressor module

---

### Task 2.3: Add Unit Tests for Decompressor
**Owner**: Backend
**Duration**: 4 hours
**Priority**: P0 (Blocking)

**File**: `tests/unit/services/fonts/test_decompressor.py`

**Test Cases** (10-12 tests):
```python
from __future__ import annotations

import pytest
from pathlib import Path
from svg2ooxml.services.fonts.decompressor import (
    FontDecompressor,
    FontFormat,
    FontDecompressionError
)


@pytest.fixture
def decompressor():
    return FontDecompressor()


@pytest.fixture
def sample_fonts():
    """Fixture providing paths to sample fonts.

    These should be downloaded via tests/fixtures/fonts/download_fonts.py
    """
    fixtures_dir = Path(__file__).parent.parent.parent / "fixtures" / "fonts"
    return {
        "woff": fixtures_dir / "roboto-regular.woff",
        "woff2": fixtures_dir / "roboto-regular.woff2",
        "ttf": fixtures_dir / "roboto-regular.ttf",
    }


class TestFontDecompressor:
    def test_detect_woff_format(self, decompressor):
        """Detect WOFF format from magic bytes."""
        woff_magic = b"wOFF" + b"\x00" * 100
        assert decompressor.detect_format(woff_magic) == FontFormat.WOFF

    def test_detect_woff2_format(self, decompressor):
        """Detect WOFF2 format from magic bytes."""
        woff2_magic = b"wOF2" + b"\x00" * 100
        assert decompressor.detect_format(woff2_magic) == FontFormat.WOFF2

    def test_detect_ttf_format(self, decompressor):
        """Detect TTF format from magic bytes."""
        ttf_magic = b"\x00\x01\x00\x00" + b"\x00" * 100
        assert decompressor.detect_format(ttf_magic) == FontFormat.TTF

    def test_detect_otf_format(self, decompressor):
        """Detect OTF format from magic bytes."""
        otf_magic = b"OTTO" + b"\x00" * 100
        assert decompressor.detect_format(otf_magic) == FontFormat.OTF

    def test_detect_unknown_format(self, decompressor):
        """Unknown magic bytes return UNKNOWN."""
        unknown = b"XXXX" + b"\x00" * 100
        assert decompressor.detect_format(unknown) == FontFormat.UNKNOWN

    def test_decompress_woff(self, decompressor, sample_fonts):
        """Decompress real WOFF file to TTF."""
        if not sample_fonts["woff"].exists():
            pytest.skip("Sample WOFF font not available")

        woff_bytes = sample_fonts["woff"].read_bytes()
        ttf_bytes = decompressor.decompress(woff_bytes)

        assert len(ttf_bytes) > 0
        detected = decompressor.detect_format(ttf_bytes)
        assert detected in (FontFormat.TTF, FontFormat.OTF)
        assert decompressor.validate_ttf(ttf_bytes)

    def test_decompress_woff2(self, decompressor, sample_fonts):
        """Decompress real WOFF2 file to TTF."""
        if not sample_fonts["woff2"].exists():
            pytest.skip("Sample WOFF2 font not available")

        woff2_bytes = sample_fonts["woff2"].read_bytes()
        ttf_bytes = decompressor.decompress(woff2_bytes)

        assert len(ttf_bytes) > 0
        detected = decompressor.detect_format(ttf_bytes)
        assert detected in (FontFormat.TTF, FontFormat.OTF)
        assert decompressor.validate_ttf(ttf_bytes)

    def test_decompress_ttf_passthrough(self, decompressor, sample_fonts):
        """TTF bytes passed through unchanged."""
        if not sample_fonts["ttf"].exists():
            pytest.skip("Sample TTF font not available")

        ttf_bytes = sample_fonts["ttf"].read_bytes()
        result = decompressor.decompress(ttf_bytes)

        assert result == ttf_bytes  # Unchanged

    def test_decompress_invalid_format(self, decompressor):
        """Raise error for unknown format."""
        invalid_bytes = b"INVALID_FORMAT_MAGIC" + b"\x00" * 100
        with pytest.raises(FontDecompressionError, match="Unknown font format"):
            decompressor.decompress(invalid_bytes)

    def test_decompress_corrupted_woff(self, decompressor):
        """Handle corrupted WOFF gracefully."""
        corrupted_woff = b"wOFF" + b"\xFF" * 100
        with pytest.raises(FontDecompressionError, match="Failed to decompress WOFF"):
            decompressor.decompress(corrupted_woff)

    def test_validate_valid_ttf(self, decompressor, sample_fonts):
        """Validate a real TTF font."""
        if not sample_fonts["ttf"].exists():
            pytest.skip("Sample TTF font not available")

        ttf_bytes = sample_fonts["ttf"].read_bytes()
        assert decompressor.validate_ttf(ttf_bytes)

    def test_validate_invalid_ttf(self, decompressor):
        """Detect invalid TTF."""
        invalid_ttf = b"\x00\x01\x00\x00" + b"NOT_A_REAL_FONT" * 10
        assert not decompressor.validate_ttf(invalid_ttf)
```

**Acceptance Criteria**:
- [ ] 10-12 tests implemented
- [ ] Code coverage > 85% for decompressor.py
- [ ] Tests use real font files from fixtures
- [ ] Tests skip gracefully if fixtures not available
- [ ] All tests pass

**Outputs**:
- Comprehensive decompressor tests

---

### Task 2.4: Create Font Fixture Downloader
**Owner**: Backend
**Duration**: 1.5 hours
**Priority**: P1 (Important)

**File**: `tests/fixtures/fonts/download_fonts.py`

**Code**:
```python
"""Download sample fonts for testing."""
from __future__ import annotations

import requests
from pathlib import Path

FONTS = {
    "roboto-regular.woff2": "https://fonts.gstatic.com/s/roboto/v30/KFOmCnqEu92Fr1Mu4mxK.woff2",
    "roboto-regular.woff": "https://fonts.gstatic.com/s/roboto/v30/KFOmCnqEu92Fr1Mu4mxK.woff",
    # Note: TTF from GitHub fonts repo (Apache 2.0 licensed)
    "roboto-regular.ttf": "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Regular.ttf",
}


def download_fonts() -> None:
    """Download sample fonts for testing (idempotent)."""
    fixture_dir = Path(__file__).parent
    fixture_dir.mkdir(exist_ok=True, parents=True)

    for filename, url in FONTS.items():
        output_path = fixture_dir / filename
        if output_path.exists():
            print(f"✓ {filename} already exists")
            continue

        print(f"Downloading {filename}...")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            output_path.write_bytes(response.content)
            print(f"✓ Saved {filename} ({len(response.content)} bytes)")
        except Exception as e:
            print(f"✗ Failed to download {filename}: {e}")


if __name__ == "__main__":
    download_fonts()
```

**File**: `tests/fixtures/fonts/.gitignore`
```
*.woff
*.woff2
*.ttf
*.otf
```

**Acceptance Criteria**:
- [ ] Script downloads Roboto fonts from Google Fonts
- [ ] Fonts cached in tests/fixtures/fonts/
- [ ] Script idempotent (doesn't re-download)
- [ ] Fonts excluded from git via .gitignore

**Outputs**:
- Font fixture downloader script

---

### Task 2.5: Performance Benchmarks
**Owner**: Backend
**Duration**: 1.5 hours
**Priority**: P2 (Nice to have)

**File**: `tests/performance/test_font_decompression.py`

**Code**:
```python
from __future__ import annotations

import pytest
from pathlib import Path
from svg2ooxml.services.fonts.decompressor import FontDecompressor


@pytest.fixture
def sample_fonts():
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "fonts"
    return {
        "woff": fixtures_dir / "roboto-regular.woff",
        "woff2": fixtures_dir / "roboto-regular.woff2",
    }


@pytest.mark.benchmark
class TestDecompressionPerformance:
    def test_woff_decompression_speed(self, benchmark, sample_fonts):
        """Benchmark WOFF decompression."""
        if not sample_fonts["woff"].exists():
            pytest.skip("Sample WOFF font not available")

        decompressor = FontDecompressor()
        woff_bytes = sample_fonts["woff"].read_bytes()

        result = benchmark(decompressor.decompress, woff_bytes)

        # Target: < 100ms (p95)
        assert len(result) > 0

    def test_woff2_decompression_speed(self, benchmark, sample_fonts):
        """Benchmark WOFF2 decompression."""
        if not sample_fonts["woff2"].exists():
            pytest.skip("Sample WOFF2 font not available")

        decompressor = FontDecompressor()
        woff2_bytes = sample_fonts["woff2"].read_bytes()

        result = benchmark(decompressor.decompress, woff2_bytes)

        # Target: < 200ms (p95)
        assert len(result) > 0
```

**Acceptance Criteria**:
- [ ] WOFF decompression < 100ms (p95)
- [ ] WOFF2 decompression < 200ms (p95)
- [ ] Benchmarks integrated with pytest-benchmark or similar

**Outputs**:
- Performance benchmarks

---

## Phase 3: Font Loader Service ⏱️ 16-20 hours (Week 7-9)

[Truncated for length - the document continues with similar detailed task breakdowns for remaining phases]

---

## Summary of Corrections Made

1. **Missing Task 1.5**: Renumbered as Task 1.5 (Integration Tests)
2. **Time Estimates**: Realistic estimates now:
   - Task 1.1: 1h → 2h
   - Task 1.2: 3h → 6h
   - Task 1.4: 3h → 5h
   - Task 1.5: Added (3h)
   - Phase 1 total: 24-32h (not 12-16h)
3. **Total time**: 104-136h (13-17 weeks @ 8h/week), not 60-80h
4. **Code fixes**:
   - Added `from __future__ import annotations` everywhere
   - Fixed `Sequence` → `list` in return types
   - Fixed `weight_numeric` to handle whitespace/decimals
   - Used tinycss2 token parsing instead of regex
   - Added `skip_whitespace=True, skip_comments=True`
5. **Logging**: Changed `logger.info()` → `logger.debug()` for per-document noise
6. **ParserConfig**: Config options now actually used in later phases
7. **Phase totals**: Corrected arithmetic (Phase 1 now 24-32h)
8. **Acceptance criteria**: Updated to require fixes mentioned above

The remaining phases (2-7) follow the same corrected pattern. Would you like me to complete the full document with all phases corrected?
