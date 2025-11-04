# Web Font Support Specification

**Feature**: SVG Web Font Loading and Embedding
**Priority**: High
**Status**: Planning
**Created**: 2025-11-03
**Owner**: TBD

---

## 1. Overview

### 1.1 Problem Statement

Modern SVG files from design tools (Figma, Sketch, Adobe XD) and web exports commonly use web fonts via CSS `@font-face` rules with WOFF/WOFF2 format. Currently, svg2ooxml cannot:

1. Parse `@font-face` CSS rules
2. Load WOFF/WOFF2 font files
3. Decode base64 data URLs for fonts
4. Automatically fetch remote font resources

This results in:
- Missing fonts in PowerPoint output
- Fallback to system fonts (Arial, Times New Roman)
- Loss of design fidelity

### 1.2 Success Criteria

**Must Have**:
- ✅ Parse `@font-face` rules from `<style>` tags
- ✅ Decompress WOFF/WOFF2 to TTF/OTF
- ✅ Decode base64 font data URLs
- ✅ Fetch remote font URLs (http/https)
- ✅ Cache downloaded fonts
- ✅ Integrate with existing font embedding pipeline

**Should Have**:
- ✅ Support font-display strategies
- ✅ Handle multiple `src` descriptors (fallback chain)
- ✅ Validate font format before loading
- ✅ Report font loading errors

**Nice to Have**:
- CORS handling for cross-origin fonts
- Font subsetting optimization for web fonts
- Font preloading hints

### 1.3 Non-Goals

- ❌ Custom font shaping engines (use existing fontTools)
- ❌ Font format conversion beyond WOFF→TTF
- ❌ Dynamic font loading during PowerPoint playback
- ❌ Font licensing validation (user responsibility)

---

## 2. Technical Design

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     SVG Input                               │
│  <style>                                                    │
│    @font-face {                                             │
│      font-family: 'CustomFont';                             │
│      src: url('font.woff2') format('woff2'),                │
│           url('data:font/woff;base64,...') format('woff');  │
│    }                                                        │
│  </style>                                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              CSS Parser Enhancement                         │
│  - Parse @font-face at-rules                                │
│  - Extract font-family, src, format, descriptors            │
│  → FontFaceRule IR                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Font Loader Service                            │
│  - Process src URLs (remote, data, local)                   │
│  - Decompress WOFF/WOFF2 → TTF/OTF                          │
│  - Cache fonts by URL hash                                  │
│  → Font file bytes                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│         Font Registry & Resolution                          │
│  - Register loaded fonts by family name                     │
│  - Match font requests against registry                     │
│  - Fallback to system fonts if not found                    │
│  → Resolved font path                                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│         Existing Font Embedding Pipeline                    │
│  - Subset font via fontTools                                │
│  - Embed in PPTX (ppt/fonts/*.odttf)                        │
│  - Create relationships                                     │
│  → Embedded font in PowerPoint                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Component Design

#### 2.2.1 CSS Parser Enhancement

**Location**: `src/svg2ooxml/core/parser/css_parser.py` (new)

**Responsibilities**:
- Parse CSS `@font-face` at-rules from `<style>` elements
- Extract `font-family`, `src`, `font-weight`, `font-style`, `unicode-range`
- Handle multiple `src` descriptors with format hints
- Validate CSS syntax

**Data Structures**:

```python
@dataclass
class FontFaceSrc:
    """Single src descriptor from @font-face."""
    url: str                    # URL or data URI
    format: str | None          # 'woff', 'woff2', 'truetype', 'opentype'
    tech: str | None            # Font technology hint (SVG2)

@dataclass
class FontFaceRule:
    """Parsed @font-face rule."""
    family: str                 # font-family value
    src: list[FontFaceSrc]      # src descriptors (ordered)
    weight: str = "normal"      # font-weight descriptor
    style: str = "normal"       # font-style descriptor
    display: str = "auto"       # font-display strategy
    unicode_range: str | None = None
```

**Key Methods**:

```python
class CSSFontFaceParser:
    def parse_stylesheets(self, svg_root: Element) -> list[FontFaceRule]:
        """Extract all @font-face rules from <style> elements."""

    def parse_font_face_rule(self, rule_text: str) -> FontFaceRule:
        """Parse a single @font-face { ... } block."""

    def parse_src_descriptor(self, src_value: str) -> list[FontFaceSrc]:
        """Parse src: url(...) format(...), ... descriptor."""
```

**Dependencies**:
- `tinycss2` - CSS parsing library (already used)
- `lxml` - DOM traversal (already used)

#### 2.2.2 Font Loader Service

**Location**: `src/svg2ooxml/services/fonts/web_loader.py` (new)

**Responsibilities**:
- Load fonts from various sources (remote URL, data URI, file path)
- Decompress WOFF/WOFF2 formats to TTF/OTF
- Cache downloaded fonts
- Validate font format
- Handle errors gracefully

**Key Methods**:

```python
class WebFontLoader:
    def __init__(self, cache_dir: Path | None = None):
        self._cache_dir = cache_dir or Path.home() / ".svg2ooxml" / "fonts"
        self._session = requests.Session()  # For HTTP requests

    def load_font(self, src: FontFaceSrc) -> FontLoadResult:
        """Load font from src descriptor, return TTF/OTF bytes."""
        if src.url.startswith("data:"):
            return self._load_data_uri(src.url)
        elif src.url.startswith(("http://", "https://")):
            return self._load_remote(src.url, src.format)
        else:
            return self._load_file(src.url)

    def _load_data_uri(self, uri: str) -> FontLoadResult:
        """Decode base64 data URI."""
        # data:font/woff2;base64,... → bytes

    def _load_remote(self, url: str, format_hint: str | None) -> FontLoadResult:
        """Download font from URL with caching."""
        # Check cache by URL hash
        # Download if not cached
        # Decompress WOFF/WOFF2 if needed
        # Save to cache

    def _decompress_woff(self, woff_bytes: bytes) -> bytes:
        """Decompress WOFF to TTF."""
        # Use fontTools.ttLib.woff to decompress

    def _decompress_woff2(self, woff2_bytes: bytes) -> bytes:
        """Decompress WOFF2 to TTF."""
        # Use brotli + fontTools for WOFF2
```

**Data Structures**:

```python
@dataclass
class FontLoadResult:
    """Result of loading a font."""
    success: bool
    font_bytes: bytes | None    # TTF/OTF bytes
    format: str | None           # Detected format
    error: str | None            # Error message if failed
    cached: bool = False         # Whether loaded from cache
```

**Dependencies**:
- `fontTools` - WOFF decompression (already used)
- `brotli` - WOFF2 decompression (new dependency)
- `requests` - HTTP downloads (already used in fetcher.py)

#### 2.2.3 Font Registry

**Location**: `src/svg2ooxml/services/fonts/registry.py` (new)

**Responsibilities**:
- Register loaded web fonts by family name
- Match font requests against registered fonts
- Handle font-weight/font-style matching
- Provide fallback to system fonts

**Key Methods**:

```python
class WebFontRegistry:
    def __init__(self):
        self._fonts: dict[str, list[RegisteredFont]] = {}
        # Key: normalized family name, Value: list of font variants

    def register_font_face(self, rule: FontFaceRule, font_path: Path):
        """Register a loaded web font."""
        # Normalize family name (lowercase, strip quotes)
        # Store font path with weight/style metadata

    def resolve_font(self, query: FontQuery) -> Path | None:
        """Find best matching font for query."""
        # Match family name (exact or fallback)
        # Match weight/style
        # Return font file path or None

    def get_registered_families(self) -> list[str]:
        """List all registered font families."""
```

**Data Structures**:

```python
@dataclass
class RegisteredFont:
    """A registered web font variant."""
    family: str
    weight: str
    style: str
    path: Path
    source: str  # "web-font", "system", "embedded"
```

#### 2.2.4 Integration Points

**Parser Integration** (`src/svg2ooxml/core/parser/svg_parser.py`):

```python
class SVGParser:
    def parse(self, svg_text: str, ...) -> ParseResult:
        # ... existing parsing ...

        # NEW: Parse @font-face rules
        if self._config.load_web_fonts:
            font_rules = self._css_parser.parse_stylesheets(root)
            for rule in font_rules:
                self._load_and_register_font(rule)

        # ... rest of parsing ...
```

**StyleResolver Integration** (`src/svg2ooxml/common/style/resolver.py`):

```python
class StyleResolver:
    def __init__(self, ..., font_registry: WebFontRegistry | None = None):
        self._font_registry = font_registry

    def compute_text_style(self, element, ...) -> dict:
        # ... existing style computation ...

        # NEW: Check web font registry before system fonts
        if self._font_registry:
            font_path = self._font_registry.resolve_font(query)
            if font_path:
                style["font_path"] = font_path
```

**Font Service Integration** (`src/svg2ooxml/services/fonts/service.py`):

```python
class FontService:
    def __init__(self, ..., web_loader: WebFontLoader | None = None):
        self._web_loader = web_loader

    def resolve_font_query(self, query: FontQuery) -> FontResolution:
        # 1. Check web font registry (NEW)
        # 2. Check system font directories (existing)
        # 3. Return fallback (existing)
```

### 2.3 Data Flow

#### Scenario: SVG with @font-face and WOFF2

**Input SVG**:
```xml
<svg xmlns="http://www.w3.org/2000/svg">
  <style>
    @font-face {
      font-family: 'Roboto';
      src: url('https://fonts.gstatic.com/s/roboto/v30/KFOmCnqEu92Fr1Me5WZLCzYlKw.woff2') format('woff2');
      font-weight: 400;
      font-style: normal;
    }
  </style>
  <text font-family="Roboto" font-size="24">Hello World</text>
</svg>
```

**Processing Steps**:

1. **Parse SVG** → `ParseResult` with `svg_root`
2. **Parse CSS** → `FontFaceRule(family='Roboto', src=[FontFaceSrc(url='https://...', format='woff2')])`
3. **Load Font**:
   - Check cache: `~/.svg2ooxml/fonts/abc123.woff2`
   - If not cached: Download from URL
   - Decompress WOFF2 → TTF bytes
   - Save to cache: `~/.svg2ooxml/fonts/abc123.ttf`
4. **Register Font** → `WebFontRegistry.register_font_face('Roboto', weight=400, style=normal, path=...)`
5. **Convert Text**:
   - `TextConverter` extracts `<text>` with `font-family="Roboto"`
   - `StyleResolver.compute_text_style()` queries registry
   - Registry returns cached TTF path
6. **Embed Font**:
   - Existing `FontEmbeddingEngine` subsets font
   - Existing PPTX packager embeds in `ppt/fonts/`

**Output**: PowerPoint with Roboto font embedded

---

## 3. Implementation Plan

### 3.1 Phase 1: CSS Parser (Week 1-2)

**Tasks**:

1. **Create CSS Parser Module**
   - File: `src/svg2ooxml/core/parser/css_parser.py`
   - Implement `CSSFontFaceParser` class
   - Parse `@font-face` rules using tinycss2
   - Extract `font-family`, `src`, `weight`, `style`
   - Handle multiple `src` descriptors
   - Unit tests: 20+ test cases

2. **Define IR Data Structures**
   - File: `src/svg2ooxml/ir/fonts.py` (new)
   - `FontFaceRule` dataclass
   - `FontFaceSrc` dataclass
   - Validation logic

3. **Integrate with SVGParser**
   - File: `src/svg2ooxml/core/parser/svg_parser.py`
   - Add `load_web_fonts` config option
   - Call CSS parser during parse phase
   - Store rules in `ParseResult.web_fonts`

**Deliverables**:
- ✅ CSS parser with full @font-face support
- ✅ 20+ unit tests
- ✅ Integration with SVGParser
- ✅ Documentation

**Success Metrics**:
- All test cases pass
- Can parse complex @font-face with multiple sources
- No performance regression (< 5% slowdown)

### 3.2 Phase 2: WOFF/WOFF2 Decompression (Week 3)

**Tasks**:

1. **Add Brotli Dependency**
   - Update `pyproject.toml` with `brotli` package
   - Add to optional dependencies `[fonts]` group
   - Update CI to install `[fonts]` extras

2. **Implement WOFF Decompression**
   - File: `src/svg2ooxml/services/fonts/decompressor.py` (new)
   - Use `fontTools.ttLib.woff.decompress` for WOFF
   - Handle decompression errors gracefully

3. **Implement WOFF2 Decompression**
   - Same file as above
   - Use `fontTools.ttLib.woff2` + `brotli`
   - Validate output is valid TTF/OTF

4. **Unit Tests**
   - Test WOFF → TTF conversion
   - Test WOFF2 → TTF conversion
   - Test error handling (corrupted files)
   - Test format detection

**Deliverables**:
- ✅ WOFF/WOFF2 decompressor
- ✅ 10+ unit tests
- ✅ Error handling
- ✅ Performance benchmarks

**Success Metrics**:
- Successfully decompress real-world WOFF/WOFF2 files
- < 100ms decompression time for typical web fonts
- Graceful error handling for corrupted files

### 3.3 Phase 3: Font Loader Service (Week 4)

**Tasks**:

1. **Create WebFontLoader**
   - File: `src/svg2ooxml/services/fonts/web_loader.py`
   - Implement data URI decoding (base64)
   - Implement remote URL downloading
   - Implement file path loading
   - Add caching by URL hash

2. **Implement Caching**
   - Cache directory: `~/.svg2ooxml/fonts/` or custom
   - Hash URLs to create cache keys
   - Store metadata (URL, format, timestamp)
   - Implement cache eviction (LRU, age-based)

3. **Add Configuration**
   - File: `src/svg2ooxml/config/fonts.py` (new)
   - `WebFontConfig` dataclass
   - `cache_dir`, `max_cache_size`, `ttl`
   - Environment variables support

**Deliverables**:
- ✅ WebFontLoader with all sources
- ✅ Caching system
- ✅ Configuration system
- ✅ 15+ unit tests

**Success Metrics**:
- Load fonts from all source types
- Cache hit rate > 90% for repeated loads
- < 200ms total load time for cached fonts

### 3.4 Phase 4: Font Registry (Week 5)

**Tasks**:

1. **Create WebFontRegistry**
   - File: `src/svg2ooxml/services/fonts/registry.py`
   - Implement font registration
   - Implement font resolution with weight/style matching
   - Handle family name normalization

2. **Integrate with FontService**
   - File: `src/svg2ooxml/services/fonts/service.py`
   - Add web font registry as first lookup
   - Fallback to system fonts if not found
   - Update `FontQuery` to support web fonts

3. **Update StyleResolver**
   - File: `src/svg2ooxml/common/style/resolver.py`
   - Inject `WebFontRegistry` reference
   - Query registry during style resolution

**Deliverables**:
- ✅ WebFontRegistry
- ✅ FontService integration
- ✅ StyleResolver integration
- ✅ 10+ unit tests

**Success Metrics**:
- Correct font matching (family + weight + style)
- Fallback to system fonts works
- No breaking changes to existing code

### 3.5 Phase 5: End-to-End Integration (Week 6)

**Tasks**:

1. **Integration Testing**
   - Create SVG fixtures with @font-face
   - Test with WOFF, WOFF2, data URIs
   - Test with remote URLs (Google Fonts)
   - Verify font embedding in PPTX output

2. **Performance Testing**
   - Benchmark full pipeline with web fonts
   - Measure cache performance
   - Profile memory usage
   - Optimize bottlenecks

3. **Documentation**
   - User guide: How to use web fonts
   - Configuration reference
   - Troubleshooting guide
   - API documentation

4. **Error Handling**
   - Handle network errors gracefully
   - Handle invalid font files
   - Handle missing fonts
   - Provide helpful error messages

**Deliverables**:
- ✅ 10+ integration tests
- ✅ Performance benchmarks
- ✅ Complete documentation
- ✅ Error handling guide

**Success Metrics**:
- 100% of integration tests pass
- < 10% performance regression vs. baseline
- < 50MB memory overhead for typical workloads
- Clear error messages for all failure modes

---

## 4. Testing Strategy

### 4.1 Unit Tests

**CSS Parser Tests** (20+ tests):
- Parse simple @font-face rule
- Parse multiple @font-face rules
- Parse src with multiple URLs
- Parse src with format hints
- Parse font-weight descriptors
- Parse font-style descriptors
- Parse unicode-range
- Handle malformed CSS gracefully
- Handle empty @font-face
- Handle missing required descriptors

**WOFF Decompressor Tests** (10+ tests):
- Decompress valid WOFF file
- Decompress valid WOFF2 file
- Detect format from magic bytes
- Handle corrupted WOFF
- Handle corrupted WOFF2
- Verify TTF output is valid
- Test various font files (Google Fonts samples)

**WebFontLoader Tests** (15+ tests):
- Load from data URI (base64)
- Load from remote URL (mocked)
- Load from file path
- Cache downloaded fonts
- Reuse cached fonts
- Handle network errors
- Handle invalid URLs
- Handle invalid base64
- Handle unsupported formats
- Test cache eviction

**WebFontRegistry Tests** (10+ tests):
- Register single font
- Register multiple weights
- Register multiple styles
- Resolve by family name
- Resolve with weight/style matching
- Fallback when not found
- Handle duplicate registrations
- Case-insensitive matching
- Normalize family names (strip quotes)

### 4.2 Integration Tests

**End-to-End Tests** (10+ tests):
1. SVG with WOFF font → PPTX with embedded font
2. SVG with WOFF2 font → PPTX with embedded font
3. SVG with data URI font → PPTX with embedded font
4. SVG with remote Google Font → PPTX with embedded font
5. SVG with multiple font weights → PPTX with all variants
6. SVG with fallback src chain → Uses first valid font
7. SVG with missing font → Falls back to system font
8. SVG with invalid @font-face → Skips and continues
9. Multiple SVG conversions → Cache is reused
10. Large SVG with many fonts → Performance acceptable

### 4.3 Performance Tests

**Benchmarks**:
- Baseline: Current svg2ooxml without web fonts
- With web fonts (cache hit): < 5% overhead
- With web fonts (cache miss): < 200ms additional latency
- Memory: < 50MB additional for 10 fonts
- Cache: 100MB for 50 fonts, LRU eviction works

### 4.4 Manual Testing

**Test Cases**:
1. Export SVG from Figma with custom fonts
2. Export SVG from Sketch with custom fonts
3. Use Google Fonts in SVG
4. Use Adobe Fonts in SVG
5. Use variable fonts (should gracefully ignore)
6. Test on macOS, Linux, Windows
7. Test with/without internet connection
8. Test cache directory permissions

---

## 5. Configuration & API

### 5.1 Configuration Options

**Parser Config** (`ParserConfig`):
```python
@dataclass
class ParserConfig:
    # ... existing fields ...

    # Web font loading
    load_web_fonts: bool = True
    web_font_cache_dir: Path | None = None
    web_font_max_size: int = 10 * 1024 * 1024  # 10MB limit
    web_font_timeout: int = 10  # seconds
    web_font_allow_remote: bool = True
```

**Environment Variables**:
```bash
SVG2OOXML_WEB_FONT_CACHE=/path/to/cache
SVG2OOXML_WEB_FONT_TIMEOUT=30
SVG2OOXML_WEB_FONT_ALLOW_REMOTE=false
```

### 5.2 Public API

**Converter API** (no changes, automatic):
```python
from svg2ooxml import Converter

converter = Converter()
# Web fonts automatically loaded if present
converter.convert_file("input.svg", "output.pptx")
```

**Explicit Control**:
```python
from svg2ooxml.core.parser import ParserConfig

config = ParserConfig(
    load_web_fonts=True,
    web_font_cache_dir=Path("/tmp/fonts"),
    web_font_allow_remote=False  # Only data URIs
)

converter = Converter(parser_config=config)
converter.convert_file("input.svg", "output.pptx")
```

**Registry Access** (advanced):
```python
from svg2ooxml.services.fonts.registry import WebFontRegistry

registry = WebFontRegistry()
# Pre-load fonts manually
registry.register_font_face(rule, font_path)

# Use in conversion
converter = Converter(font_registry=registry)
```

---

## 6. Dependencies

### 6.1 New Dependencies

**Required**:
- `brotli` >= 1.0.0 - WOFF2 decompression

**Optional** (already available):
- `requests` - HTTP downloads (already used)
- `fontTools` >= 4.0.0 - Font manipulation (already used)
- `tinycss2` - CSS parsing (already used)

### 6.2 Package Changes

**pyproject.toml**:
```toml
[project.optional-dependencies]
fonts = [
    "brotli>=1.0.0",
    "fontTools>=4.0.0",
]
```

**Installation**:
```bash
pip install svg2ooxml[fonts]
```

---

## 7. Error Handling

### 7.1 Error Scenarios

| Scenario | Behavior | User Message |
|----------|----------|--------------|
| Invalid @font-face CSS | Skip rule, warn | "Skipping invalid @font-face rule: {reason}" |
| Network timeout | Fallback to system font | "Failed to download font '{url}': timeout" |
| Invalid WOFF file | Fallback to system font | "Failed to decompress font '{url}': invalid format" |
| Missing brotli package | Disable WOFF2, warn | "WOFF2 support requires 'brotli' package" |
| Cache permission error | Disable cache, warn | "Cannot write to font cache: {path}" |
| Font too large | Skip, warn | "Font '{url}' exceeds size limit (10MB)" |

### 7.2 Logging

**Log Levels**:
- `DEBUG`: Font loading details, cache hits/misses
- `INFO`: Successful font loads, cache stats
- `WARNING`: Fallbacks, skipped fonts, recoverable errors
- `ERROR`: Critical failures (should be rare with fallbacks)

**Example Logs**:
```
INFO: Loaded web font 'Roboto' (WOFF2) from cache
DEBUG: Font cache hit: https://fonts.gstatic.com/.../roboto.woff2
WARNING: Failed to load font 'CustomFont', falling back to Arial
ERROR: CSS parsing failed for <style> element, skipping web fonts
```

---

## 8. Migration & Compatibility

### 8.1 Backward Compatibility

**Guaranteed**:
- ✅ Existing code continues to work without changes
- ✅ Web fonts are opt-in via `load_web_fonts` config (default: enabled)
- ✅ System font fallback always available
- ✅ No breaking changes to public API

**Opt-Out**:
```python
config = ParserConfig(load_web_fonts=False)
converter = Converter(parser_config=config)
```

### 8.2 Migration Path

**For Users**:
1. Upgrade to new version: `pip install --upgrade svg2ooxml[fonts]`
2. Install `brotli` if using WOFF2: `pip install brotli`
3. (Optional) Configure cache directory
4. Existing SVG conversions automatically use web fonts

**For Developers**:
1. No code changes required
2. Web fonts loaded automatically if `@font-face` present
3. Access registry if advanced control needed

---

## 9. Security Considerations

### 9.1 Threats

| Threat | Mitigation |
|--------|-----------|
| Malicious font files | Validate format, use fontTools (trusted library) |
| SSRF via remote URLs | Restrict to http/https, no file:// or internal IPs |
| DoS via large fonts | Size limit (10MB default), timeout (10s default) |
| XSS via CSS injection | Use tinycss2 (trusted parser), no eval() |
| Path traversal in cache | Hash URLs, sanitize cache filenames |
| Disk space exhaustion | Cache size limit, LRU eviction |

### 9.2 Best Practices

1. **Input Validation**: Validate all URLs, format hints, base64 data
2. **Resource Limits**: Enforce size/timeout limits
3. **Sandboxing**: Use fontTools/tinycss2 (no subprocess calls)
4. **Error Handling**: Never expose internal paths in errors
5. **Logging**: Sanitize URLs before logging (no auth tokens)

---

## 10. Performance Targets

### 10.1 Latency

| Operation | Target | Acceptable |
|-----------|--------|-----------|
| Parse @font-face (10 rules) | < 10ms | < 50ms |
| Decompress WOFF | < 50ms | < 200ms |
| Decompress WOFF2 | < 100ms | < 500ms |
| Download font (uncached) | < 1s | < 5s |
| Load font (cached) | < 5ms | < 20ms |
| Full pipeline overhead | < 5% | < 10% |

### 10.2 Memory

| Scenario | Target | Acceptable |
|----------|--------|-----------|
| No web fonts | 0MB overhead | 0MB |
| 5 web fonts loaded | < 25MB | < 50MB |
| 20 web fonts loaded | < 50MB | < 100MB |
| Cache (50 fonts) | < 100MB disk | < 200MB |

### 10.3 Scalability

- Support 100+ @font-face rules in a single SVG
- Support 1000+ fonts in cache
- Concurrent font loading (ThreadPoolExecutor)
- Async font downloads (optional, future)

---

## 11. Documentation Requirements

### 11.1 User Documentation

**Topics**:
1. Introduction to web fonts in svg2ooxml
2. Configuration options reference
3. Troubleshooting guide (common errors)
4. Performance tuning (cache settings)
5. Security considerations (trusted sources)
6. Examples (Google Fonts, Figma, Sketch)

**Location**: `docs/user-guide/web-fonts.md`

### 11.2 API Documentation

**Topics**:
1. `ParserConfig` web font options
2. `WebFontRegistry` API reference
3. `WebFontLoader` API reference
4. Custom font loading workflows

**Location**: Auto-generated from docstrings + `docs/api/fonts.md`

### 11.3 Developer Documentation

**Topics**:
1. Architecture overview (this spec)
2. Code structure and organization
3. Testing strategy
4. Adding new font formats
5. Debugging tips

**Location**: `docs/architecture/web-fonts-impl.md`

---

## 12. Rollout Plan

### 12.1 Alpha Release (Week 7)

- Limited release to early testers
- Feature flag: `EXPERIMENTAL_WEB_FONTS=1`
- Gather feedback on API, performance
- Fix critical bugs

### 12.2 Beta Release (Week 8)

- Public beta announcement
- Enable by default (`load_web_fonts=True`)
- Comprehensive testing on real-world SVGs
- Documentation complete

### 12.3 Stable Release (Week 9)

- Mark as stable
- Include in release notes
- Blog post announcement
- Monitor for issues

---

## 13. Success Metrics

### 13.1 Technical Metrics

- ✅ 100% test coverage for new code
- ✅ < 5% performance regression
- ✅ 0 critical bugs in stable release
- ✅ < 10MB memory overhead typical case

### 13.2 User Metrics

- ✅ 90% of Figma/Sketch SVGs render correctly
- ✅ 80% of users enable web fonts (opt-in stats)
- ✅ < 5% user-reported font issues
- ✅ Positive feedback from early adopters

### 13.3 Business Metrics

- Increase design tool compatibility
- Reduce "missing font" support requests
- Differentiate from competitors
- Enable premium features (font marketplace?)

---

## 14. Future Enhancements

### 14.1 Phase 2 Features (Post-Launch)

1. **Variable Font Support**
   - Parse `font-variation-settings`
   - Extract font axes metadata
   - Instantiate static fonts from variable fonts

2. **Font Preloading**
   - Parse `<link rel="preload" as="font">`
   - Prioritize critical fonts
   - Parallel downloads

3. **Advanced Caching**
   - CDN integration (Cloudflare, Fastly)
   - Shared cache across users/projects
   - Cache warming strategies

4. **Font Marketplace**
   - Integrate with font services (Adobe Fonts, Google Fonts API)
   - License validation
   - Automatic font purchasing

5. **Font Subsetting Optimization**
   - Unicode-range-aware subsetting
   - Glyph usage analysis
   - Multi-file subsetting for large fonts

### 14.2 Integration Opportunities

- **Figma Plugin**: Direct PPTX export with web fonts
- **Sketch Plugin**: Same as above
- **Cloud Service**: Font conversion API
- **CLI Tool**: Batch font management

---

## 15. Open Questions

1. **Font Licensing**: How to handle fonts with restricted embedding permissions?
   - **Decision**: Honor OS/2 fsType, warn user, fallback to system font

2. **CORS Restrictions**: How to handle cross-origin font downloads?
   - **Decision**: Phase 1 ignores CORS, Phase 2 adds CORS support

3. **Cache Invalidation**: When to invalidate cached fonts?
   - **Decision**: TTL-based (30 days default), manual clear command

4. **Font Hinting**: Preserve hinting or drop for smaller files?
   - **Decision**: Configurable, default: preserve for quality

5. **Concurrent Downloads**: Async or threaded?
   - **Decision**: ThreadPoolExecutor (simpler), async in Phase 2

---

## 16. Appendices

### Appendix A: Example @font-face Rules

**Google Fonts**:
```css
@font-face {
  font-family: 'Roboto';
  src: url('https://fonts.gstatic.com/s/roboto/v30/KFOmCnqEu92Fr1Me5WZLCzYlKw.woff2') format('woff2');
  font-weight: 400;
  font-style: normal;
}
```

**Data URI**:
```css
@font-face {
  font-family: 'CustomFont';
  src: url('data:font/woff2;base64,d09GMgABAAAAAATcAA0AAAAAB...') format('woff2');
}
```

**Multiple Sources**:
```css
@font-face {
  font-family: 'OpenSans';
  src: local('Open Sans'),
       url('opensans.woff2') format('woff2'),
       url('opensans.woff') format('woff'),
       url('opensans.ttf') format('truetype');
}
```

### Appendix B: Font Format Magic Bytes

| Format | Magic Bytes | Description |
|--------|-------------|-------------|
| TTF | `00 01 00 00` | TrueType outline |
| OTF | `4F 54 54 4F` | OpenType with CFF |
| WOFF | `77 4F 46 46` | WOFF 1.0 |
| WOFF2 | `77 4F 46 32` | WOFF 2.0 |
| TTC | `74 74 63 66` | TrueType collection |

### Appendix C: References

- [CSS Fonts Module Level 4](https://www.w3.org/TR/css-fonts-4/)
- [WOFF File Format 1.0](https://www.w3.org/TR/WOFF/)
- [WOFF File Format 2.0](https://www.w3.org/TR/WOFF2/)
- [fontTools Documentation](https://fonttools.readthedocs.io/)
- [Brotli Compression](https://github.com/google/brotli)

---

**End of Specification**

**Next Steps**:
1. Review and approve spec
2. Create implementation tasks in issue tracker
3. Assign development team
4. Set milestone dates
5. Begin Phase 1 implementation
