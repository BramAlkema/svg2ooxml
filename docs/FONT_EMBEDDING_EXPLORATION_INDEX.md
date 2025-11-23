# Font Embedding in PPTX: Complete Exploration Index

This directory contains comprehensive documentation about how fonts are embedded in PPTX files, created through thorough exploration of the svg2ooxml codebase.

## Documents Generated

### 1. **FONT_EMBEDDING_ANALYSIS.md** (26KB)
   **Most Detailed Reference**
   
   Contains:
   - Complete mapping of font embedding logic across all modules
   - All 9 stages of the packaging pipeline with line numbers
   - Data structure definitions (FontMatch, EmbeddedFontPlan, etc.)
   - All 4 injection points for web font data
   - Font file writing procedures (directory creation, naming, deduplication)
   - Full integration flow diagram
   - Known issues and solutions
   - Test coverage information

   **Best for:** Understanding the entire system architecture and finding specific code locations

### 2. **FONT_INJECTION_QUICK_REFERENCE.md** (11KB)
   **Developer-Friendly Quick Guide**
   
   Contains:
   - 5-stage pipeline overview
   - Each stage with input/output types
   - Key methods and line numbers
   - Critical integration points (5 points identified)
   - Known issues with solutions
   - Action items for web font support
   - Test file references

   **Best for:** Quick lookup while implementing changes, understanding decision points

### 3. **FONT_DATA_FLOW_VISUAL.txt** (16KB)
   **ASCII Art Flowchart**
   
   Contains:
   - ASCII flowchart showing data transformation at each stage
   - Stage-by-stage breakdown with visual tree structure
   - Data structure evolution (LoadedFont → FontMatch → EmbeddedFontPlan → PPTX)
   - Metadata flow summary
   - PPTX output structure
   - Critical decision points
   - Dependencies checklist

   **Best for:** Visual understanding of the pipeline, presentations, documentation

---

## Quick Navigation

### Finding Specific Components

**Font Loading:**
- FontLoader class: `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/loader.py`
- Lines 70-189: Core loading logic
- Lines 122-189: Data URI loading with decompression

**Font Resolution:**
- WebFontProvider class: `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/providers/webfont.py`
- Lines 45-278: Font matching and metadata creation
- Lines 253-278: **INJECTION POINT #1** - font_data added to FontMatch.metadata

**Font Planning:**
- TextConversionPipeline class: `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/core/ir/text_pipeline.py`
- Lines 187-270: Embedding planning
- Lines 233-248: **INJECTION POINT #2** - font_data should flow to FontEmbeddingRequest

**Font Embedding:**
- FontEmbeddingEngine class: `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/embedding.py`
- Lines 105-154: Main subset_font() method
- Lines 167-198: Direct copy strategy
- Lines 200-247: fontTools subsetting strategy

**Asset Collection:**
- DrawingMLWriter: `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/drawingml/writer.py`
- Lines 611-624: Font plan registration

**PPTX Writing:**
- PPTXPackageBuilder class: `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/io/pptx_writer.py`
- Lines 471-561: **INJECTION POINT #5** - font_data extraction and writing
- Lines 485-489: Actual font_data retrieval
- Lines 506-540: Directory creation and file writing
- Lines 605-667: Relationship and XML updates

### Critical Code Sections

**Font Data Extraction (PPTX Writer):**
```python
# File: pptx_writer.py, Lines 485-489
metadata = plan.metadata or {}
font_data = metadata.get("font_data")  # ← GET BYTES
if not isinstance(font_data, (bytes, bytearray)):
    continue
font_bytes = bytes(font_data)
```

**Font Data Storage (WebFontProvider):**
```python
# File: webfont.py, Lines 253-278
if loaded_font:
    metadata["loaded"] = True
    metadata["font_data"] = loaded_font.data  # ← STORE BYTES
```

**Font Data Planning (TextPipeline):**
```python
# File: text_pipeline.py, Lines 233-248
request = FontEmbeddingRequest(
    font_path=match.path,
    glyph_ids=glyph_tuple,
    metadata={
        "font_family": match.family,
        "font_source": metadata.get("font_source"),
        # ← Should include match.metadata items!
    },
)
```

---

## Key Findings

### Data Flow Path
```
FontLoader.data 
  → WebFontProvider.metadata["font_data"]
  → (Should be) FontEmbeddingRequest.metadata["font_data"]
  → FontEmbeddingResult.packaging_metadata["font_data"]
  → EmbeddedFontPlan.metadata["font_data"]
  → PPTX Writer retrieval
  → ppt/fonts/fontN.{ttf|otf}
```

### Critical Integration Points

1. **WebFontProvider (Lines 253-278):** Stores loaded font bytes in FontMatch.metadata
2. **TextConversionPipeline (Lines 233-248):** Should merge FontMatch.metadata into FontEmbeddingRequest.metadata
3. **FontEmbeddingEngine (Lines 178-188):** Merges request.metadata into FontEmbeddingResult.packaging_metadata
4. **TextConversionPipeline (Lines 263-270):** Merges embedding result into EmbeddedFontPlan.metadata
5. **PPTXPackageBuilder (Lines 485-489):** Extracts font_data and writes to ppt/fonts/

### Known Issues

1. **Font Path vs Data Issue:**
   - FontEmbeddingEngine expects font_path to be a filesystem path
   - For web fonts, path is a data URI or HTTP URL
   - Solution: Check request.metadata["font_data"] first

2. **Metadata Flow Gap:**
   - TextPipeline doesn't explicitly copy FontMatch.metadata to FontEmbeddingRequest.metadata
   - Font_data ends up in metadata but implicit
   - Solution: Explicitly merge match.metadata

3. **Subsetting URLs:**
   - fontTools can't subset from URL paths
   - Need to check metadata["font_data"] before trying filesystem access

---

## File Locations (Absolute Paths)

### Core Implementation Files
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/embedding.py` - Embedding engine
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/loader.py` - Font loading
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/providers/webfont.py` - Web font resolution
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/services/fonts/service.py` - Font service and data structures
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/core/ir/text_pipeline.py` - Text conversion pipeline
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/drawingml/writer.py` - DrawingML rendering
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/drawingml/assets.py` - Asset collection
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/io/pptx_writer.py` - PPTX packaging
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/ir/text.py` - Text IR structures

### Data Structure Definitions
- FontMatch: service.py lines 22-32
- FontQuery: service.py lines 10-18
- EmbeddedFontPlan: ir/text.py lines 157-172
- FontEmbeddingRequest: embedding.py lines 47-62
- FontEmbeddingResult: embedding.py lines 65-75
- LoadedFont: loader.py lines 48-67
- FontAsset: assets.py lines 24-29

### Test Files
- `/Users/ynse/projects/svg2ooxml/tests/integration/test_webfont_embedding_e2e.py` - End-to-end web font tests
- `/Users/ynse/projects/svg2ooxml/tests/unit/services/test_font_embedding_engine.py` - Embedding engine tests
- `/Users/ynse/projects/svg2ooxml/tests/integration/test_font_embedding_eot.py` - Verifies `.fntdata` payloads, content types, relationships, and `<p:fontKey>` wiring.

---

## Dependencies

### External Libraries
- **fontTools** (embedding.py): Font subsetting and TTFont manipulation
- **brotli** (loader.py): WOFF2 decompression
- **gzip** (loader.py): WOFF decompression (stdlib)
- **base64** (loader.py): Data URI decoding (stdlib)
- **tools/verify_font_embedding.py** – CLI helper that uses `lxml` to inspect PPTX font parts and GUID wiring.

### Internal Dependencies
- SVGParser → FontFaceRule extraction
- FontService → Provider registration and caching
- FontSystem → Directory provider initialization
- TextConversionPipeline → Glue between resolution and packaging
- DrawingMLWriter → Asset registration
- PPTXPackageBuilder → Final packaging

---

## Recommendations for Enhancement

1. **Make metadata flow explicit:**
   - In text_pipeline.py line 238, explicitly merge match.metadata
   - Ensure all FontMatch metadata flows to planning stage

2. **Handle in-memory fonts in embedding engine:**
   - Check request.metadata["font_data"] in _subset_copy() and _subset_with_fonttools()
   - Avoid filesystem access for URL-based fonts

3. **Support in-memory subsetting:**
   - Load font from BytesIO for fontTools operations
   - Allows subsetting without temp files for web fonts

4. **Add comprehensive tests:**
   - Data URI subsetting
   - Remote URL font embedding (with mocking)
   - Multiple weight/style variants
   - Edge cases (restricted fonts, bitmap-only fonts)

5. **Consider performance:**
   - Cache subsetted fonts by hash
   - Already implemented in FontEmbeddingEngine._cache
   - Extend to consider font_data source

---

## How to Use These Documents

1. **First Time Learning:**
   - Start with FONT_DATA_FLOW_VISUAL.txt for overall picture
   - Read FONT_INJECTION_QUICK_REFERENCE.md for concepts
   - Reference FONT_EMBEDDING_ANALYSIS.md for details

2. **Implementing Changes:**
   - Use FONT_INJECTION_QUICK_REFERENCE.md for action items
   - Reference line numbers in FONT_EMBEDDING_ANALYSIS.md
   - Check FONT_DATA_FLOW_VISUAL.txt for metadata flow

3. **Debugging Issues:**
   - Trace data flow using FONT_DATA_FLOW_VISUAL.txt
   - Check critical integration points section
   - Look up specific file/line in FONT_EMBEDDING_ANALYSIS.md

4. **Documentation/Presentations:**
   - Use FONT_DATA_FLOW_VISUAL.txt for diagrams
   - Reference FONT_INJECTION_QUICK_REFERENCE.md for structure
   - Quote from FONT_EMBEDDING_ANALYSIS.md for details

---

## Document Generation Details

**Exploration Date:** 2025-11-03
**Repository:** /Users/ynse/projects/svg2ooxml
**Method:** Comprehensive code search and analysis
**Coverage:**
- src/svg2ooxml/services/fonts/ (all files)
- src/svg2ooxml/io/pptx_writer.py
- src/svg2ooxml/drawingml/ (selected files)
- src/svg2ooxml/core/ir/text_pipeline.py
- src/svg2ooxml/ir/text.py
- Integration tests

---

## Related Documentation

- ARCHITECTURE_SKELETON.md - Overall system architecture
- README.md - Project overview
- Integration test files - Usage examples

---

**Generated with comprehensive code exploration and analysis**
