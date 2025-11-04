# WebFont Provider Architecture

## Overview

The WebFont Provider integrates CSS `@font-face` rules extracted from SVG documents into the font resolution system. It enables the conversion pipeline to use custom web fonts declared in `<style>` elements when rendering text content.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        SVG Document                             │
│  <style>                                                        │
│    @font-face {                                                 │
│      font-family: 'CustomFont';                                 │
│      src: url('font.woff2') format('woff2');                    │
│    }                                                            │
│  </style>                                                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SVGParser                                   │
│  - CSSFontFaceParser.parse_stylesheets()                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ParseResult                                 │
│  .web_fonts: list[FontFaceRule]                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│         convert_parser_output() → _hydrate_services_from_parser()│
│  - Creates WebFontProvider(web_fonts)                           │
│  - Registers with FontService via prepend_provider()            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FontService                                 │
│  Provider chain (queried in order):                             │
│    1. WebFontProvider  ← Document-specific fonts (priority)     │
│    2. DirectoryFontProvider ← System fonts (fallback)           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                 IRConverter / TextPipeline                      │
│  - font_service.find_font(query)                                │
│  - Returns FontMatch from WebFontProvider or fallback           │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. WebFontProvider

**File**: `src/svg2ooxml/services/fonts/providers/webfont.py`

**Purpose**: Implements the `FontProvider` protocol to resolve font queries against `@font-face` rules parsed from SVG.

**Key Responsibilities**:
- Index `FontFaceRule` objects by normalized family name
- Match font queries based on family, weight, and style
- Score matches for best-fit selection
- Return `FontMatch` objects with metadata

**Architecture**:
```python
@dataclass
class WebFontProvider(FontProvider):
    rules: tuple[FontFaceRule, ...]  # Immutable font declarations

    def __post_init__(self):
        # Build index: family.lower() → list[FontFaceRule]
        self._index: dict[str, list[FontFaceRule]] = {}

    def resolve(self, query: FontQuery) -> FontMatch | None:
        # Return best match or None

    def list_alternatives(self, query: FontQuery) -> Iterable[FontMatch]:
        # Yield all compatible matches, sorted by score
```

#### Font Matching Algorithm

**Resolution Steps**:
1. **Family Matching**
   - Case-insensitive lookup
   - Strip quotes from family name
   - Return None if no family match

2. **Scoring**
   - Base score: +0.1 (for family match)
   - Exact weight match: +1.0
   - Compatible weight category: +0.5
   - Exact style match: +0.5
   - Compatible style: +0.3
   - Web-compatible format: +0.3

3. **Best Match Selection**
   - Return rule with highest score
   - Use first `src` in fallback chain (highest priority)

**Weight Categories**:
- **Normal category**: < 600 (100-500)
- **Bold category**: >= 600 (600-900)

Compatible if both in same category.

**Style Matching**:
- Exact match: `normal == normal`, `italic == italic`
- Compatible: `normal` with non-italic/oblique

**Format Compatibility**:
Web-compatible formats: `woff`, `woff2`, `truetype`, `opentype`

#### FontMatch Construction

**Metadata Included**:
```python
{
    "source": "webfont",
    "format": "woff2",           # Format hint from src
    "font_display": "swap",      # CSS font-display value
    "unicode_range": "U+0000-00FF",  # Unicode coverage
    "src_count": 3,              # Number of src fallbacks
    "is_data_uri": False,        # Is embedded data URI?
    "is_remote": True,           # Is remote HTTPS URL?
    "is_local": False,           # Is local() font reference?
}
```

**Embedding Permission**:
- **Allowed**: Data URIs, remote URLs
- **Disallowed**: `local()` font references (system fonts)

### 2. FontService Enhancements

**File**: `src/svg2ooxml/services/fonts/service.py`

**New Methods**:

#### `prepend_provider(provider: FontProvider)`
```python
def prepend_provider(self, provider: FontProvider) -> None:
    """Add a provider to the front of the resolution chain (highest priority).

    Use this for document-specific fonts that should override system fonts.
    """
    if provider in self._providers:
        return
    self._providers.insert(0, provider)
```

**Why Prepend?**
- Web fonts are document-specific
- Should override system fonts with same family name
- Example: Document's "Roboto" should take precedence over system Roboto

#### `clone() -> FontService`
```python
def clone(self) -> "FontService":
    """Create a shallow clone with the same providers but empty cache.

    Used for per-parse isolation to prevent cache pollution across documents.
    """
    cloned = FontService()
    cloned._providers = list(self._providers)  # Shallow copy
    return cloned
```

**Why Clone?**
- Each document may have different web fonts
- Prevents cache pollution between documents
- Maintains provider list (system fonts) across parses

### 3. Integration Point

**File**: `src/svg2ooxml/ir/entrypoints.py`

**Function**: `_hydrate_services_from_parser()`

**Integration Flow**:
```python
def _hydrate_services_from_parser(
    services: ConversionServices,
    parser_result: ParseResult,
    logger: logging.Logger | None = None,
) -> None:
    """Ensure DI services pick up parser-collected definitions."""

    # Existing: Register filters, markers, symbols
    # ...

    # NEW: Register web fonts
    if parser_result.web_fonts:
        font_service = services.resolve("font")
        if font_service is not None:
            try:
                from svg2ooxml.services.fonts.providers.webfont import WebFontProvider
                provider = WebFontProvider(tuple(parser_result.web_fonts))
                font_service.prepend_provider(provider)  # Priority!
                if logger:
                    logger.debug(
                        "Registered WebFontProvider with %d font face(s)",
                        len(parser_result.web_fonts)
                    )
            except Exception as exc:
                if logger:
                    logger.warning("Failed to register web fonts: %s", exc)
```

**Why This Location?**
1. Called before IR conversion begins
2. Already responsible for flowing parser data into services
3. Consistent with existing patterns (filters, markers, symbols)
4. Has access to both `ParseResult` and `ConversionServices`
5. Defensive error handling built-in

**Architectural Benefits**:
- ✅ No tight coupling between parser and FontService
- ✅ Uses dependency injection container
- ✅ Per-parse isolation maintained
- ✅ Follows existing service hydration pattern
- ✅ Defensive programming (try/except, optional logging)

## Usage Examples

### Basic Web Font Resolution

```python
from svg2ooxml.core.parser import SVGParser
from svg2ooxml.ir import convert_parser_output
from svg2ooxml.services.fonts import FontQuery

# Parse SVG with @font-face
svg = """
<svg xmlns="http://www.w3.org/2000/svg">
  <style>
    @font-face {
      font-family: 'CustomFont';
      src: url('custom.woff2') format('woff2');
      font-weight: 700;
    }
  </style>
  <text font-family="CustomFont" font-weight="700">Hello</text>
</svg>
"""

# Parse
parser = SVGParser()
parse_result = parser.parse(svg)

# Web fonts are in ParseResult
print(f"Found {len(parse_result.web_fonts)} web fonts")

# Convert to IR (web fonts automatically registered)
ir_scene = convert_parser_output(parse_result)

# Font service now has WebFontProvider registered
font_service = ir_scene.services.resolve("font")
match = font_service.find_font(FontQuery(family="CustomFont", weight=700))

print(f"Resolved: {match.family}")
print(f"Source: {match.found_via}")  # "webfont"
print(f"Path: {match.path}")         # "custom.woff2"
```

### Provider Priority

```python
# Web fonts take priority over system fonts
svg = """
<svg xmlns="http://www.w3.org/2000/svg">
  <style>
    @font-face {
      font-family: 'Arial';  # Override system Arial
      src: url('custom-arial.woff2');
    }
  </style>
  <text font-family="Arial">Text</text>
</svg>
"""

parse_result = parser.parse(svg)
ir_scene = convert_parser_output(parse_result)

font_service = ir_scene.services.resolve("font")
match = font_service.find_font(FontQuery(family="Arial"))

# Returns web font, not system Arial
assert match.found_via == "webfont"
assert match.path == "custom-arial.woff2"
```

### Fallback to System Fonts

```python
# If web font not found, falls back to system fonts
svg = """
<svg xmlns="http://www.w3.org/2000/svg">
  <style>
    @font-face {
      font-family: 'CustomFont';
      src: url('custom.woff2');
    }
  </style>
  <text font-family="Arial">Text</text>  # Arial not in web fonts
</svg>
"""

parse_result = parser.parse(svg)
ir_scene = convert_parser_output(parse_result)

font_service = ir_scene.services.resolve("font")
match = font_service.find_font(FontQuery(family="Arial"))

# Falls back to DirectoryFontProvider (system fonts)
assert match.found_via == "directory"
```

### Weight and Style Matching

```python
svg = """
<svg xmlns="http://www.w3.org/2000/svg">
  <style>
    @font-face {
      font-family: 'Roboto';
      src: url('roboto-400.woff2');
      font-weight: 400;
      font-style: normal;
    }
    @font-face {
      font-family: 'Roboto';
      src: url('roboto-700-italic.woff2');
      font-weight: 700;
      font-style: italic;
    }
  </style>
</svg>
"""

parse_result = parser.parse(svg)
ir_scene = convert_parser_output(parse_result)

font_service = ir_scene.services.resolve("font")

# Exact match for 400 normal
match = font_service.find_font(FontQuery(family="Roboto", weight=400, style="normal"))
assert "roboto-400" in match.path

# Exact match for 700 italic
match = font_service.find_font(FontQuery(family="Roboto", weight=700, style="italic"))
assert "roboto-700-italic" in match.path

# Request 300 (light) → falls back to 400 (same category)
match = font_service.find_font(FontQuery(family="Roboto", weight=300))
assert "roboto-400" in match.path
```

## Testing

### Unit Tests

**File**: `tests/unit/services/fonts/test_webfont_provider.py`

**Coverage** (23 tests):
- ✅ Exact family/weight/style matching
- ✅ Case-insensitive family matching
- ✅ Quote stripping from family names
- ✅ Weight category fallback (bold vs normal)
- ✅ Style matching and fallback
- ✅ Multiple src fallback chains
- ✅ Data URI, remote URL, local font handling
- ✅ Metadata preservation
- ✅ Scoring algorithm correctness
- ✅ list_alternatives() priority ordering
- ✅ Empty rules edge case
- ✅ Provider indexing

**Running Tests**:
```bash
source .venv/bin/activate
python -m pytest tests/unit/services/fonts/test_webfont_provider.py -v
```

All 23 tests passing ✅

### Type Checking

```bash
mypy src/svg2ooxml/services/fonts/providers/webfont.py --strict
mypy src/svg2ooxml/services/fonts/service.py --strict
mypy src/svg2ooxml/ir/entrypoints.py --strict
```

All type checks passing ✅

## Performance Considerations

### Indexing

- **Time Complexity**: O(n) during `__post_init__()` where n = number of rules
- **Space Complexity**: O(n) for index dictionary
- **Lookup**: O(1) average case for family lookup (hash table)

### Scoring

- **Time Complexity**: O(m) where m = number of rules for a family
- **Optimization**: Early return on exact matches
- **Caching**: FontService caches results at FontQuery level

### Memory

- **FontFaceRule**: Lightweight dataclass (~200 bytes per rule)
- **Data URIs**: Can be large (kilobytes for embedded fonts)
- **Mitigation**: Rules stored as tuple (immutable, shareable)

## Architectural Patterns

### Dependency Injection

- ✅ WebFontProvider registered via services container
- ✅ No direct imports in conversion code
- ✅ Testable without full integration

### Provider Chain Pattern

- ✅ Multiple providers queried in sequence
- ✅ First match wins (fail-fast)
- ✅ Priority via prepend vs append

### Immutability

- ✅ `rules` is tuple (immutable)
- ✅ `FontFaceRule` and `FontFaceSrc` are frozen dataclasses
- ✅ Thread-safe after construction

### Defensive Programming

- ✅ Try/except around provider registration
- ✅ None checks before service resolution
- ✅ Optional logger (no hard dependency)
- ✅ Duplicate provider check

### Per-Parse Isolation

- ✅ FontService.clone() creates fresh cache
- ✅ WebFontProvider registered per-document
- ✅ No global state pollution

## Limitations and Future Work

### Current Limitations

1. **No Font Loading**
   - WebFontProvider returns URLs, doesn't download fonts
   - Phase 2-3 will add font loading and decompression

2. **No WOFF/WOFF2 Decompression**
   - Data URIs are stored as-is
   - Phase 2 will add brotli/gzip decompression

3. **No Variable Fonts**
   - Doesn't parse `font-variation-settings`
   - Doesn't handle weight ranges (`100 900`)

4. **No @import Support**
   - External stylesheets not loaded
   - Only inline `<style>` elements processed

### Planned Enhancements

**Phase 2-3: Font Loading**
- HTTP fetcher for remote URLs
- Base64 decoder for data URIs
- WOFF/WOFF2 decompression (brotli, gzip)
- TTF/OTF parsing

**Phase 5: Rendering Integration**
- Glyph extraction for OOXML
- Text measurement with custom fonts
- Font subsetting for file size optimization

**Future**:
- Variable font support
- @import stylesheet loading
- Font feature settings (`font-feature-settings`)
- Font variation settings (`font-variation-settings`)

## Troubleshooting

### Web Fonts Not Resolving

**Symptom**: `find_font()` returns system font instead of web font

**Diagnosis**:
```python
font_service = services.resolve("font")
providers = list(font_service.iter_providers())
print(f"Provider count: {len(providers)}")
for i, provider in enumerate(providers):
    print(f"{i}: {provider.__class__.__name__}")
```

**Expected Output**:
```
Provider count: 2
0: WebFontProvider
1: DirectoryFontProvider
```

**Fix**:
- Ensure `parse_result.web_fonts` is not empty
- Check logger output for "Registered WebFontProvider" message
- Verify `_hydrate_services_from_parser()` is called

### Wrong Font Matched

**Symptom**: Query matches unexpected font variant

**Diagnosis**:
```python
# Use list_alternatives to see scoring
alternatives = list(font_service.iter_alternatives(query))
for alt in alternatives:
    print(f"{alt.family} {alt.weight} {alt.style} - score: {alt.score}")
```

**Fix**:
- Verify @font-face descriptors (weight, style) are correct
- Check if multiple rules have same family name
- Review scoring algorithm in WebFontProvider

### Import Errors

**Symptom**: `ImportError: cannot import name 'WebFontProvider'`

**Diagnosis**:
```bash
python tools/rebuild_inits.py --root src/svg2ooxml
```

**Fix**:
- Rebuild auto-generated `__init__.py` files
- Verify module is in correct location
- Check for circular import issues

## References

- [CSS Fonts Module Level 3](https://www.w3.org/TR/css-fonts-3/)
- [FontProvider Protocol](../src/svg2ooxml/services/fonts/service.py)
- [CSS Font Parsing Architecture](./css-font-parsing.md)
- [Service Container Architecture](../src/svg2ooxml/services/README.md)

## Summary

The WebFont Provider architecture cleanly integrates CSS `@font-face` rules into the font resolution system by:

1. **Parsing**: CSS parser extracts rules into `FontFaceRule` IR
2. **Storage**: ParseResult carries web fonts to conversion phase
3. **Registration**: `_hydrate_services_from_parser()` creates WebFontProvider and registers with FontService
4. **Resolution**: FontService queries WebFontProvider first (priority), falls back to system fonts
5. **Isolation**: Per-document providers via FontService.clone()

This design maintains loose coupling, follows existing architectural patterns, and enables future font loading features while providing robust font matching today.
