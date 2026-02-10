# ADR-023: Fix Remaining OOXML Shape Schema Violations

- **Status:** Implemented
- **Date:** 2026-02-07
- **Owners:** svg2ooxml team
- **Depends on:** ADR-020 (animation writer rewrite — proved validation workflow)

## 1. Problem Statement

After eliminating all 88 animation schema violations (commit `72f353e`), full-corpus
validation of the 524 W3C SVG test files revealed **97 pre-existing schema errors** in
the DrawingML shape, effect, clipping, and masking code. These errors cause PowerPoint
to trigger repair dialogs on affected slides.

### 1.1 Error Census

Errors were found in two of the five W3C corpus batches:

| Batch | Slides | Errors | Categories |
|-------|--------|--------|------------|
| ab    | 106    | 12     | clipPath 1, clrChange 2, hsl 1, outerShdw 4, mask 2, effectLst 2 |
| ac    | 106    | 85     | clipPath 36, prstGeom 21, mask 14, headEnd 10, custGeom 4 |
| aa    | 106    | 0      | — |
| ad    | 106    | 0      | — |
| ae    | 102    | 0      | — |
| **Total** | **526** | **97** | |

### 1.2 Error Categories

| # | Category | Count | Affected Slides | ECMA-376 Violation |
|---|----------|-------|-----------------|-------------------|
| 1 | `clipPath` in `spPr` | 37 | ab:76, ac:38,39,43,44 | Element does not exist in CT_ShapeProperties |
| 2 | `prstGeom` ordering | 21 | ac:12,13,18,19,25,31 | Sequence broken by preceding non-standard element |
| 3 | `mask` in `spPr` | 16 | ab:97, ac:8,9,21,22,31 | Element does not exist in CT_ShapeProperties |
| 4 | `headEnd` in `ln` | 10 | ac:38,39,43 | Appears after `tailEnd`; schema requires headEnd first |
| 5 | `custGeom` ordering | 4 | ac:8,16,31 | Sequence broken by following non-standard element |
| 6 | `outerShdw` in `effectLst` | 4 | ab:33,50 | Ordering/duplication in merged effect chains |
| 7 | `clrChange` missing `clrFrom` | 2 | ab:18 | Required child element omitted |
| 8 | `effectLst` position | 2 | ab:50 | Knock-on from clipPath/mask breaking spPr sequence |
| 9 | `hsl` in `effectLst` | 1 | ab:18 | Not a valid child of CT_EffectList |

## 2. Root Cause Analysis

The 97 errors group into three independent families.

### 2.1 Family A — Non-Standard Elements in spPr (78 errors)

**Root cause:** The project invented `<a:clipPath>` and `<a:mask>` elements that do not
exist in ECMA-376. These are injected into `<p:spPr>` via template placeholders.

All four shape templates follow the same pattern:

```xml
<!-- assets/pptx_templates/shape_rectangle.xml (line 16) -->
{CLIP_PATH_XML}{MASK_XML}{FILL_XML}{STROKE_XML}{EFFECTS_XML}    </p:spPr>
```

The ECMA-376 CT_ShapeProperties sequence is:

```
xfrm, (custGeom | prstGeom), fill-group, ln, (effectLst | effectDag),
scene3d, sp3d, extLst
```

When `<a:clipPath>` or `<a:mask>` is inserted between geometry and fill, the validator
sees an unexpected element and reports both the non-standard element *and* the geometry
element as sequence violations. This explains the prstGeom (21) and custGeom (4)
"ordering" errors — they are cascading failures from the illegal elements.

**Generating code:**

| Element | Source | Function |
|---------|--------|----------|
| `<a:clipPath>` | `drawingml/clipmask.py:94` | `_clip_path_from_segments()` — builds raw XML string |
| `<a:clipPath>` | `drawingml/paint_runtime.py:178` | `clip_rect_to_xml()` — builds lxml element |
| `<a:mask>` | `drawingml/mask_writer.py:163` | `_build_vector_mask_fragment()` |
| `<a:mask>` | `drawingml/mask_writer.py:400` | `_build_blip_mask_fragment()` |

**Templates affected:** `shape_rectangle.xml`, `shape_preset.xml`, `shape_path.xml`,
`shape_line.xml` — all use `{CLIP_PATH_XML}{MASK_XML}` placeholders.

### 2.2 Family B — headEnd/tailEnd Ordering in ln (10 errors)

**Root cause:** `paint_runtime.py:stroke_to_xml()` appends `tailEnd` before `headEnd`.

```python
# paint_runtime.py lines 122-125 — WRONG ORDER
if tail_elem is not None:
    ln.append(tail_elem)
if head_elem is not None:
    ln.append(head_elem)
```

ECMA-376 CT_LineProperties requires: `..., headEnd, tailEnd, extLst`. The append order
must be reversed.

The same reversed order appears in the no-stroke branch (lines 67-70).

**Note:** `markers.py:marker_end_elements()` correctly returns `(head_elem, tail_elem)`.
The bug is purely in the append order at the call site.

### 2.3 Family C — Filter Effect Schema Violations (9 errors)

Three distinct bugs in the SVG filter-to-DrawingML conversion:

**2.3.1 clrChange missing clrFrom (2 errors)**

`filters/primitives/color_matrix.py:76` — the `saturate` branch creates `<a:clrChange>`
with only a `<a:clrTo>` child. ECMA-376 CT_ColorChangeEffect requires both `<a:clrFrom>`
and `<a:clrTo>`, in that order.

```python
# Current — missing clrFrom
clrChange = a_sub(effectLst, "clrChange")
clrTo = a_sub(clrChange, "clrTo")
srgbClr = a_sub(clrTo, "srgbClr", val="FFFFFF")
a_sub(srgbClr, "satMod", val=sat)
```

**2.3.2 hsl in effectLst (1 error)**

`filters/primitives/color_matrix.py:88` — the `hueRotate` branch places `<a:hsl>`
directly inside `<a:effectLst>`. The `<a:hsl>` element is not a valid child of
CT_EffectList. Valid children are: `blur, fillOverlay, glow, innerShdw, outerShdw,
prstShdw, reflection, softEdge`.

Additionally, the code creates `<a:hue>` as a child element of `<a:hsl>`, but
CT_HSLEffect takes `hue`, `sat`, `lum` as **attributes**, not child elements.

**2.3.3 outerShdw ordering/duplication (4 errors) + effectLst position (2 errors)**

When multiple SVG filter primitives are combined (e.g. feGaussianBlur + feOffset +
feDropShadow), each produces its own `<a:effectLst>`. The merger in
`shapes_runtime.py:_effect_block()` may produce duplicate `<a:outerShdw>` elements
(schema allows at most one) or place effects out of the required CT_EffectList sequence.

The effectLst position errors are a knock-on effect: when clipPath/mask elements precede
it in spPr, the validator cannot locate effectLst in the expected sequence position.

## 3. Fix Plan

### Phase 1: Quick Wins (19 errors) — Mechanical Code Changes

These are straightforward bugs with clear fixes that don't require architectural changes.

#### 1A. Reverse headEnd/tailEnd append order (10 errors)

**File:** `src/svg2ooxml/drawingml/paint_runtime.py`

Swap the append order in both branches of `stroke_to_xml()`:

```python
# Lines 67-70 (no-stroke branch) and 122-125 (stroke branch):
if head_elem is not None:
    ln.append(head_elem)
if tail_elem is not None:
    ln.append(tail_elem)
```

#### 1B. Add clrFrom to clrChange (2 errors)

**File:** `src/svg2ooxml/filters/primitives/color_matrix.py`

Add `<a:clrFrom>` before `<a:clrTo>` in the `saturate` branch. Use the original color
(pre-saturation) as the source:

```python
clrChange = a_sub(effectLst, "clrChange")
clrFrom = a_sub(clrChange, "clrFrom")
a_sub(clrFrom, "srgbClr", val="000000")  # black as source
clrTo = a_sub(clrChange, "clrTo")
srgbClr = a_sub(clrTo, "srgbClr", val="FFFFFF")
a_sub(srgbClr, "satMod", val=sat)
```

#### 1C. Fix hsl element usage (1 error)

**File:** `src/svg2ooxml/filters/primitives/color_matrix.py`

Replace the invalid `<a:hsl>` in effectLst with a valid approach. Two options:

- **Option A:** Use `<a:hsl hue="..." sat="0" lum="0"/>` as a color transform inside a
  `<a:srgbClr>` or as a group-level effect (not in effectLst).
- **Option B:** Drop the hueRotate DrawingML output entirely (return empty string) since
  CSS/SVG hue rotation has no direct OOXML equivalent in effectLst. Document the gap.

Recommend **Option B** — the current implementation doesn't produce correct visual results
anyway, and removing invalid XML is better than producing incorrect but schema-valid XML.

#### 1D. Fix outerShdw ordering and deduplication (4 + 2 = 6 errors)

**Files:** `src/svg2ooxml/drawingml/shapes_runtime.py`, filter primitives

- Ensure `_effect_block()` deduplicates outerShdw elements when merging filter outputs
  (keep last/most specific).
- Ensure effectLst children follow the required CT_EffectList order:
  `blur, fillOverlay, glow, innerShdw, outerShdw, prstShdw, reflection, softEdge`.

### Phase 2: Clip/Mask Architecture (78 errors) — Requires Design Work

These errors require a fundamental rearchitecture of how SVG clipping and masking map
to OOXML.

#### 2A. Remove non-standard elements from templates

Remove `{CLIP_PATH_XML}` and `{MASK_XML}` placeholders from all four shape templates.
This immediately eliminates the 78 schema violations.

#### 2B. Implement OOXML-compliant clipping

SVG `clip-path` has no direct equivalent in OOXML shape properties. Compliant approaches:

1. **Geometry intersection** — Compute the intersection of the shape geometry with the
   clip path, producing a single `<a:custGeom>` that represents the clipped shape. This
   is mathematically correct but complex (requires computational geometry for path
   boolean operations).

2. **Group-level clipping via extLst** — Some PowerPoint extensions support clipping at
   the group level. However, this is not part of the strict ECMA-376 schema and may not
   be supported by all consumers.

3. **Rasterization fallback** — For complex clip paths, rasterize the clipped shape to
   a PNG/EMF image and embed as `<p:pic>`. This preserves visual fidelity at the cost of
   editability. The project already has rasterization infrastructure (resvg bridge).

4. **Drop clip-path silently** — Remove the clip without visual compensation. Some SVGs
   use clip paths for minor cropping that may not be visually critical.

Recommend a **tiered approach**: use geometry intersection for simple rectangular clips
(common case), rasterization fallback for complex paths, and document the gap for
interactive clips.

#### 2C. Implement OOXML-compliant masking

SVG `mask` is even harder to map. OOXML has no per-shape alpha mask. Options:

1. **`<a:alphaModFix>` in effectLst** — Can set a fixed alpha level but cannot apply a
   spatially-varying mask.

2. **EMF fallback** — Embed the masked shape as an EMF image. The existing EMF bridge
   (`drawingml/emf_bridge.py`) already supports this pattern.

3. **Rasterization fallback** — Same as clipping: rasterize to PNG/EMF.

Recommend **rasterization/EMF fallback** for masked shapes, matching the existing
infrastructure pattern.

## 4. Testing Strategy

### Phase 1 Verification

1. Run full unit test suite (1798 tests) after each fix.
2. Rebuild the two affected W3C batches (ab and ac).
3. Re-validate with ooxml-validator — expect 0 errors on Phase 1 categories.
4. Spot-check affected SVGs in PowerPoint (no repair dialogs).

### Phase 2 Verification

1. Unit tests for new clipping/masking code paths.
2. Visual regression tests comparing before/after for clipped/masked SVGs.
3. Full W3C corpus rebuild and validation — target 0 errors across all 5 batches.
4. Manual PowerPoint verification for representative clipped/masked shapes.

## 5. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Phase 1 headEnd fix changes arrow rendering | Low — only affects arrow order, not appearance | Visual regression test on marker SVGs |
| Removing hueRotate output changes visual output | Low — current output is already incorrect | Document as known gap |
| Phase 2 geometry intersection is complex | High — boolean path ops are non-trivial | Start with rectangular clips (simplest case) |
| Phase 2 rasterization loses editability | Medium — shapes become images | Only use as fallback for complex cases |
| Phase 2 removes visual features | High — clipping/masking may disappear | Tiered approach ensures best-effort rendering |

## 6. Priority and Sequencing

| Phase | Errors Fixed | Effort | Dependencies |
|-------|-------------|--------|-------------|
| Phase 1 | 19 (20%) | Small — 1-2 hours | None |
| Phase 2 | 78 (80%) | Large — multi-day | Phase 1 (for clean validation baseline) |

Phase 1 should be implemented immediately. Phase 2 requires design spikes for geometry
intersection and rasterization fallback strategies.

## 7. Implementation Notes

### Phase 1C — Family C (9 errors) — Completed (commit `390b720`)

Filter effect schema violations fixed:
- `clrChange` — added required `<a:clrFrom>` child element
- `hsl` — removed invalid element from `<a:effectLst>` (documented as known gap)
- `outerShdw` — deduplicated and enforced CT_EffectList ordering

### Phase 1A — Family B headEnd/tailEnd (10 errors) — Completed

Swapped `headEnd`/`tailEnd` append order in both branches of
`paint_runtime.py:stroke_to_xml()` to match ECMA-376 CT_LineProperties sequence.

### Phase 2 — Family A clip/mask architecture (78 errors) — Completed

**Strategy:** Remove non-standard `<a:clipPath>` and `<a:mask>` elements entirely.
These elements are not defined in ECMA-376 and PowerPoint silently strips them during
repair. Replaced with schema-compliant approximations:

**Changes made:**

1. **Templates** — Removed `{CLIP_PATH_XML}{MASK_XML}` placeholders from all 7 shape
   templates (rectangle, preset, path, line, picture, text, wordart).

2. **Render pipeline** — Removed `clip_path_xml` and `mask_xml` parameters from the
   entire render chain: `writer.py` → `shape_renderer.py` → `shapes_runtime.py` →
   `image.py` → `text_renderer.py`.

3. **clipmask.py** — Replaced `clip_xml_for()` XML generation with `clip_bounds_for()`
   which returns clip bounding box for xfrm approximation. Removed all `<a:clipPath>`
   XML generation helpers. Legacy `clip_xml_for()` wrapper kept for backward
   compatibility (always returns empty string).

4. **mask_writer.py** — All fallback attempt methods (`_attempt_native`,
   `_attempt_mimic`, `_attempt_emf`, `_attempt_raster`) now return empty XML instead of
   `<a:mask>` fragments. EMF and raster assets are still registered for potential future
   use. Removed dead code: `_build_vector_mask_fragment()`,
   `_build_blip_mask_fragment()`, `_src_rect()`, `_to_thousandth_percent()`.

5. **Clip bounds approximation** — `clip_bounds_for()` extracts clip bounding box from
   `ClipRef.custom_geometry_bounds` or `ClipRef.bounding_box`. The bounds are stored in
   element metadata as `_clip_bounds` and applied in `shape_renderer.py` via rectangle
   intersection for `Rectangle` and `Image` elements using `dataclasses.replace()`.

6. **Marker clip** — `render_path()` no longer generates `<a:clipPath>` for
   `overflow:hidden` markers. The marker clipping visual effect is lost (documented
   as known gap).

**Schema-compliant strategies preserved:**
- **Alpha mask shortcut** — Modifies fill/stroke opacity directly (no XML element)
- **Hide strategy** — Sets element `opacity=0.0` (no XML element)

### Phase 3 — Native Clip Fidelity (Tricks 4, 5, 6) — Completed

Three ECMA-376 compliant mechanisms restore visual fidelity for clipped content
without reintroducing any schema violations.

**Trick 4: srcRect on pictures** — When an Image element has a rectangular clip,
`_apply_clip_bounds()` computes crop percentages (thousandths of percent) and stores
them as `_src_rect` in Image metadata. `render_picture()` formats these into
`<a:srcRect l="..." t="..." r="..." b="..."/>` inside `<p:blipFill>`. This is the
standard ECMA-376 mechanism for image cropping.

**Trick 5: Clip geometry on pictures ("crop to shape")** — The picture template
(`picture_shape.xml`) now uses `{GEOMETRY_XML}` instead of hardcoded `prst="rect"`.
When a ClipRef provides `custom_geometry_xml` (preset or custom geometry), it replaces
the default rectangle, enabling elliptical crops, rounded-rectangle crops, etc.

**Trick 6: EMF cutout overlay** — For Path elements with non-rectangular clip paths,
a white EMF overlay is generated using even-odd (ALTERNATE) polygon fill. Two contours
(outer bbox rectangle + inner clip path) create a transparent cutout where the clip
allows content and an opaque white frame elsewhere. The overlay is placed immediately
after the original shape as an additional `<p:pic>`.

**Files changed:**
- `assets/pptx_templates/picture_shape.xml` — `{SRC_RECT_XML}` + `{GEOMETRY_XML}`
- `src/svg2ooxml/drawingml/image.py` — `geometry_xml` param, srcRect formatting
- `src/svg2ooxml/drawingml/shape_renderer.py` — srcRect computation, geometry
  pass-through, `_maybe_clip_overlay()` method
- `src/svg2ooxml/drawingml/clip_overlay.py` — **NEW** `build_clip_overlay_emf()`

**Overlay limitations:**
- White overlay only works on white/solid backgrounds
- Overlay covers shapes behind the target (z-order)
- Complex bezier paths produce large EMFs after flattening

**Remaining visual gaps:**
- Non-alpha masks lose visual effect (geometry/pattern masks)
- Marker overflow clipping lost
- EMF overlay assumes white background

**Result:** 88 schema violations eliminated (78 clip/mask + 10 headEnd/tailEnd).
Combined with Family C fix (9 errors), all 97 pre-existing violations resolved.
Native clip fidelity restored for rectangular image crops, preset-geometry crops,
and non-rectangular path clips (via overlay).
