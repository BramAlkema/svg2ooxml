# CSS Font Parsing Architecture

**Status**: Implementation snapshot
**Scope**: Parser-side extraction of CSS `@font-face` rules into IR structures carried forward in `ParseResult`.

## Overview

The CSS Font Parsing subsystem extracts `@font-face` rules from SVG `<style>` elements and makes web font declarations available throughout the conversion pipeline. This enables proper handling of custom fonts embedded in SVG files.

This document owns the parsing-side architecture only: how `@font-face` is recognized, normalized, and surfaced to later stages. It does not own the broader web-font loading and embedding rollout, which is tracked in:
- `docs/specs/web-font-support.md`
- `docs/tasks/web-font-support-tasks.md`

## Architecture

```
┌─────────────────────┐
│   SVG Document      │
│   <style>           │
│     @font-face {...}│
│   </style>          │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   SVGParser         │
│  - parse()          │
└──────────┬──────────┘
           │
           ├─────────────────────────┐
           │                         │
           ▼                         ▼
┌─────────────────────┐   ┌─────────────────────┐
│  StyleResolver      │   │ CSSFontFaceParser   │
│  - collect_css()    │   │ - parse_stylesheets()│
│  (selectors, rules) │   │ (@font-face only)   │
└─────────────────────┘   └──────────┬──────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │  FontFaceRule IR    │
                          │  - family           │
                          │  - src[]            │
                          │  - weight, style    │
                          └──────────┬──────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │   ParseResult       │
                          │   .web_fonts        │
                          └─────────────────────┘
```

## Components

### 1. Intermediate Representation (IR)

**File**: `src/svg2ooxml/ir/fonts.py`

#### `FontFaceSrc`
Represents a single source in the `src` descriptor:

```python
@dataclass
class FontFaceSrc:
    url: str                    # URL, data URI, or local font name
    format: str | None = None   # 'woff', 'woff2', 'truetype', etc.
    tech: str | None = None     # Font technology hint (rarely used)
```

**Properties**:
- `is_data_uri` - Checks if URL is a base64 data URI
- `is_remote` - Checks if URL is HTTP(S)
- `is_local` - Checks if URL references a local font

**Example**:
```python
FontFaceSrc(
    url='roboto.woff2',
    format='woff2'
)
```

#### `FontFaceRule`
Represents a complete `@font-face` declaration:

```python
@dataclass
class FontFaceRule:
    family: str                          # Required
    src: Sequence[FontFaceSrc]           # Required, priority order
    weight: str = "normal"               # Optional
    style: str = "normal"                # Optional
    display: str = "auto"                # Optional
    unicode_range: str | None = None     # Optional
```

**Properties**:
- `normalized_family` - Lowercase family name without quotes
- `weight_numeric` - Converts weight to numeric value (100-900)

**Example**:
```python
FontFaceRule(
    family='Roboto',
    src=[
        FontFaceSrc(url='roboto.woff2', format='woff2'),
        FontFaceSrc(url='roboto.woff', format='woff')
    ],
    weight='700',
    style='italic'
)
```

### 2. CSS Parser

**File**: `src/svg2ooxml/core/parser/css_font_parser.py`

#### `CSSFontFaceParser`
Parses `@font-face` rules from SVG `<style>` elements using tinycss2.

**Key Methods**:

##### `parse_stylesheets(svg_root) -> list[FontFaceRule]`
Main entry point. Extracts all `@font-face` rules from all `<style>` elements.

```python
parser = CSSFontFaceParser()
rules = parser.parse_stylesheets(svg_root)
# Returns list of FontFaceRule objects
```

**Implementation Details**:
- Uses XPath to find all `<style>` elements
- Handles multiple `<style>` elements (including nested in `<defs>`)
- Returns empty list if no `@font-face` rules found

##### `_parse_css_text(css_text) -> list[FontFaceRule]`
Parses CSS text and extracts `@font-face` rules.

**Robustness Features**:
- Uses `tinycss2.parse_stylesheet()` with `skip_whitespace=True, skip_comments=True`
- Gracefully handles malformed CSS (logs warning, continues)
- Validates required descriptors (family, src)

##### `_parse_src_descriptor(tokens) -> list[FontFaceSrc]`
Parses `src` descriptor using token-based parsing.

**Supported Syntax**:
```css
/* Quoted URL */
src: url('font.woff2') format('woff2');

/* Unquoted URL */
src: url(font.woff2) format(woff2);

/* Data URI */
src: url('data:font/woff2;base64,d09GMg...');

/* Local font */
src: local('Roboto Regular');

/* Fallback chain */
src: url('font.woff2') format('woff2'),
     url('font.woff') format('woff'),
     url('font.ttf') format('truetype');

/* Local + fallback */
src: local('Roboto'),
     url('roboto.woff2') format('woff2');
```

**Token Handling**:
- `URLToken` - Unquoted URLs (e.g., `url(font.woff2)`)
- `FunctionBlock(url)` - Quoted URLs (e.g., `url('font.woff2')`)
- `FunctionBlock(local)` - Local font references
- `FunctionBlock(format)` - Format hints
- `FunctionBlock(tech)` - Technology hints (SVG2 spec)

### 3. Integration with SVGParser

**File**: `src/svg2ooxml/core/parser/svg_parser.py`

**Integration Points**:

1. **Initialization** (line ~88):
```python
def __init__(self, config, services):
    # ... existing initialization ...
    self._font_parser = CSSFontFaceParser()
```

2. **Parsing** (line ~185-188):
```python
# After CSS selector collection
self._style_resolver.collect_css(root)

# Parse web fonts from @font-face rules
web_fonts = self._font_parser.parse_stylesheets(root)
```

3. **Result** (line ~269, ~296):
```python
return ParseResult.success_with(
    # ... existing fields ...
    web_fonts=web_fonts if web_fonts else None,
)
```

**Design Principles**:
- **No duplication**: StyleResolver handles CSS selectors, CSSFontFaceParser handles @font-face
- **No config changes**: Uses existing ParserConfig, no new flags needed
- **Minimal coupling**: Font parser is independent, called after collect_css()
- **Zero regression**: All existing tests pass unchanged

### 4. ParseResult Extension

**File**: `src/svg2ooxml/core/parser/result.py`

**Added Field**:
```python
@dataclass(slots=True)
class ParseResult:
    # ... existing fields ...
    web_fonts: "list[FontFaceRule] | None" = None
```

**Usage**:
```python
parser = SVGParser()
result = parser.parse(svg_content)

if result.web_fonts:
    for rule in result.web_fonts:
        print(f"Font: {rule.family}, Weight: {rule.weight}")
        for src in rule.src:
            print(f"  - {src.url} ({src.format})")
```

## Supported CSS Features

### Font Descriptors

| Descriptor      | Support | Notes                                      |
|-----------------|---------|-------------------------------------------|
| `font-family`   | ✅ Full | Required. Quotes stripped.                |
| `src`           | ✅ Full | Required. Supports fallback chains.       |
| `font-weight`   | ✅ Full | Named (bold) and numeric (100-900).       |
| `font-style`    | ✅ Full | normal, italic, oblique.                  |
| `font-display`  | ✅ Full | auto, block, swap, fallback, optional.    |
| `unicode-range` | ✅ Full | Preserved as-is (tinycss2 normalizes).    |

### Source Formats

| Format Type     | Example                                    | Support |
|-----------------|-------------------------------------------|---------|
| Local fonts     | `local('Roboto Regular')`                 | ✅ Full |
| Remote URLs     | `url('https://fonts.../font.woff2')`      | ✅ Full |
| Relative URLs   | `url('../fonts/font.woff2')`              | ✅ Full |
| Data URIs       | `url('data:font/woff2;base64,...')`       | ✅ Full |
| Unquoted URLs   | `url(font.woff2)`                         | ✅ Full |

### Font Formats

| Format          | MIME Type                  | Support |
|-----------------|---------------------------|---------|
| WOFF2           | `font/woff2`              | ✅ Full |
| WOFF            | `font/woff`               | ✅ Full |
| TrueType        | `font/ttf`                | ✅ Full |
| OpenType        | `font/otf`                | ✅ Full |
| Embedded OT     | `application/vnd.ms-fontobject` | ✅ Full |

## Limitations

### Not Currently Supported

1. **Variable Fonts** (CSS Fonts Level 4)
   - `font-variation-settings` descriptor
   - `font-weight: 100 900` range syntax
   - **Reason**: Requires additional IR fields and rendering engine support

2. **@import in <style>**
   - `@import url('fonts.css');`
   - **Reason**: No external resource loading in parser phase

3. **Nested @font-face in @media**
   ```css
   @media (min-width: 600px) {
       @font-face { ... }
   }
   ```
   - **Reason**: tinycss2 doesn't parse nested at-rules in media queries

4. **CSS Feature Queries**
   - `@supports (font-variation-settings: 'wght' 400)`
   - **Reason**: Out of scope for SVG parsing

### Graceful Degradation

The parser handles invalid CSS gracefully:
- **Missing required descriptors**: Rule skipped, warning logged
- **Malformed src**: Rule skipped, warning logged
- **Unknown descriptors**: Ignored silently
- **Invalid syntax**: Rule skipped, parsing continues

## Usage Examples

### Basic Parsing

```python
from svg2ooxml.core.parser import SVGParser

svg = """
<svg xmlns="http://www.w3.org/2000/svg">
  <style>
    @font-face {
      font-family: 'CustomFont';
      src: url('custom.woff2') format('woff2');
    }
  </style>
  <text font-family="CustomFont">Hello</text>
</svg>
"""

parser = SVGParser()
result = parser.parse(svg)

if result.web_fonts:
    for rule in result.web_fonts:
        print(f"Loaded font: {rule.family}")
```

### Multiple Weights

```python
svg = """
<svg xmlns="http://www.w3.org/2000/svg">
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
</svg>
"""

parser = SVGParser()
result = parser.parse(svg)

# result.web_fonts contains 2 FontFaceRule objects
# One for weight 400, one for weight 700
```

### Fallback Chain

```python
svg = """
<svg xmlns="http://www.w3.org/2000/svg">
  <style>
    @font-face {
      font-family: 'OpenSans';
      src: url('opensans.woff2') format('woff2'),
           url('opensans.woff') format('woff'),
           url('opensans.ttf') format('truetype');
    }
  </style>
</svg>
"""

parser = SVGParser()
result = parser.parse(svg)

rule = result.web_fonts[0]
# rule.src contains 3 FontFaceSrc objects in priority order
# Font loader will try woff2 first, then woff, then ttf
```

### Checking Font Source Type

```python
for rule in result.web_fonts:
    for src in rule.src:
        if src.is_remote:
            print(f"Need to download: {src.url}")
        elif src.is_data_uri:
            print(f"Embedded font: {src.format}")
        elif src.is_local:
            print(f"System font: {src.url}")
```

## Testing

### Test Coverage

- **Unit tests**: 15 tests in `tests/unit/core/parser/test_css_font_parser.py`
  - URL parsing (quoted, unquoted, data URIs, local)
  - Descriptor parsing (weight, style, display, unicode-range)
  - Fallback chains
  - Error handling (missing descriptors, malformed CSS)
  - Multiple @font-face rules

- **Integration tests**: 13 tests in `tests/integration/core/test_svg_parser_web_fonts.py`
  - End-to-end SVGParser flow
  - Multiple style elements
  - CSS rules + @font-face coexistence
  - ParseResult services preservation
  - Edge cases (empty styles, malformed rules)

- **IR tests**: 25 tests in `tests/unit/ir/test_fonts.py`
  - FontFaceSrc properties
  - FontFaceRule properties
  - Weight normalization (named, numeric, whitespace, decimals)
  - URL type detection

**Total**: 53 tests, 100% passing

### Running Tests

```bash
# All font-related tests
source .venv/bin/activate
python -m pytest tests/unit/ir/test_fonts.py \
                 tests/unit/core/parser/test_css_font_parser.py \
                 tests/integration/core/test_svg_parser_web_fonts.py -v

# Just CSS parser unit tests
python -m pytest tests/unit/core/parser/test_css_font_parser.py -v

# Just integration tests
python -m pytest tests/integration/core/test_svg_parser_web_fonts.py -v
```

## Implementation Notes

### Why tinycss2?

1. **Token-based parsing**: More robust than regex for CSS
2. **Standard compliance**: Follows CSS parsing spec
3. **Error recovery**: Graceful handling of malformed CSS
4. **Whitespace/comment handling**: Built-in normalization
5. **No external dependencies**: Pure Python

### Type Safety

All components use strict type annotations:
- `from __future__ import annotations` for forward references
- Full mypy strict mode compliance
- `TYPE_CHECKING` blocks for circular imports
- Explicit `cast()` for untyped library returns

### Performance

- **Lazy parsing**: Only parses @font-face rules, ignores other CSS
- **Single pass**: All <style> elements processed in one traversal
- **Minimal overhead**: ~0.1ms per @font-face rule on typical hardware

### Logging

Uses Python logging framework:
```python
logger.debug(f"Parsed {len(font_rules)} @font-face rule(s)")
logger.warning(f"Skipping invalid @font-face rule: {e}")
```

Configure in application:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Follow-On Work

### Downstream Work (Tracked Elsewhere)

1. **Font Loading Service**
   - Download remote fonts
   - Decode base64 data URIs
   - WOFF/WOFF2 decompression

2. **Font Registry**
   - Cache loaded fonts
   - Font matching algorithm (family, weight, style)

3. **Rendering Integration**
   - Text measurement with custom fonts
   - Glyph extraction for OOXML

### Additional Follow-On Topics

1. **Variable Fonts Support**
   - Parse `font-variation-settings`
   - Handle weight ranges (`100 900`)

2. **@import Support**
   - Load external stylesheets
   - Recursive font extraction

3. **Feature Queries**
   - Conditional font loading based on capabilities

Keep scope, prioritization, and acceptance criteria for those items in the web-font spec/task docs rather than extending this parser architecture note.

## References

- [CSS Fonts Module Level 3](https://www.w3.org/TR/css-fonts-3/)
- [CSS Fonts Module Level 4](https://www.w3.org/TR/css-fonts-4/)
- [tinycss2 Documentation](https://doc.courtbouillon.org/tinycss2/)
- [WOFF File Format 1.0](https://www.w3.org/TR/WOFF/)
- [WOFF File Format 2.0](https://www.w3.org/TR/WOFF2/)
- [Web Font Support Specification](../specs/web-font-support.md)
- [Web Font Support Tasks](../tasks/web-font-support-tasks.md)
