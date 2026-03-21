# DrawingML Feature Gap Closure Specification

- **Status:** Draft
- **Date:** 2026-03-21
- **Relates to:** `docs/research/svg-to-drawingml-feature-map.md`,
  `docs/research/svg-to-drawingml-implementation-reality.md`
- **Roadmap item:** "Fill remaining DrawingML writer gaps" (v0.5.0)

## 1. Purpose

The feature map catalogues 89 Done/Direct rows and 83 Planned/Investigate rows.
This spec organises the 83 open items into prioritised waves, defines acceptance
criteria per wave, and establishes a triage policy for items that should be
deferred or dropped.

## 2. Guiding Principles

1. **Figma-first.** Prioritise features that appear in real Figma SVG exports.
   Long-tail SVG features that Figma never emits get lower priority.
2. **W3C gate green.** The animation gate currently fails 4/40 tests due to
   malformed timing XML. Fix schema violations before adding new features.
3. **Tier ladder.** Exhaust Tier 1–2 (native DrawingML) before reaching for
   EMF (Tier 3) or raster (Tier 4). EMF is a last-resort vector path.
4. **Traceable degradation.** Every skipped feature must emit a reason code via
   `ConversionTracer`. Silent drops are bugs.
5. **Stale map hygiene.** Update `svg-to-drawingml-feature-map.md` status as
   each item ships. Four rows are already stale (see §8).

## 3. Triage Categories

| Category | Meaning | Action |
|----------|---------|--------|
| **Wave 1** | Bugs and broken output — valid OOXML violations, wrong values | Fix immediately |
| **Wave 2** | High-impact gaps — features Figma exports or W3C corpus exercises | Implement next |
| **Wave 3** | Medium-impact — real SVG features with known Tier 2 solutions | Implement after Wave 2 |
| **Wave 4** | Low-impact / long-tail — rare features, complex EMF/raster paths | Backlog |
| **Defer** | Needs design decision or external dependency | Park with rationale |
| **Drop** | Not relevant for static PPTX or impossible without browser runtime | Close as won't-fix |

## 4. Wave 1 — Bugs & Schema Violations

Fix before any new features. These cause OpenXML validation failures or
visibly wrong output.

| # | Item | Problem | Resolution |
|---|------|---------|------------|
| 1.1 | ~~Animation timing schema errors~~ | ~~4/40 W3C tests fail~~ | **Done** — stale report. Re-validated all 4 SVGs with both Python `openxml-audit` and .NET Open XML SDK: 0 errors. Fixed during ADR-020 rewrite. |
| 1.2 | ~~Multi-keyframe rotate `by="0"`~~ | ~~`values="0;360;0"` produces `by="0"`~~ | **Done** — `_build_multi_keyframe_rotate` splits N angles into N-1 sequential `<p:animRot>` segments with proportional durations from key_times. 6 new tests added. |
| 1.3 | ~~Rotate center point~~ | ~~`values="0 40 40"` — cx/cy ignored~~ | **Done** — implemented companion `<p:animMotion>` orbital arc. When cx/cy differs from shape center, handler emits both `animRot` (spin) and `animMotion` (circular orbit) as simultaneous siblings. Element center populated via `_enrich_animations_with_element_centers` from scene graph bboxes. 7 tests added. |
| 1.4 | Mask effect XML | All four mask tiers return empty XML | **Moved to Wave 3** (items 3.15–3.18). Empty XML is intentional — `<a:mask>` is non-standard. The alpha shortcut path already works. Gradient/complex masks require design work. |

**Exit criteria:** ~~W3C animation gate passes 98%.~~ Gate was already passing —
stale report. Multi-keyframe rotate now produces correct segments. Mask
deferred to Wave 3.

## 5. Wave 2 — High-Impact Gaps

Features that appear in Figma exports or are exercised by the W3C corpus.

### 5A. Painting & Stroke

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 2.1 | `stroke-dashoffset` | 2 | Rotate dash/gap array entries by offset amount. Already parsed in IR — wire to `paint_runtime.py` dash writer |
| 2.2 | `paint-order: stroke fill` | 2 | Emit stroke as separate shape behind fill shape |
| 2.3 | `vector-effect: non-scaling-stroke` | 2 | Divide stroke-width by effective transform scale at emission time |

### 5B. Gradients

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 2.4 | `gradientUnits="userSpaceOnUse"` | 2 | Transform coordinates from userSpace to bbox-relative [0,1] |
| 2.5 | `gradientTransform` (pure rotation) | 2 | Decompose matrix → extract angle → set `<a:lin ang="...">` |
| 2.6 | `gradientTransform` (uniform scale) | 2 | Scale stop offset values proportionally |
| 2.7 | `gradientTransform` (non-uniform scale) | 2 | Scale positions + adjust angle for aspect ratio |
| 2.8 | `color-interpolation: linearRGB` | 2 | Pre-compute intermediate stops by sampling in linearRGB, convert to sRGB, insert 10–20 extra stops |
| 2.9 | Radial `fx`/`fy` (focal ≠ center) | 2 | Improve `fillToRect` approximation for moderate off-center; raster for extreme |

### 5C. Transforms

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 2.10 | `skewX(angle)` / `skewY(angle)` | 2 | Bake skew into custGeom path coordinates (multiply each point by skew matrix). Works for paths. |
| 2.11 | `matrix()` with skew | 2→3 | Decompose to translate+rotate+scale for `xfrm`, bake residual skew into geometry. EMF for images/groups. |

### 5D. Clipping

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 2.12 | `clip-path` on `<g>` (group) | 2 | Apply clip to each child individually |
| 2.13 | Nested `clip-path` | 2 | Boolean-intersect nested clips into single compound clip |
| 2.14 | `clipPathUnits="objectBoundingBox"` | 2 | Transform clip coordinates from [0,1] to shape bbox |

### 5E. Animation

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 2.15 | SkewX/SkewY animation | 2 | Approximate with sequential `<p:animScale>` pairs or bake into keyframe geometry snapshots |
| 2.16 | Multi-value animation keyframes | 2 | Split into chained sequential `<p:par>` sub-animations for rotate, scale |

**Exit criteria:** All Wave 2 items emit correct DrawingML or traced degradation.
`stroke-dashoffset` and `gradientTransform` produce visible output. Skew on
path geometry renders correctly in PowerPoint. Group clip paths work for
non-overlapping children.

## 6. Wave 3 — Medium-Impact Gaps

Real SVG features with known solutions but lower frequency in practice.

### 6A. Text

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 3.1 | Per-character `dx`/`dy` arrays | 2 | Split into individual single-character text boxes, absolutely positioned |
| 3.2 | Per-character `x`/`y` absolute arrays | 2 | Same as dx/dy |
| 3.3 | Per-character `rotate` | 2 | Individual rotated text boxes |
| 3.4 | `textLength` + `lengthAdjust="spacing"` | 2 | Compute effective letter-spacing → `spc` |
| 3.5 | `textLength` + `lengthAdjust="spacingAndGlyphs"` | 2→3 | Approximate with `spc` + font size adjustment |
| 3.6 | `font-stretch` | 2 | Select condensed/expanded font variant if available |
| 3.7 | `word-spacing` | 2 | Insert extra space chars or apply `spc` on space-character runs |
| 3.8 | `text-decoration: overline` | 2 | Draw thin line shape above baseline |
| 3.9 | `dominant-baseline` / `alignment-baseline` | 2 | Map to vertical offset on text position |
| 3.10 | `<textPath>` on arbitrary curve | 2→3 | Convert text glyphs to custGeom outlines positioned along path |
| 3.11 | `<textPath startOffset>` | 2 | Adjust glyph start position along path |
| 3.12 | `<textPath method="stretch">` | 2→3 | Warp custGeom glyph geometry along path curvature |
| 3.13 | `unicode-bidi: bidi-override` | 2 | Split mixed-direction runs into separate paragraphs |
| 3.14 | `xml:lang` / `lang` | 1 | Map BCP-47 tags to `lang` on `<a:rPr>` |

### 6B. Masking (beyond Wave 1 fix)

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 3.15 | `<mask>` gradient (linear alpha fade) | 2 | `gradFill` with varying `<a:alpha>` on stops |
| 3.16 | `<mask>` alpha mode | 2→4 | Alpha gradient approximation where possible, rasterize otherwise |
| 3.17 | `<mask>` complex vector content | 3→4 | EMF clip-path approximation for hard-edged; rasterize for soft |
| 3.18 | `maskContentUnits="objectBoundingBox"` | — | Transform coordinates to shape bbox |

### 6C. Patterns

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 3.19 | `patternUnits="userSpaceOnUse"` | 2 | Convert tile px → EMU, set `sx`/`sy` on `<a:tile>` |
| 3.20 | `patternUnits="objectBoundingBox"` | 2 | Scale tile dimensions based on shape bbox |
| 3.21 | `patternContentUnits="objectBoundingBox"` | 2 | Scale tile content to shape bbox proportionally |
| 3.22 | `patternTransform` (scale) | 2 | Map scale to tile `sx`/`sy` (× 100,000) |
| 3.23 | `patternTransform` (rotation) | 2→3 | Pre-rotate rasterized tile image before embedding |
| 3.24 | `patternTransform` (skew) | 2→3 | Pre-skew tile image |

### 6D. Filters

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 3.25 | `feGaussianBlur`+`feMerge` (glow) | 2 | Detect glow pattern → `<a:glow rad="...">` |
| 3.26 | `feColorMatrix(saturate)` | 2 | Map to `<a:satMod>` on solid fills |
| 3.27 | `feColorMatrix(hueRotate)` | 2 | Map to `<a:hueOff>` (approximate) |
| 3.28 | `feComponentTransfer(gamma)` on solid fills | — | Apply gamma to fill colors before emission |
| 3.29 | Filter on pure-geometry (no gradients) | — | Compute filter effect on fill colors, emit geometry with modified colors |

### 6E. Document Structure

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 3.30 | `<title>` / `<desc>` | 1 | Map to `<p:cNvPr descr="...">` |
| 3.31 | `overflow: visible` on nested `<svg>` | 2 | Skip viewport clipping |

### 6F. Compositing

| # | Feature | Tier | Approach |
|---|---------|------|----------|
| 3.32 | `opacity` on `<g>` (no overlap) | 2 | Detect non-overlapping children via bbox, apply `<a:alpha>` to each |
| 3.33 | `opacity` on `<g>` (with overlap) | 4 | Render group to PNG via resvg/Skia, embed as `blipFill` |

**Exit criteria:** Per-character text positioning works for at least `dx`/`dy`.
Gradient masks produce visible alpha fade. Pattern tile transforms apply
correctly. Glow filter detection works.

## 7. Wave 4 — Low-Impact / Long-Tail

These are real SVG features but rarely appear in practice, require complex
implementation, or can only be solved by raster fallback.

### 7A. Raster-Only (Tier 4)

| # | Feature | Why Tier 4 |
|---|---------|-----------|
| 4.1 | `mix-blend-mode` (all 16 values) | Neither DrawingML nor EMF supports CSS blend modes |
| 4.2 | `isolation: isolate` | Only matters with blend modes |
| 4.3 | `gradientTransform` (skew) | No gradient skew in DrawingML or EMF |

### 7B. Complex EMF (Tier 3)

| # | Feature | Why Tier 3 |
|---|---------|-----------|
| 4.4 | `clip-path` (complex/self-intersecting) | Boolean path intersection needed |
| 4.5 | `clip-rule: evenodd` | EMF `SetPolyFillMode(ALTERNATE)` |
| 4.6 | `<pattern>` with vector content | EMF DIB pattern brush |
| 4.7 | `<foreignObject>` | Headless browser render → EMF/PNG |
| 4.8 | Nested transforms with accumulated skew | Flatten full matrix at each leaf |
| 4.9 | `<image>` SVG (recursive) | Recursive conversion or rasterize |

### 7C. CSS Parsing

| # | Feature | Approach |
|---|---------|----------|
| 4.10 | `@media` queries | Evaluate at SVG viewport dimensions |
| 4.11 | `@import` | Fetch and merge imported stylesheets |
| 4.12 | CSS custom properties (`var()`) | Substitute during cascade |
| 4.13 | `calc()` | Evaluate during property resolution |

### 7D. Colour Spaces

| # | Feature | Approach |
|---|---------|----------|
| 4.14 | `oklab()` / `oklch()` (CSS Color 4) | Convert to sRGB at parse time |
| 4.15 | System colors | Map to sensible defaults |

### 7E. Remaining

| # | Feature | Tier | Notes |
|---|---------|------|-------|
| 4.16 | `stroke` gradient | 1→2→3 | Investigate: `gradFill` inside `<a:ln>` may work |
| 4.17 | `stroke` pattern | 2→3 | Stroke-to-fill expansion |
| 4.18 | `fill-rule: evenodd` | 1→3 | Investigate: compound subpath winding in DrawingML |
| 4.19 | `feTurbulence` → hybrid EMF | 3 | Rasterize noise tile → EMF DIB brush |
| 4.20 | `feDiffuseLighting` / `feSpecularLighting` | 2→3 | Try DrawingML 3D lighting first |
| 4.21 | `feFlood`+`feBlend(multiply)` | 2 | Investigate DrawingML duotone |
| 4.22 | Marker `overflow="visible"` | 2 | Don't clip marker custGeom to markerWidth/Height |
| 4.23 | Marker with gradient fill | 2 | Expanded marker inherits fill → `gradFill` |
| 4.24 | Marker with filter effect | 2→4 | Route through filter fallback ladder |
| 4.25 | `writing-mode: vertical-rl/lr` | 1 | Investigate: `vert`/`vert270` on `<a:bodyPr>` |
| 4.26 | `baseline-shift: super/sub` | 1 | Investigate: `baseline` on `<a:rPr>` |
| 4.27 | `font-variant: small-caps` | 1 | Investigate: `cap="small"` on `<a:rPr>` |
| 4.28 | `feColorMatrix(luminanceToAlpha)` | — | Pre-compute luminance → alpha per fill color |
| 4.29 | `color-interpolation-filters` | — | Affects filter rasterization color space |

**Exit criteria:** Items attempted as bandwidth allows. Raster-only items (4.1–4.3)
implemented via existing Tier 4 pipeline. Investigate items (4.16–4.18, 4.25–4.27)
tested in PowerPoint and GSlides — promote to Done or document as unsupported.

## 8. Map Hygiene — Stale Rows

These rows in `svg-to-drawingml-feature-map.md` are listed as Planned but are
already implemented. Update status to Done as part of Wave 1.

| Feature | Current status | Actual status | Evidence |
|---------|---------------|---------------|----------|
| `<textPath>` on simple curve | Planned | Done | WordArt classification in `text_coordinator.py:174` |
| `orient="auto-start-reverse"` | Planned | Done | `markers.py:195` |
| `<switch>` (systemLanguage, requiredFeatures) | Planned | Done | `switch_evaluator.py:18` |
| Hyperlinks (`<a xlink:href>`) | Planned | Partial | `navigation.py:183` — valid action URIs only |

## 9. Execution Order

```
Wave 1  ─── fix bugs, unblock W3C gate, emit mask XML
  │         estimated: 4 items, small scope each
  ▼
Wave 2  ─── high-impact: stroke, gradients, transforms, clips, animation
  │         estimated: 16 items, mix of small (dashoffset) and medium (skew)
  ▼
Wave 3  ─── medium-impact: text, masks, patterns, filters, compositing
  │         estimated: 33 items, many are Tier 2 arithmetic
  ▼
Wave 4  ─── long-tail: blend modes, CSS parsing, EMF edge cases
            estimated: 29 items, investigate-first or raster fallback
```

Each wave should end with:
1. Updated feature map status
2. All new code paths emit tracer reason codes
3. Tests (unit at minimum, golden master where output is deterministic)
4. W3C gate remains green

## 10. Test Strategy

| Wave | Test type | Criteria |
|------|-----------|----------|
| 1 | Golden master + `openxml-audit` | Gate passes 98%, mask produces output |
| 2 | Unit per feature + integration for transform/clip interactions | All new DrawingML validated |
| 3 | Unit per feature + visual spot-checks for text/pattern | PowerPoint opens without repair |
| 4 | Investigate items: manual PowerPoint + GSlides verification | Document viewer support matrix |

## 11. Non-Goals

- Full SMIL event runtime (see `animation-smil-parity-spec.md`)
- Browser-faithful `foreignObject` HTML rendering
- GDI+ EMF+ extensions (gradient brushes in EMF)
- SVG 2.0 features beyond CSS Color 4 colour functions
