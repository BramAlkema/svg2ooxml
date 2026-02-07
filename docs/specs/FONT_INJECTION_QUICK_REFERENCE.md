# Font Embedding: Quick Reference for Web Font Integration

## 5-Stage Pipeline Overview

```
Web Font Data → Resolution → Planning → Rendering → Packaging
    ↓               ↓            ↓          ↓            ↓
FontLoader    FontService  TextPipeline  DrawingML  PPTX Writer
    ↓               ↓            ↓          ↓            ↓
LoadedFont    FontMatch   EmbedPlan   FontAsset   ppt/fonts/
  bytes        metadata    metadata    metadata    font1.ttf
```

---

## 1. LOADER STAGE: FontLoader (loader.py)

**What it does:** Loads font bytes from data URIs, remote URLs, or filesystem

**Output:** LoadedFont
```python
@dataclass
class LoadedFont:
    data: bytes                    # ← RAW FONT BYTES
    format: str                    # "ttf", "otf", "woff", "woff2"
    source_url: str
    decompressed: bool             # WOFF/WOFF2 decompressed?
    size_bytes: int
```

**Key functions:**
- `load_data_uri(data_uri: str)` - Decode base64, decompress WOFF/WOFF2
- `load_remote(url: str, format_hint)` - Fetch from HTTP(S) via FontFetcher
- Auto-detects format from magic bytes or MIME type

---

## 2. RESOLUTION STAGE: WebFontProvider (providers/webfont.py)

**What it does:** Match FontQuery against @font-face rules, load font data

**Input:** FontQuery
```python
@dataclass
class FontQuery:
    family: str                    # "Arial", "Helvetica", etc.
    weight: int = 400              # 100-900
    style: str = "normal"          # "normal", "italic"
    fallback_chain: tuple = ()     # Fallback families
```

**Output:** FontMatch
```python
@dataclass(frozen=True)
class FontMatch:
    family: str
    path: str | None               # URL (could be data URI)
    weight: int
    style: str
    found_via: str                 # "webfont", "system", "directory"
    embedding_allowed: bool = True
    metadata: Mapping[str, object] # ← CRITICAL CONTAINER
```

**Lines 253-278 (INJECTION POINT #1):**
```python
if loaded_font:
    metadata["loaded"] = True
    metadata["font_data"] = loaded_font.data      # ← BYTES HERE
    metadata["decompressed"] = loaded_font.decompressed
    metadata["loaded_format"] = loaded_font.format
    metadata["loaded_size_bytes"] = loaded_font.size_bytes

return FontMatch(
    family=rule.family,
    path=url,
    weight=rule.weight_numeric,
    style=rule.style,
    found_via="webfont",
    embedding_allowed=embedding_allowed,
    metadata=metadata,                # ← Contains font_data
)
```

---

## 3. PLANNING STAGE: TextConversionPipeline (text_pipeline.py)

**What it does:** Plan font embedding, create EmbeddedFontPlan

**Input:** TextFrame with runs

**Key method:** _plan_embedding() Lines 187-270

**Critical section (233-248):**
```python
match: FontMatch | None = self._font_service.find_font(query)

if requires_embedding and self._embedding is not None and match.path:
    request = FontEmbeddingRequest(
        font_path=match.path,              # URL or file path
        glyph_ids=glyph_tuple,
        preserve_hinting=...,
        subset_strategy=...,
        metadata={
            "font_family": match.family,
            "font_source": match.found_via,
            # ↑ Should also include match.metadata items!
        },
    )
    subset_result = self._embedding.subset_font(request)
    
if subset_result is not None:
    metadata.update(subset_result.packaging_metadata)
    # ↑ This has font_data from embedding engine
```

**Output:** EmbeddedFontPlan
```python
@dataclass(frozen=True)
class EmbeddedFontPlan:
    font_family: str
    requires_embedding: bool
    subset_strategy: str
    glyph_count: int = 0
    relationship_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # ↑ Contains font_data
```

**Attached to:** TextFrame.embedding_plan

---

## 4. EMBEDDING STAGE: FontEmbeddingEngine (embedding.py)

**What it does:** Subset or copy fonts based on used glyphs

**Input:** FontEmbeddingRequest
```python
@dataclass(frozen=True)
class FontEmbeddingRequest:
    font_path: str                         # ← Path or URL
    glyph_ids: Sequence[int] = ()          # Glyph Unicode values
    characters: Sequence[str] = ()
    preserve_hinting: bool = False
    subset_strategy: str = "glyph"         # "glyph", "character", "aggressive", "none"
    optimisation: FontOptimisationLevel = BALANCED
    metadata: Mapping[str, object] = {}    # ← Can have font_data!
```

**Key methods:**
- `subset_font(request)` - Main entry point
- `_subset_with_fontforge()` - Lines 200-247: Uses FontForge
- `_subset_copy()` - Lines 167-198: Direct copy for restricted fonts

**Critical section (_subset_copy, 178-188):**
```python
metadata = {
    "subset_strategy": request.subset_strategy,
    "preserve_hinting": request.preserve_hinting,
    "font_path": request.font_path,
    "glyph_ids": request.glyph_ids,
    "characters": request.characters,
    "font_data": data,                    # ← FROM FILE
    "optimisation": request.optimisation.value,
    "permission": permission.value,
}
metadata.update(request.metadata)         # ← User metadata merged

return FontEmbeddingResult(
    relationship_id=None,
    subset_path=None,
    glyph_count=self._glyph_count(request),
    bytes_written=len(data),
    permission=permission,
    optimisation=request.optimisation,
    packaging_metadata=metadata,           # ← HAS font_data
)
```

**Output:** FontEmbeddingResult
```python
@dataclass(frozen=True)
class FontEmbeddingResult:
    relationship_id: str | None
    subset_path: str | None
    glyph_count: int
    bytes_written: int
    permission: EmbeddingPermission
    optimisation: FontOptimisationLevel
    packaging_metadata: Mapping[str, object]  # ← Contains font_data
```

---

## 5. ASSET COLLECTION: DrawingML Writer (drawingml/writer.py)

**What it does:** Register embedding plans as FontAssets

**Location:** Lines 611-624
```python
if getattr(element, "embedding_plan", None) is not None:
    plan = element.embedding_plan
    if plan.requires_embedding:
        self._assets.add_font_plan(shape_id=shape_id, plan=plan)
```

**Creates:** FontAsset
```python
@dataclass(frozen=True)
class FontAsset:
    shape_id: int
    plan: EmbeddedFontPlan          # Has metadata with font_data
```

**Stored in:** AssetRegistry → DrawingMLRenderResult.assets

---

## 6. PPTX PACKAGING: PPTXPackageBuilder (io/pptx_writer.py)

**What it does:** Write fonts to ppt/fonts/ directory

**Method:** _write_font_parts() Lines 471-561

**Key extraction (485-489):**
```python
metadata = plan.metadata or {}
font_data = metadata.get("font_data")       # ← RETRIEVES BYTES
if not isinstance(font_data, (bytes, bytearray)):
    continue
font_bytes = bytes(font_data)
```

**Directory & filename (506-540):**
```python
fonts_dir = package_root / "ppt" / "fonts"
fonts_dir.mkdir(parents=True, exist_ok=True)

filename = f"font{filename_index}.{extension}"
target_path = fonts_dir / filename

with target_path.open("wb") as handle:
    handle.write(font_bytes)               # ← WRITES TO DISK
```

**Deduplication (480-501):**
```python
digest = hashlib.md5(font_bytes, usedforsecurity=False).hexdigest()
key = (
    plan.font_family,
    plan.subset_strategy,
    plan.glyph_count,
    plan.relationship_hint,
    digest,
)
if key in seen_keys:
    continue                               # ← Skip duplicate
```

**Relationships & XML (605-667):**
```xml
<!-- presentation.xml -->
<p:embeddedFontLst>
  <p:embeddedFont>
    <p:font typeface="FontName"/>
    <p:regular r:id="rIdFont1" r:subsetted="1"/>
  </p:embeddedFont>
</p:embeddedFontLst>

<!-- presentation.xml.rels -->
<Relationship
    Id="rIdFont1"
    Type="...relationships/font"
    Target="fonts/font1.ttf"/>
```

---

## Critical Integration Points

### Point 1: FontMatch.metadata["font_data"]
- **Source:** WebFontProvider (lines 256, 260)
- **Created by:** FontLoader.load_data_uri() or load_remote()
- **Contains:** Raw font bytes after decompression

### Point 2: FontEmbeddingRequest.metadata
- **Source:** TextConversionPipeline._plan_embedding() (lines 238-241)
- **Should contain:** Copy/merge of FontMatch.metadata
- **Problem:** Currently doesn't explicitly copy match.metadata to request.metadata

### Point 3: FontEmbeddingResult.packaging_metadata
- **Source:** FontEmbeddingEngine.subset_font() (lines 190-197, 239-246)
- **Contains:** Request metadata + embedded font_data + stats
- **Usage:** Merged into EmbeddedFontPlan.metadata

### Point 4: EmbeddedFontPlan.metadata
- **Source:** TextConversionPipeline._plan_embedding() (lines 263-270)
- **Contains:** All planning metadata + font_data
- **Flows to:** FontAsset → PPTX Writer

### Point 5: PPTX _write_font_parts extraction
- **Source:** PPTXPackageBuilder._write_font_parts() (lines 485-489)
- **Extracts:** plan.metadata.get("font_data")
- **Writes:** bytes to ppt/fonts/fontN.{ttf|otf|...}

---

## Known Issues & Gaps

### Issue 1: FontPath vs Data
FontEmbeddingEngine expects font_path to be a filesystem path:
- Line 173: `data = Path(request.font_path).read_bytes()`
- Line 212: `font = TTFont(request.font_path, lazy=False)`

But for web fonts:
- font_path is a data URI or HTTP URL
- Can't be read with Path().read_bytes()
- **Solution:** Check request.metadata["font_data"] first

### Issue 2: Metadata Flow Gap
Text pipeline creates request with minimal metadata:
```python
metadata={
    "font_family": match.family,
    "font_source": metadata.get("font_source"),
}
```
Doesn't explicitly copy match.metadata items (like font_data)
- **Solution:** Merge match.metadata into request.metadata

### Issue 3: Subsetting with In-Memory Data
FontForge expects a file path, not raw bytes
- Use a temp file when subsetting web fonts

---

## Test Files

- `/Users/ynse/projects/svg2ooxml/tests/integration/test_webfont_embedding_e2e.py`
  - Tests data URI TTF/OTF fonts
  - Tests multiple font weights
  - Validates ppt/fonts/ directory content

---

## Action Items for Web Font Support

1. **Ensure metadata flow from FontMatch → FontEmbeddingRequest**
   - File: text_pipeline.py (line 238)
   - Merge match.metadata into request.metadata

2. **Handle in-memory font data in embedding engine**
   - File: embedding.py (lines 173, 212)
   - Check request.metadata["font_data"] before Path.read_bytes()

3. **Support subsetting of in-memory fonts**
   - File: embedding.py (line 212)
   - Load font bytes from metadata instead of filesystem if URL

4. **Verify PPTX writer correctly unpacks font_data**
   - File: pptx_writer.py (lines 485-540)
   - Already correct! Just ensure it receives font_data

5. **Add integration tests for web font flow**
   - Already exists: test_webfont_embedding_e2e.py
   - May need expansion for edge cases
