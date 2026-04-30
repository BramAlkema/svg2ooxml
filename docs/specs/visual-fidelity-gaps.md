# Visual Fidelity Gaps Specification

**Status:** Draft
**Date:** 2026-03-24
**Context:** Side-by-side comparison of Ghostscript Tiger SVG vs PPTX output revealed four categories of visual difference. This spec documents the root causes and proposed fixes.

## 1. Slide Background Detection

### Problem
SVGs with a full-coverage background (e.g. a `<rect>` filling the viewBox, or inherited fill on root `<g>`) render on a white slide background in PowerPoint. The background shape is converted as a regular shape instead of being set as the slide background.

### Current behavior
- Slide template (`slide_template.xml`) has no `<p:bg>` element
- All SVG elements become shapes, including background rects
- Slide background defaults to white

### Proposed fix

**Phase 1: Background rect detection** in the IR converter. After parsing, scan `IRScene.elements` for a first element that:
- Is a `Rectangle` with no corner radius, no stroke, no effects
- Covers ≥95% of the viewport area (within tolerance)
- Has a `SolidPaint` fill

If found, extract it as `IRScene.background_color` and remove from `elements`.

**Phase 2: Slide background emission** in the DrawingML writer. When `background_color` is set, inject before `<p:spTree>`:
```xml
<p:bg>
  <p:bgPr>
    <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
    <a:effectLst/>
  </p:bgPr>
</p:bg>
```

### Files to modify
- `src/svg2ooxml/ir/scene.py` — add `background_color: str | None` field
- `src/svg2ooxml/core/ir/converter.py` or post-processing — background detection
- `src/svg2ooxml/drawingml/writer.py` — emit `<p:bg>` in slide XML
- `src/svg2ooxml/assets/pptx_scaffold/slide_template.xml` — add placeholder or keep dynamic

### Acceptance criteria
- Ghostscript Tiger gets black slide background
- EU flag gets blue (`#003399`) slide background
- SVGs without a clear background rect are unaffected
- Background detection is conservative — no false positives

---

## 2. Fill Inheritance on Groups

### Problem
Some shapes rendered with wrong fill when the SVG uses `<g fill="#color">` to set fill on a group and child paths inherit it.

### Current behavior
- Resvg tree correctly inherits fill via `_inherit_fill()` in `usvg_tree.py`
- Style extractor has `_compute_paint_style_with_inheritance()`
- Works for most cases

### Known gaps
- `<use>` clones that bypass resvg may lose inherited styles (style_runtime.py line 70)
- Legacy (non-resvg) path resolves styles differently

### Proposed fix
- Add integration test: SVG with `<g fill="#F00"><path d="..."/></g>` → verify PPTX shape has red fill
- Audit `<use>` clone style resolution to ensure parent `<g>` fill propagates
- No architectural change needed — this is mostly working

### Priority
Low — affects edge cases only. The Ghostscript Tiger ear issue is more likely a shape ordering / z-index issue than inheritance.

---

## 3. Stroke Width Under ViewBox Transforms

### Problem
When an SVG has a viewBox that differs from the viewport (e.g. `viewBox="0 0 100 100"` on a 1000×1000 canvas), stroke widths should scale accordingly. Thin whisker-like strokes may appear too thick or too thin.

### Current behavior
- Stroke width extracted from paint style as pixels
- Converted to EMU via `px_to_emu()` (9525 EMU/px)
- Resvg tree provides pre-resolved stroke widths
- No explicit viewBox scaling verification

### Known gaps
- `vector-effect: non-scaling-stroke` is implemented for shape strokes that pass
  through the IR converters.
- Stylesheet/transform edge cases still need corpus validation, especially
  non-uniform transforms and fallback paths.

### Proposed fix

**Phase 1: Verify resvg stroke scaling.** Create test SVGs with:
- `viewBox="0 0 100 100"` on 1000px canvas, stroke-width="1" → should render as 10px stroke in PPTX
- Same with `vector-effect: non-scaling-stroke` → should render as 1px

**Phase 2: Handle non-scaling-stroke.** Check for `vector-effect` during style extraction. Normal transformed strokes scale with baked geometry; `non-scaling-stroke` keeps the authored width.

### Files to modify
- `src/svg2ooxml/core/styling/style_extractor.py` — check `vector-effect`
- Test fixtures for viewBox stroke scaling

### Priority
Medium — visible in detailed SVGs with fine strokes.

---

## 4. Opacity Compositing

### Problem
Overlapping semi-transparent shapes may composite differently between SVG (Porter-Duff compositing) and DrawingML (shape-level alpha).

### Current behavior
- Element `opacity` → `<a:alphaModFix>` on shape
- `fill-opacity` → multiplied into SolidPaint alpha
- `stroke-opacity` → applied to stroke paint alpha
- Group opacity with overlapping children → **rasterized to PNG** (correct but lossy)
- Group opacity with non-overlapping children → passed through to individual shapes

### Known gaps
- **Non-overlapping group opacity**: children rendered individually without multiplying group opacity. DrawingML has no group-level alpha, so each child gets its own opacity. This is correct for non-overlapping shapes but may differ from SVG compositing for edge cases.
- **Overlap detection**: `children_overlap()` uses rendered child bounds, including stroke width and zero-area stroked lines. It also uses exact intersection for simple filled circle pairs. It remains conservative for complex curves and effects, so it may over-trigger rasterization in some edge cases.

### Proposed fix

**Phase 1: Multiply group opacity into children.** When a group has `opacity < 1.0` and children don't overlap, multiply the group's opacity into each child's opacity before rendering. Currently this is skipped.

**Phase 2: Improve overlap detection.** Use rendered bounds rather than raw geometry bounds, including stroke width for lines and stroke-only shapes. Simple filled circle pairs use radius-based intersection to avoid diagonal bounding-box false positives. Future tightening can add exact shape intersection for more shape pairs to reduce unnecessary rasterization further.

### Files to modify
- `src/svg2ooxml/drawingml/writer.py` — `_render_group()`, multiply group opacity into children
- `src/svg2ooxml/drawingml/writer.py` — `_children_overlap()`, tighter detection

### Priority
Low-medium — only visible when semi-transparent shapes overlap. Most logos and diagrams don't hit this.

---

## Implementation Order

| Phase | Gap | Impact | Effort |
|-------|-----|--------|--------|
| 1 | Slide background detection | High — fixes most "wrong background" issues | Medium |
| 2 | Stroke width viewBox test | Medium — validates current behavior | Low |
| 3 | Group opacity multiplication | Medium — fixes opacity edge cases | Low |
| 4 | Fill inheritance audit | Low — already mostly working | Low |
| 5 | Non-scaling-stroke | Low — rare SVG feature | Medium |
| 6 | Overlap detection improvement | Low — optimization, not correctness | Medium |

## Exit Criteria

- Ghostscript Tiger: black background, correct ear rendering, matching whisker thickness
- EU flag: blue background, all 12 stars visible and correctly colored
- ProteoNic logo: smooth letter curves, correct text positioning
- No visual regression on W3C or resvg test suites
