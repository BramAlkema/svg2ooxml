# DrawingML Feature Gap Closure Specification

- **Status:** Active
- **Date:** 2026-03-21 (revised)
- **Relates to:** `docs/reference/research/svg-to-drawingml-feature-map.md`
- **Roadmap item:** "Fill remaining DrawingML writer gaps" (v0.5.0)

## Current State

Feature map: **138 closed (80%) / 34 open (20%)** out of 172 total.
Validation: **524/525 W3C test SVGs pass** OpenXML validation.

The remaining 34 items split into non-text (9) and text (18) + CSS/color (7).
This section specs the 9 non-text items.

---

## Non-Text Gaps (9 items)

### NT-1. `<title>` / `<desc>` → `cNvPr descr`

**Tier 1 — direct mapping. Corpus: 15 SVGs.**

SVG `<title>` and `<desc>` child elements carry accessibility text. DrawingML
`<p:cNvPr>` accepts a `descr` attribute.

**Approach:**
1. In traversal hooks (`hooks.py:163`), when processing an element that has
   `<title>` or `<desc>` children, extract the text and store in
   `metadata["description"]`.
2. In the shape template formatting (shapes_runtime and templates), emit
   `descr="{DESCRIPTION}"` on `<p:cNvPr>` when present.

**Scope:** Parser hook + template placeholder. No IR changes needed — uses
existing metadata dict.

**Files:**
- `src/svg2ooxml/core/traversal/hooks.py` — extract title/desc text
- `src/svg2ooxml/assets/pptx_scaffold/*.xml` — add `{DESCRIPTION}` to templates
- `src/svg2ooxml/drawingml/shapes_runtime.py` — pass description through

---

### NT-2. `fr` (focal radius, SVG2)

**Tier 2 — stop insertion. Corpus: 0 SVGs.**

SVG2 `fr` attribute on `<radialGradient>` defines a focal circle radius.
DrawingML has no concept of focal radius — the gradient always starts from a
point.

**Approach:** Insert a flat-color stop (matching the first gradient color) from
offset 0 to `fr/r`, then map the remaining stops from `fr/r` to 1.0. This
produces a solid disc at the focal radius before the gradient begins.

**Where:** `_radial_gradient_to_fill_elem()` in `paint_runtime.py`, or in the
resvg gradient adapter where stops are prepared.

**Priority:** Low — SVG2 feature, zero corpus usage.

---

### NT-3. `paint-order: stroke fill markers`

**Tier 2 — shape duplication. Corpus: 0 SVGs.**

SVG default paint order is fill → stroke → markers. When `paint-order` reverses
this (e.g., `stroke fill`), the stroke renders behind the fill.

**Approach:**
1. Parse `paint-order` in style extraction (`style_extractor.py`).
2. Add `paint_order` field to IR `Path`/`Shape` metadata or as a dedicated field.
3. In the shape renderer, when paint order is reversed:
   - Emit two shapes at the same position: first a stroke-only shape
     (`<a:noFill/>` as shape fill), then a fill-only shape (`<a:ln><a:noFill/></a:ln>`).
   - Both share the same geometry.

**Complexity:** Medium — requires shape duplication in the renderer and careful
z-ordering. The stroke-only and fill-only paths already work (tested).

**Priority:** Low — zero corpus usage. Primarily matters for decorative text
outlines.

---

### NT-4. `vector-effect: non-scaling-stroke`

**Tier 2 — transform-aware scaling. Corpus: 0 SVGs.**

Keeps stroke width visually constant regardless of the element's transform
scale. Without this, a `stroke-width: 2` on a `scale(3)` element renders as
6px wide.

**Approach:**
1. Parse `vector-effect` in style extraction.
2. During IR conversion, when `vector-effect: non-scaling-stroke` is set,
   divide the stroke width by the effective transform scale before storing
   in the IR `Stroke` object.
3. Effective scale = `sqrt(abs(matrix.a * matrix.d - matrix.b * matrix.c))`
   (determinant-based uniform scale approximation).

**Complexity:** Small — one division during stroke extraction. The CTM is
already available at that point.

**Priority:** Low — zero corpus usage.

---

### NT-5. `opacity` on `<g>` (children overlap)

**Tier 4 — raster. Corpus: ~45 SVGs have group opacity, subset overlaps.**

When a group has opacity and its children overlap, applying per-child alpha
produces incorrect compositing (double-blending at overlap). The only correct
approach is to render the group to an offscreen buffer, then composite the
buffer with the specified opacity.

**Approach:**
1. Detect overlapping children via bounding box intersection.
2. When overlap is detected and group opacity < 1.0:
   - Rasterize the group via resvg/Skia to a PNG.
   - Embed as `<a:blipFill>` with `<a:alphaModFix amt="..."/>` for the opacity.
3. When no overlap: per-child alpha (already done).

**Complexity:** Medium — the rasterization pipeline exists but the overlap
detection and group-to-image conversion need wiring.

**Note:** The non-overlapping case is already handled (marked Done in map).
This item covers only the overlapping case.

---

### NT-6. `isolation: isolate`

**Tier 2→4. Corpus: 0 SVGs.**

Only matters when `mix-blend-mode` is in use. If no blend modes are present on
the isolated group's children, this property has no visual effect and can be
ignored.

**Approach:** Check if any descendant has a blend mode. If not, no-op. If yes,
rasterize the isolated group (same as NT-5).

**Priority:** Blocked by NT-7 (blend modes). No standalone value.

---

### NT-7. `mix-blend-mode`

**Tier 4 — raster only. Corpus: 0 SVGs.**

Neither DrawingML nor EMF supports CSS blend modes. All 16 values (multiply,
screen, overlay, darken, lighten, color-dodge, color-burn, hard-light,
soft-light, difference, exclusion, hue, saturation, color, luminosity) require
pre-compositing the blended result as a raster image.

**Approach:**
1. Parse `mix-blend-mode` in style extraction.
2. When a non-normal blend mode is detected, rasterize the element (and its
   backdrop) via resvg/Skia.
3. Embed as `<a:blipFill>`.

**Complexity:** High — requires backdrop capture, which means understanding the
stacking context. This is essentially a mini compositing engine.

**Priority:** Low — zero corpus usage, high complexity.

---

### NT-8. `<pattern>` with vector-only content

**Tier 3 — EMF DIB brush. Corpus: handled via raster tile.**

Pattern tiles with vector content are currently rasterized to PNG before
embedding as `<a:blipFill>` tiles. This item would instead render the tile as
an EMF with `CreateDIBPatternBrushPt`, preserving the vector wrapper.

**Approach:** Render pattern tile content to EMF via the existing EMF adapter,
then embed as an EMF DIB brush instead of a PNG tile.

**Priority:** Low — current raster tile approach works and passes validation.
EMF would improve print quality but not screen rendering.

---

### NT-9. `<foreignObject>`

**Tier 3→4. Corpus: 1 SVG.**

Embeds arbitrary HTML/XHTML inside SVG. Full rendering requires a headless
browser. Current code has a placeholder/simplification path for trivial cases.

**Approach:**
- Trivial content (text-only `<xhtml:p>`): extract text, emit as text shape.
- Complex content: rasterize via headless browser (Playwright/Puppeteer),
  embed as PNG.

**Complexity:** High — headless browser dependency. Not worth implementing
unless real-world usage demands it.

**Priority:** Very low — 1 corpus SVG, requires external dependency.

---

## Execution Priority

```
Quick wins (1-2 hours each):
  NT-1  title/desc → descr          (15 SVGs, Tier 1, small)
  NT-4  non-scaling-stroke           (0 SVGs, Tier 2, small)
  NT-2  fr focal radius              (0 SVGs, Tier 2, small)

Medium effort (half day each):
  NT-3  paint-order                  (0 SVGs, Tier 2, medium)
  NT-5  group opacity overlap        (subset of 45, Tier 4, medium)

Deferred (complex, low ROI):
  NT-6  isolation                    (blocked by NT-7)
  NT-7  mix-blend-mode               (Tier 4, high complexity, 0 SVGs)
  NT-8  pattern vector EMF           (current raster works fine)
  NT-9  foreignObject                (needs headless browser)
```

## Exit Criteria

- NT-1 through NT-4 implemented and tested.
- NT-5 implemented for detectable overlap cases.
- NT-6 through NT-9 documented as deferred with rationale.
- Feature map updated for each completed item.
- 524/525 validation rate maintained (or improved if slide-size fix lands).
