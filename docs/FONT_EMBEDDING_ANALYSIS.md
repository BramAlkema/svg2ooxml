# Font Embedding in PPTX: Complete Integration Analysis

## Executive Summary

Font embedding in PPTX follows a multi-stage pipeline where fonts are discovered, resolved, embedded with optional subsetting, and finally packaged into the PPTX file structure. Web fonts (from @font-face) are loaded early and passed through FontService → FontEmbeddingEngine → TextConversionPipeline → DrawingML writer → PPTX package builder.

### 2025-11 Update Highlights

- `FontEmbeddingEngine` now emits Embedded OpenType (EOT) payloads via `src/svg2ooxml/services/fonts/eot.py`, capturing GUID/root-string metadata and style flags inside `EmbeddedFontPayload`.
- `PPTXPackageBuilder` writes `/ppt/fonts/fontN.fntdata` parts (`application/x-fontdata`), adds `<p:fontKey guid="…">`, and wires `<p:regular>/<p:bold>/<p:italic>/<p:boldItalic>` elements to the correct `relationships/font` entries instead of the legacy `.odttf` approach.
- `tests/integration/test_font_embedding_eot.py` unzips a generated PPTX to verify the `.fntdata` headers, content-types, relationships, and presentation XML.
- `tools/verify_font_embedding.py` provides a CLI for inspecting embedded fonts in any PPTX (useful for PowerPoint/Google Slides validation workflows).

---

## 1. Font Embedding Logic Location

### Core Embedding Engine
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/embedding.py`

**Key Components:**
- **FontEmbeddingEngine**: Main class handling subsetting and font optimization
  - `can_embed()`: Checks fsType flags for embedding permissions
  - `subset_font()`: Produces or reuses subsetted fonts for a glyph set
  - `_subset_with_fonttools()`: Uses fontTools library for subsetting
  - `_subset_copy()`: Copies full font when subsetting not permitted

- **FontEmbeddingRequest**: Parameters for embedding (frozen dataclass)
  - `font_path`: Path to font file
  - `glyph_ids`: Specific glyphs to include
  - `characters`: Text characters needing glyphs
  - `preserve_hinting`: Keep hinting instructions
  - `subset_strategy`: "glyph", "character", "aggressive", or "none"
  - `optimisation`: FontOptimisationLevel (NONE, BASIC, BALANCED, AGGRESSIVE)
  - `metadata`: Custom metadata dictionary

- **FontEmbeddingResult**: Output with font data (frozen dataclass)
  - `relationship_id`: PPTX relationship ID
  - `subset_path`: Path to subsetted font
  - `glyph_count`: Number of glyphs included
  - `bytes_written`: Size of embedded font
  - `permission`: EmbeddingPermission (INSTALLABLE, RESTRICTED, etc.)
  - **`packaging_metadata`**: Contains `font_data` (bytes) + request metadata

### Subsetting with fontTools
Lines 249-305 show fontTools integration:
- Uses `fontTools.subset.Subsetter`
- Configurable options for hinting, table dropping, desubroutinization
- Writes to temp file, reads as bytes, cleans up
- Returns bytes or None on failure

### Cache Layer
- `_cache`: Dict[str, FontEmbeddingResult] indexed by hash of font_path + glyphs + options
- Stats tracking: subset requests, successes, failures, cache hits, bytes

---

## 2. Font Flow: FontService → PPTX

### Stage 1: Web Font Loading (Optional)
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/loader.py`

When SVG has `@font-face` rules:
1. SVG parser extracts FontFaceRule from `<style>` tags
2. FontLoader loads from sources (in priority order):
   - Data URIs: base64 decode + gzip/brotli decompression if WOFF/WOFF2
   - Remote URLs: fetch via FontFetcher
   - Local fonts: skipped
3. Returns LoadedFont with:
   - `data`: Raw bytes (TTF/OTF after decompression)
   - `format`: Font format string
   - `source_url`: Original URL
   - `decompressed`: Whether WOFF/WOFF2 was decompressed

### Stage 2: Web Font Provider Integration
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/providers/webfont.py`

WebFontProvider resolves @font-face rules to FontMatch:
1. Indexes @font-face rules by family name
2. Scores rules by weight/style compatibility (lines 117-151)
3. Loads font data if loader available (lines 185-224)
4. **KEY: Lines 253-259** - Adds loaded font data to metadata:
   ```python
   if loaded_font:
       metadata["loaded"] = True
       metadata["font_data"] = loaded_font.data  # ← BYTES ARE STORED HERE
       metadata["decompressed"] = loaded_font.decompressed
       metadata["loaded_format"] = loaded_font.format
       metadata["loaded_size_bytes"] = loaded_font.size_bytes
   ```
5. Returns FontMatch with metadata containing `font_data`

### Stage 3: Text Pipeline Planning
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/core/ir/text_pipeline.py`

TextConversionPipeline._plan_embedding() (lines 187-270):
1. Finds font via FontService.find_font(FontQuery)
2. Collects unique glyphs from text runs
3. If font found and embedding allowed:
   ```python
   request = FontEmbeddingRequest(
       font_path=match.path,  # URL or filesystem path
       glyph_ids=tuple(sorted(glyphs)),
       metadata={
           "font_family": match.family,
           "font_source": match.found_via,
           # Web font metadata from FontMatch.metadata is here too
       }
   )
   subset_result = self._embedding.subset_font(request)
   ```
4. **KEY: Line 248** - Metadata from embedding result added to plan:
   ```python
   metadata.update(subset_result.packaging_metadata)
   ```
5. Creates EmbeddedFontPlan with metadata containing `font_data`

### Stage 4: IR to DrawingML
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/drawingml/writer.py` (lines 611-624)

Writer finds TextFrame with `embedding_plan` and registers it:
```python
if getattr(element, "embedding_plan", None) is not None:
    plan = element.embedding_plan
    if plan.requires_embedding:
        self._assets.add_font_plan(shape_id=shape_id, plan=plan)
```

### Stage 5: Asset Collection
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/drawingml/assets.py`

AssetRegistry collects FontAsset objects:
```python
def add_font_plan(self, *, shape_id: int, plan: EmbeddedFontPlan) -> None:
    self._fonts.append(FontAsset(shape_id=shape_id, plan=plan))
```

FontAsset wraps the EmbeddedFontPlan with metadata.

### Stage 6: PPTX Packaging
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/io/pptx_writer.py` (lines 471-561)

PPTXPackageBuilder._write_font_parts():
1. Iterates font_assets from DrawingMLRenderResult
2. **KEY: Lines 485-488** - Extracts font_data:
   ```python
   metadata = plan.metadata or {}
   font_data = metadata.get("font_data")  # ← RETRIEVES BYTES
   if not isinstance(font_data, (bytes, bytearray)):
       continue
   font_bytes = bytes(font_data)
   ```
3. Deduplicates by (family, strategy, glyph_count, relationship_hint, md5)
4. Creates `ppt/fonts/` directory
5. Writes each font file (lines 539-540):
   ```python
   with target_path.open("wb") as handle:
       handle.write(font_bytes)
   ```
6. Returns list of _PackagedFont objects

### Stage 7: Presentation Metadata
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/io/pptx_writer.py` (lines 605-625)

Updates presentation.xml with embeddedFontLst:
```xml
<p:embeddedFontLst>
  <p:embeddedFont>
    <p:font typeface="FontName"/>
    <p:regular r:id="rIdFontX" r:subsetted="1"/>
  </p:embeddedFont>
</p:embeddedFontLst>
```

### Stage 8: Relationship Wiring
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/io/pptx_writer.py` (lines 653-665)

Adds font relationships to presentation.xml.rels:
```xml
<Relationship
    Id="rIdFontX"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
    Target="fonts/fontX.ttf"/>
```

### Stage 9: Content Types
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/io/pptx_writer.py` (lines 718-732)

Updates [Content_Types].xml with font MIME types and overrides for each font.

---

## 3. Data Structures in Conversion Pipeline

### FontMatch (Service Resolution)
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/service.py`

```python
@dataclass(frozen=True)
class FontMatch:
    family: str
    path: str | None  # URL or filesystem path
    weight: int
    style: str
    found_via: str  # "webfont", "system", "directory"
    score: float = 0.0
    embedding_allowed: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)
    # ↑ Contains "font_data" (bytes) for web fonts
```

### EmbeddedFontPlan (IR Level)
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/ir/text.py`

```python
@dataclass(frozen=True)
class EmbeddedFontPlan:
    font_family: str
    requires_embedding: bool
    subset_strategy: str
    glyph_count: int = 0
    relationship_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # ↑ Contains "font_data" (bytes) passed through from embedding engine
```

### TextFrame (IR Level)
```python
@dataclass(frozen=True)
class TextFrame:
    origin: Point
    anchor: TextAnchor
    bbox: Rect
    runs: list[Run] | None = None
    embedding_plan: EmbeddedFontPlan | None = None
    # ↑ Link between text and its embedding plan
```

### FontAsset (Asset Collection)
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/drawingml/assets.py`

```python
@dataclass(frozen=True)
class FontAsset:
    shape_id: int
    plan: EmbeddedFontPlan  # Contains metadata with font_data
```

---

## 4. Injection Point for Web Font Data

### Primary Injection: FontEmbeddingRequest.metadata
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/embedding.py` (lines 178-188, 227-237)

When embedding engine processes request:
```python
metadata = {
    "subset_strategy": request.subset_strategy,
    "preserve_hinting": request.preserve_hinting,
    "font_path": request.font_path,
    "glyph_ids": request.glyph_ids,
    "characters": request.characters,
    "font_data": data,  # ← EMBEDDED HERE FOR DIRECT COPY
    "optimisation": request.optimisation.value,
    "permission": permission.value,
}
metadata.update(request.metadata)  # ← User metadata merged
```

The request.metadata from FontMatch can include web font data that was loaded.

### Secondary Injection: FontMatch.metadata
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/providers/webfont.py` (lines 240-278)

WebFontProvider adds to FontMatch.metadata:
```python
metadata: dict[str, object] = {
    "source": "webfont",
    "format": format_hint,
    "font_display": rule.display,
    "unicode_range": rule.unicode_range,
    "src_count": len(rule.src),
}

if loaded_font:
    metadata["loaded"] = True
    metadata["font_data"] = loaded_font.data  # ← BYTES STORED
    metadata["decompressed"] = loaded_font.decompressed
    metadata["loaded_format"] = loaded_font.format
    metadata["loaded_size_bytes"] = loaded_font.size_bytes
    url = loaded_font.source_url

return FontMatch(
    family=rule.family,
    path=url,
    weight=rule.weight_numeric,
    style=rule.style,
    found_via="webfont",
    embedding_allowed=embedding_allowed,
    metadata=metadata,  # ← This gets merged into request metadata
)
```

### Tertiary Injection: TextConversionPipeline._plan_embedding
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/core/ir/text_pipeline.py` (lines 233-248)

When creating FontEmbeddingRequest:
```python
request = FontEmbeddingRequest(
    font_path=match.path,
    glyph_ids=glyph_tuple,
    preserve_hinting=decision.embedding.preserve_hinting,
    subset_strategy=decision.embedding.subset_strategy,
    metadata={  # ← This is the initial request metadata
        "font_family": match.family,
        "font_source": metadata.get("font_source"),
        # ↑ match.metadata (including font_data) will be available via match object
    },
)
subset_result = self._embedding.subset_font(request)
if subset_result is not None:
    metadata.update(subset_result.packaging_metadata)  # ← Merges embedding result
```

**Key Insight:** To inject web font data, it should be added to FontMatch.metadata["font_data"] and will flow through:
1. FontMatch.metadata → (implicitly available in request context)
2. FontEmbeddingResult.packaging_metadata (line 248: subset_result.packaging_metadata)
3. EmbeddedFontPlan.metadata
4. PPTX packaging via plan.metadata.get("font_data")

---

## 5. Font File Writing to ppt/fonts/ Directory

### Directory Creation
**File:** `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/io/pptx_writer.py` (lines 506-507)

```python
fonts_dir = package_root / "ppt" / "fonts"
fonts_dir.mkdir(parents=True, exist_ok=True)
```

### Filename Generation
Lines 514-537:
- Base filename from `plan.font_family` or `metadata.get("font_family")`
- Extension derived from `metadata.get("font_path")` or defaults to "ttf"
- Numbering: `font1.ttf`, `font2.otf`, etc.
- Format conversion: extension lowercased

### File Writing
Lines 539-540:
```python
target_path = fonts_dir / filename
with target_path.open("wb") as handle:
    handle.write(font_bytes)
```

### Relationship ID Assignment
Lines 524-534:
- Prefers `plan.relationship_hint` if not already used
- Falls back to generated IDs: `rIdFont1`, `rIdFont2`, etc.
- Tracks used IDs to avoid collisions

### Content Type Detection
Lines 753-761 (`_content_type_for_extension()`):
```python
mapping = {
    "ttf": "application/x-font-ttf",
    "otf": "application/x-font-otf",
    "woff": "application/font-woff",
    "woff2": "application/font-woff2",
    "odttf": "application/vnd.openxmlformats-officedocument.obfuscatedFont",
}
```

### Deduplication
Lines 480-501:
```python
seen_keys: set[tuple[object, ...]] = set()
for asset in font_assets:
    plan = asset.plan
    if not plan.requires_embedding:
        continue
    font_data = metadata.get("font_data")
    if not isinstance(font_data, (bytes, bytearray)):
        continue
    font_bytes = bytes(font_data)
    digest = hashlib.md5(font_bytes, usedforsecurity=False).hexdigest()
    key = (
        plan.font_family,
        plan.subset_strategy,
        plan.glyph_count,
        plan.relationship_hint,
        digest,  # ← Same bytes = skipped
    )
    if key in seen_keys:
        continue
    seen_keys.add(key)
    entries.append((plan, metadata, font_bytes))
```

Prevents duplicate fonts from being written multiple times.

---

## 6. Integration Summary: Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ SVG with @font-face rules                                   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ SVGParser extracts FontFaceRule from <style>                │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ FontLoader loads from src (data URI, remote, etc.)          │
│ → LoadedFont { data: bytes, format, ... }                   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ WebFontProvider.resolve(FontQuery)                          │
│ → FontMatch {                                               │
│     family: str                                             │
│     path: URL                                               │
│     metadata: {                                             │
│         "font_data": bytes,  ← KEY INJECTION POINT          │
│         "loaded": True,                                     │
│         "loaded_format": str,                               │
│         ...                                                 │
│     }                                                       │
│ }                                                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ TextConversionPipeline._plan_embedding()                    │
│ → FontEmbeddingRequest {                                    │
│     font_path: URL (for loading)                            │
│     glyph_ids: [32, 65, 66, ...]                            │
│     metadata: {                                             │
│         "font_source": str,                                 │
│         // Will include match.metadata items                │
│     }                                                       │
│ }                                                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ FontEmbeddingEngine.subset_font()                           │
│ → If path is URL: Try to load (won't work, needs fetch!)    │
│ → If path is file: Load and subset or copy                  │
│ → FontEmbeddingResult {                                     │
│     relationship_id: "rIdFont1"                             │
│     glyph_count: 42                                         │
│     bytes_written: 5000                                     │
│     packaging_metadata: {                                   │
│         "font_data": bytes,  ← FROM REQUEST OR FILE         │
│         "font_path": str,                                   │
│         "permission": str,                                  │
│         ...                                                 │
│     }                                                       │
│ }                                                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ TextFrame.embedding_plan = EmbeddedFontPlan {               │
│     font_family: str                                        │
│     requires_embedding: True                                │
│     subset_strategy: str                                    │
│     glyph_count: 42                                         │
│     metadata: {                                             │
│         "font_data": bytes,  ← PASSED THROUGH               │
│         ...                                                 │
│     }                                                       │
│ }                                                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ DrawingMLWriter registers FontAsset                         │
│ → AssetRegistry.add_font_plan(shape_id, plan)               │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ PPTXPackageBuilder._write_font_parts()                      │
│ 1. Extract plan.metadata["font_data"] → bytes               │
│ 2. Create ppt/fonts/ directory                              │
│ 3. Generate filename (font1.ttf, etc.)                      │
│ 4. Write bytes to ppt/fonts/fontX.ext                       │
│ 5. Generate relationship ID                                 │
│ 6. Return _PackagedFont { filename, rel_id, family }        │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ PPTXPackageBuilder._update_presentation_parts()             │
│ 1. Update presentation.xml with embeddedFontLst             │
│ 2. Add <p:embeddedFont> for each font                       │
│ 3. Update presentation.xml.rels with font relationships     │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ PPTXPackageBuilder._write_content_types()                   │
│ 1. Update [Content_Types].xml with font MIME types          │
│ 2. Add Override entries for ppt/fonts/fontX.*               │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│ Final PPTX Structure:                                        │
│ ├── ppt/fonts/font1.ttf (bytes)                             │
│ ├── ppt/fonts/font2.otf (bytes)                             │
│ ├── ppt/presentation.xml (with embeddedFontLst)             │
│ ├── ppt/_rels/presentation.xml.rels (with font rels)        │
│ └── [Content_Types].xml (with font MIME types)              │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Critical Issue: Font Data from URLs

### Problem
FontEmbeddingEngine._subset_copy() and _subset_with_fonttools() expect `request.font_path` to be a valid filesystem path (lines 173, 212):
```python
data = Path(request.font_path).read_bytes()
font = TTFont(request.font_path, lazy=False)
```

But for web fonts, `match.path` is a URL (data URI or HTTP URL), which cannot be read directly from filesystem.

### Solution Pattern
The font_data should be passed via metadata instead:
1. WebFontProvider already loads data via FontLoader
2. FontEmbeddingEngine should check request.metadata["font_data"] first
3. If font_data exists in metadata, use it directly (in-memory)
4. Fall back to reading from file if path is filesystem

### Current Workaround (Implicit)
- For data URI fonts: path is data URI, but embedding won't work with Path().read_bytes()
- Font data is in metadata["font_data"] - **needs explicit handling in embedding engine**

---

## 8. Key Files for Web Font Injection

1. **`/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/embedding.py`** (Lines 167-198, 200-247)
   - Modify to check request.metadata["font_data"] before Path.read_bytes()
   - OR pass font_data directly to FontEmbeddingResult

2. **`/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/providers/webfont.py`** (Lines 253-278)
   - Currently adds font_data to FontMatch.metadata
   - Needs to ensure it flows to FontEmbeddingRequest.metadata

3. **`/Users/ynse/projects/svg2ooxml/src/svg2ooxml/core/ir/text_pipeline.py`** (Lines 233-248)
   - Extract font_data from match.metadata
   - Pass to FontEmbeddingRequest.metadata

4. **`/Users/ynse/projects/svg2ooxml/src/svg2ooxml/io/pptx_writer.py`** (Lines 471-561)
   - Already correctly extracts metadata["font_data"]
   - Already correctly writes to ppt/fonts/ directory

---

## 9. Test Coverage

**File:** `/Users/ynse/projects/svg2ooxml/tests/integration/test_webfont_embedding_e2e.py`

Tests data URI fonts embedded in PPTX but shows that font bytes need to be passed through the pipeline properly. Key test cases:
- `test_data_uri_ttf_font_embedded_in_pptx()`: Verifies TTF in ppt/fonts/
- `test_data_uri_otf_font_embedded_in_pptx()`: Verifies OTF support
- `test_multiple_font_weights_embedded_separately()`: Multiple fonts

---

## Summary: Where to Inject Web Font Data

1. **FontMatch.metadata["font_data"]** - Loaded by FontLoader in WebFontProvider
2. → Needs to flow through text pipeline
3. → **EmbeddedFontPlan.metadata["font_data"]** - Final IR representation
4. → **PPTX Writer retrieves:** `plan.metadata.get("font_data")`
5. → **Writes to:** `ppt/fonts/fontN.{ttf|otf|woff2}`

**Critical:** Ensure FontEmbeddingEngine doesn't fail when font_path is a URL. It should check metadata["font_data"] first.
