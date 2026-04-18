# Visual Rendering Problems in Generated PPTX

**Date**: 2025-11-04
**Status**: FIXED - All 4 issues resolved (100%)
**Severity**: Resolved - All visual rendering and PowerPoint compliance issues fixed

## Summary

While PPTX files open in LibreOffice and corpus metrics report "success", several visual rendering issues were identified. **Status as of 2025-01-04**:

1. ✅ **FIXED: Stroke widths** - Were 10x too thin (1px instead of 10px) → Now correct with resvg-dominant style resolution
2. ✅ **FIXED: Text box sizing** - Were 40% too small causing text clipping → Now use proper line height (1.5x font size)
3. ✅ **FIXED: Missing required PPTX files** → presProps.xml, viewProps.xml, tableStyles.xml now included
4. ✅ **FIXED: Font content type and hyperlink format issues** → All PowerPoint compliance issues resolved

## Issue 1: Stroke Widths are 10x Too Small

### Status: ✅ FIXED (2025-01-04)

**Problem**: Shapes with `stroke-width="10"` rendered with hairline 1-pixel strokes (10x too thin).

**Root Cause**: Legacy `<use>` element expansion was modifying the SVG DOM, breaking the element-to-resvg-node mapping. Style extraction couldn't find resvg nodes, fell back to defaults.

**Solution**: Implemented resvg-dominant style resolution:
1. Skip legacy DOM expansion when resvg tree exists
2. Convert `<use>` elements directly using mapped resvg nodes
3. Merge `<use>` attributes in resvg tree building per SVG spec

**Implementation**:
- `src/svg2ooxml/core/traversal/hooks.py`: Skip legacy expansion in resvg mode
- `src/svg2ooxml/core/traversal/runtime.py`: Convert `<use>` directly
- `src/svg2ooxml/core/resvg/usvg_tree.py`: Merge `<use>` presentation attributes

**Tests**: 7 tests in `tests/unit/core/ir/test_converter_resvg_lookup.py`, `tests/unit/map/converter/test_styles_runtime_resvg.py`, and `tests/integration/resvg/test_use_stroke_width.py`

**Result**: Stroke widths now render correctly (10px → 95,250 EMUs).

---

### Original Symptom (Before Fix)

Shapes with `stroke-width="10"` in SVG render with hairline 1-pixel strokes in PPTX.

### Evidence

**SVG Source** (struct-use-10-f.svg):
```xml
<use id="testid1" xlink:href="#testrect1" x="40" y="100"
     style="stroke:darkgreen" stroke-width="10"/>
```

**Generated XML**:
```xml
<a:ln w="9525">
  <a:solidFill><a:srgbClr val="006400"/></a:solidFill>
</a:ln>
```

**Analysis**:
```
Expected: 10 pixels × 9525 EMU/pixel = 95,250 EMUs
Actual:   9,525 EMUs = 1 pixel
Error:    10x too small
```

### Root Cause

**Location**: `<use>` element attribute inheritance during resvg tree building and IR conversion

The bug occurs in two stages:

**Stage 1: Tree Building** (`src/svg2ooxml/core/resvg/usvg_tree.py:774-819`) - FIXED ✓
- `<use>` elements now correctly merge their presentation attributes with cloned content
- Cloned nodes have correct `stroke.width=10.0` in resvg tree

**Stage 2: IR Conversion** (`src/svg2ooxml/core/styling/style_extractor.py:258`) - BUG ✗
- Style is extracted from SVG DOM element, not from resvg tree node
- SVG DOM still has `<use>` elements after resvg tree expansion
- StyleResolver reads `<use>` element's attributes but doesn't find `stroke_width_px`
- Defaults to `1.0` when `stroke_width_px` not found
- Result: `stroke.width = 1.0` in IR (should be 10.0)

**Conversion chain**:
```
SVG parsing → resvg tree build (width=10.0 ✓) → style extraction → defaults to 1.0 ✗
```

**Key insight**: After `<use>` expansion, the resvg tree has cloned rects with correct strokes, but the SVG DOM still has `<use>` elements. Style extraction reads from SVG elements, missing the resvg node's corrected stroke width.

### Impact

- All strokes render as hairlines
- Shapes look incorrect (too thin outlines)
- Design fidelity lost
- W3C test failures (expects "thick darkgreen stroke")

### Related Code

- `src/svg2ooxml/ir/paint.py`: Stroke dataclass
- `src/svg2ooxml/drawingml/paint_runtime.py:78`: EMU conversion
- `src/svg2ooxml/drawingml/generator.py:21`: px_to_emu function (working correctly)
- Stroke creation: SVG parser or resvg integration (needs investigation)

## Issue 2: Text Boxes Too Small for Content

### Status: ✅ FIXED (2025-01-04)

**Problem**: Text boxes 40% too small, causing text to be clipped at top/bottom.

**Root Cause**: Text bbox calculation had two issues:
1. No point-to-pixel conversion (font_size_pt used directly as pixels)
2. Line height only 1.2x font size (too conservative)

**Solution**: Proper text box height calculation:
1. Convert points to pixels: `font_px = font_pt × (96/72)`
2. Use adequate line height: `line_height = font_px × 1.5`
3. Account for multiple lines: `height = line_height × num_lines`

**Implementation** (`src/svg2ooxml/core/ir/text_converter.py:260-302`):
```python
def _estimate_text_bbox(runs, origin_x, origin_y):
    max_font_pt = max(run.font_size_pt for run in runs)
    max_font_px = max_font_pt * (96.0 / 72.0)  # Convert pt to px

    lines = text_content.split("\\n")
    line_height = max_font_px * 1.5  # Adequate line height
    height = line_height * max(1, len(lines))
```

**Tests**: 7 tests in `tests/unit/core/ir/test_text_bbox_sizing.py`

**Results**:
- **Before**: 18pt font → 14.4px height (way too small)
- **After**: 18pt font → 36px height (correct)
- **Improvement**: 150% increase in height

---

### Original Symptom (Before Fix)

Text is clipped because bounding boxes don't account for actual text height.

### Evidence

**SVG Source** (struct-use-10-f.svg):
```xml
<text x="50%" y="3em" style="text-anchor:middle; fill:black">
  CSS selectors and use element
</text>
```

Font size: 18pt

**Generated XML**:
```xml
<a:xfrm>
  <a:off x="0" y="0"/>
  <a:ext cx="1988820" cy="137160"/>
</a:xfrm>
```

**Analysis**:
```
Text box height:  137,160 EMUs = 14.4 pixels
Font size:        18pt ≈ 24 pixels
Deficit:          -9.6 pixels (40% too small)
```

### Root Cause

Text bounding box calculation doesn't account for:
- Font ascent/descent (character height above/below baseline)
- Line height
- Padding/margins

Current calculation appears to use:
- Character width only
- Minimal height estimate

### Impact

- Text appears clipped at top/bottom
- Multiline text severely affected
- Inconsistent with SVG rendering
- Professional appearance compromised

### Visual Comparison

**Expected** (SVG in browser):
```
 CSS selectors and use element
 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 (full height, no clipping)
```

**Actual** (PPTX rendering):
```
 CSS selectors and use element
 ^^^^^^^^^^^^------^^^^^^------
 (top/bottom clipped)
```

## Issue 3: Missing Required OOXML Files

### Status: ✅ FIXED (2025-01-04)

**Problem**: PowerPoint required file repair due to missing required ECMA-376 files.

**Solution**: Added three required OOXML parts:
- `/ppt/presProps.xml` - Minimal presentation properties
- `/ppt/viewProps.xml` - View properties with normal view settings
- `/ppt/tableStyles.xml` - Table styles with default style reference

**Implementation** (`src/svg2ooxml/io/pptx_writer.py`):
```python
def _write_required_presentation_parts(self, package_root: Path):
    """Write required PPTX parts per ECMA-376."""
    # Creates presProps.xml, viewProps.xml, tableStyles.xml
    # Updates presentation.xml.rels with relationships
    # Updates [Content_Types].xml with declarations
```

**Tests**: `tests/unit/io/test_pptx_required_parts.py` (4 tests, all passing)

**Result**: PowerPoint now opens files without requiring repair.

**Additional Fixes** (see `pptx-powerpoint-validation.md`):
- ✅ Font content type changed to `application/x-fontdata` (was `application/x-font-ttf`)
- ✅ Hyperlink format fixed - removed invalid `ppaction://` URLs
- Minor DocProps declarations (low priority)

## Testing Gap

### Current Situation

**Corpus Testing** reports:
```
✓ Success (native: 85.0%, EMF: 10.0%, raster: 5.0%)
```

But this only tests:
- ✅ Conversion completes without crashes
- ✅ PPTX file structure is valid ZIP
- ✅ LibreOffice can render (lenient parser)

**Not tested**:
- ❌ Visual correctness (stroke widths, text sizing)
- ❌ PowerPoint compatibility (strict validation)
- ❌ Pixel-perfect fidelity
- ❌ Actual measurements (EMU values)

### Why LibreOffice Passes

LibreOffice is lenient:
- Accepts non-standard content types
- Renders with missing presProps/viewProps/tableStyles
- Tolerates invalid hyperlink formats
- **BUT still shows thin strokes and clipped text**

### What Visual E2E Tests Revealed

Running `tools/visual/w3c_suite.py`:
- ✅ Conversion completes
- ✅ Files render
- ❌ Visual output is incorrect (strokes too thin, text clipped)
- ❌ PowerPoint rejects files

## Recommended Fixes

### Priority 1: Fix Stroke Width Bug

**Location**: Stroke width conversion in SVG parser or resvg integration

**Investigation needed**:
```bash
# Find where stroke.width gets set
grep -r "Stroke(" src/svg2ooxml/core/parser/
grep -r "stroke.width =" src/svg2ooxml/
grep -r "stroke-width" src/svg2ooxml/core/resvg/
```

**Expected fix**: Ensure `stroke.width` in IR matches SVG user units correctly.

### Priority 2: Fix Text Box Sizing

**Location**: Text bounding box calculation

**Investigation needed**:
- Find text extent calculation code
- Add font metrics (ascent, descent, line-height)
- Test with various font sizes and multiline text

**Possible locations**:
- `src/svg2ooxml/core/ir/text_pipeline.py`
- `src/svg2ooxml/core/parser/svg_parser.py`
- Text-related IR converters

### Priority 3: Add PowerPoint Compliance

See `pptx-powerpoint-validation.md` for details.

### Priority 4: Improve Test Coverage

**Add to test suite**:

1. **Measurement validation tests**:
```python
def test_stroke_width_conversion():
    """Verify stroke-width=10 produces w=95250 EMUs."""
    svg = '<rect stroke-width="10"/>'
    pptx_xml = convert_and_extract_xml(svg)
    assert 'w="95250"' in pptx_xml
```

2. **Text box dimension tests**:
```python
def test_text_box_height():
    """Verify text box height accommodates font size."""
    svg = '<text font-size="18">Test</text>'
    bbox = get_text_box_dimensions(svg)
    assert bbox.height >= 24  # 18pt ≈ 24px
```

3. **PowerPoint validation tests**:
```python
def test_powerpoint_opens_without_repair():
    """Verify PowerPoint accepts file without repair."""
    pptx = generate_pptx(test_svg)
    assert not requires_repair(pptx)
```

## Impact Assessment

| Issue | Severity | User Impact | Corpus Detected? |
|-------|----------|-------------|------------------|
| Thin strokes | HIGH | Design fidelity lost | ❌ No |
| Clipped text | HIGH | Readability impaired | ❌ No |
| PowerPoint errors | MEDIUM | UX friction | ❌ No |
| Missing OOXML files | MEDIUM | Font/link breakage | ❌ No |

**Key Insight**: Corpus testing gives false confidence. Files "work" but are visually incorrect.

## Real-World Example

**W3C Test**: struct-use-10-f.svg

**Pass Criteria**: "Three rectangles have green fill and thick darkgreen stroke"

**Actual Output**:
- ✅ Green fill correct
- ❌ Stroke barely visible (1px instead of 10px)
- ❌ Text partially clipped

**Corpus Report**: "✓ Success"

**Reality**: Test failed visually, but metrics don't catch it.

## Next Steps

1. **Immediate**: Document as known issues, add warnings to corpus testing
2. **Short-term**: Fix stroke width bug (highest impact, likely simple fix)
3. **Medium-term**: Fix text box sizing (requires font metrics)
4. **Long-term**: Add PowerPoint compliance, improve test coverage

## References

- SVG stroke-width spec: https://www.w3.org/TR/SVG11/painting.html#StrokeWidthProperty
- OOXML DrawingML line spec: ECMA-376 Part 1, Section 20.1.2.2.24 (CT_LineProperties)
- EMU units: 914,400 EMUs per inch, 9,525 EMUs per pixel at 96 DPI
