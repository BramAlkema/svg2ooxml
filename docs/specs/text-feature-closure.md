# Text Feature Closure Specification

- **Status:** Draft
- **Date:** 2026-03-21
- **Available tools:** Skia (rasterization), FontForge (glyph outlines, subsetting), librt/resvg (SVG rendering), WordArt classification pipeline
- **Feature map:** 16 text items remain open

## Available Infrastructure

| Tool | What it gives us |
|---|---|
| **FontForge** | Glyph outlines as bezier paths, font metrics (advances, ascent/descent), subsetting, WOFF2 decompression |
| **Skia** | Text shaping, per-glyph positioning, path rendering, `textBlobBuilder` for complex layouts |
| **WordArt** | `prstTxWarp` presets on `<a:bodyPr>` — existing classification pipeline matches SVG curves to presets |
| **EMF** | `ExtTextOut` with per-character `dx` arrays, `SetWorldTransform` for rotation/scale per glyph |
| **custGeom** | Convert text glyphs to vector outlines — scalable, exact positioning, no editability |

## Strategy

Three rendering tiers for text, chosen per feature:

1. **Native DrawingML** — `<a:rPr>` attributes, live editable text
2. **custGeom outlines** — FontForge extracts glyph paths, positioned via Skia metrics. Scalable vector, not editable.
3. **EMF fallback** — complex per-character positioning via `ExtTextOut`

WordArt (`prstTxWarp`) is preferred for `textPath` when the curve matches a preset — already implemented. For arbitrary curves, fall through to custGeom outlines.

## Items

### T-1. `writing-mode: vertical-rl/lr` (6 SVGs, Tier 1)

**Approach:** Parse `writing-mode` from SVG element/CSS. Set `vert="vert"` (tb-rl) or `vert="vert270"` (tb-lr) on `<a:bodyPr>`. Already detected by layout analyzer — currently triggers EMF fallback. Wire to native DrawingML attribute instead.

**Where:** `text_converter.py` extracts writing-mode → store on TextFrame metadata. `shapes_runtime.py` template emits `vert` on `<a:bodyPr>`.

**Complexity:** Small — same pattern as `xml:lang` wiring.

### T-2. `word-spacing` (1 SVG, Tier 2)

**Approach:** Already on IR Run (`word_spacing` field). Emit as extra `spc` on space-character runs, or insert extra space characters proportional to the word-spacing value.

**Where:** `run_fragment()` in `shapes_runtime.py`. When `word_spacing` is set, split text at spaces, emit each word as a separate `<a:r>`, insert space runs with inflated `spc`.

**Complexity:** Small-medium — text splitting + spacing math.

### T-3. `dominant-baseline` / `alignment-baseline` (0 SVGs, Tier 2)

**Approach:** Map SVG baseline values to vertical position offsets:
- `central` / `middle` → shift by half ascent
- `hanging` → shift by ascent
- `text-bottom` → shift by descent
- `alphabetic` → default (no shift)

Apply as y-offset on the TextFrame origin during IR conversion.

**Where:** `text_converter.py` — adjust `origin_y` based on baseline value and font metrics (from FontForge or Skia).

**Complexity:** Small — arithmetic offset using font metrics.

### T-4. `text-decoration: overline` (0 SVGs, Tier 2)

**Approach:** DrawingML has no overline. Emit a separate thin line shape positioned above the text baseline. Line width matches the text's stroke-width or 1px. Position = origin_y - ascent.

**Where:** Shape renderer — after emitting the text shape, if overline is requested, emit an additional `<p:cxnSp>` (line shape) at the computed position.

**Complexity:** Small — one extra shape.

### T-5. `font-stretch` (0 SVGs, Tier 2)

**Approach:** FontForge can select condensed/expanded font variants by name. Map SVG `font-stretch` values (condensed, expanded, etc.) to font family suffixes. If the variant exists, use it. Otherwise no-op.

**Where:** `text_converter.py` — append width suffix to font family query before font resolution.

**Complexity:** Small — string manipulation on font family name.

### T-6. Per-character `dx`/`dy` arrays (13 SVGs, Tier 2→3)

**Approach — Tier 2 (custGeom outlines):**
1. Use FontForge to extract glyph outlines as bezier paths
2. Use Skia `textBlobBuilder` or FontForge metrics to get per-glyph advances
3. Apply cumulative dx/dy offsets to each glyph's position
4. Emit each glyph as a custGeom path at the computed position

**Approach — Tier 3 (EMF):**
EMF `ExtTextOut` natively supports per-character `dx` array (character widths). Already available via EMF adapter.

**Where:** New `_render_positioned_text()` in text pipeline. Triggered when `dx`/`dy` attributes present on `<text>` or `<tspan>`.

**Complexity:** Medium — glyph extraction + positioning pipeline.

### T-7. Per-character `x`/`y` absolute arrays (same as T-6)

**Approach:** Same infrastructure as T-6 but with absolute positioning instead of cumulative offsets. Each glyph placed at `(x[i], y[i])`.

**Shares implementation with T-6.**

### T-8. Per-character `rotate` (10 SVGs, Tier 2→3)

**Approach — Tier 2 (custGeom outlines):**
Same as T-6 but each glyph's bezier paths are rotated by the specified angle before positioning. FontForge extracts outlines, apply rotation matrix per glyph, emit as custGeom.

**Approach — Tier 3 (EMF):**
EMF `SetWorldTransform` per character + `ExtTextOut`. Set rotation matrix before each character draw.

**Complexity:** Medium — builds on T-6 infrastructure + rotation transform.

### T-9. `textLength` + `lengthAdjust="spacing"` (3 SVGs, Tier 2)

**Approach:** Compute effective letter-spacing = `(textLength - natural_width) / (char_count - 1)`. Emit as `spc` attribute on `<a:rPr>`.

Natural width from Skia `measureText()` or FontForge advance widths.

**Where:** `text_converter.py` — compute spacing, set on Run.

**Complexity:** Small — one division + Skia/FontForge metric query.

### T-10. `textLength` + `lengthAdjust="spacingAndGlyphs"` (same SVGs, Tier 2→3)

**Approach — Tier 2:** Approximate with `spc` + font size scaling. Compute scale factor = `textLength / natural_width`. If close to 1.0, use `spc` only. If significantly different, also scale font size.

**Approach — Tier 3 (custGeom):** Extract glyph outlines, apply horizontal scale transform, position at correct widths.

**Complexity:** Small (Tier 2 approx) to Medium (Tier 3 exact).

### T-11. `<textPath>` on arbitrary curve (5 SVGs, Tier 2→3)

**Approach — WordArt (preferred):**
Existing `CurveTextPositioner` classifies SVG path against `prstTxWarp` presets. When confidence > threshold, emit `prstTxWarp` on `<a:bodyPr>`. **Already implemented** for simple curves — this item covers arbitrary curves that don't match presets.

**Approach — Tier 2 (custGeom outlines):**
1. Sample the SVG path at regular intervals using existing `PathSamplingMethod`
2. Use FontForge to get glyph outlines and advance widths
3. Place each glyph tangent to the path at its position
4. Emit as custGeom path elements

**Approach — Tier 3 (EMF):**
Same glyph placement but rendered via EMF path outlines with `SetWorldTransform` for per-glyph rotation.

**Complexity:** Medium-high — path sampling + glyph placement math.

### T-12. `<textPath startOffset>` (same SVGs, Tier 2)

**Approach:** Shift the starting position along the path by `startOffset` before placing glyphs. Uses the same path sampling infrastructure as T-11.

**Shares implementation with T-11.**

### T-13. `<textPath method="stretch">` (same SVGs, Tier 2→3)

**Approach:** Warp each glyph's outline along the path curvature. More complex than simple tangent placement — each glyph's bezier control points are deformed to follow the curve.

**Complexity:** High — bezier warping. Defer until T-11 is solid.

### T-14. `unicode-bidi: bidi-override` (2 SVGs, Tier 2)

**Approach:** Force explicit character order by splitting text into individual character runs with explicit direction. Each run is a separate `<a:r>` with the overridden direction.

**Where:** `text_converter.py` — detect `unicode-bidi: bidi-override`, split text into per-character runs with forced direction.

**Complexity:** Small-medium — character splitting + RTL attributes.

## Execution Order

```
Batch 1 — Quick attribute wiring (T-1, T-2, T-3, T-4, T-5, T-9):
  writing-mode vert, word-spacing, baselines, overline,
  font-stretch, textLength spacing
  Estimated: each 1-2 hours, no new infrastructure

Batch 2 — Glyph outline pipeline (T-6, T-7, T-8):
  Per-character dx/dy, x/y, rotate
  Requires: FontForge glyph extraction + Skia metrics
  Estimated: 1 day for shared infrastructure, then each feature quick

Batch 3 — Text path (T-11, T-12, T-13):
  Arbitrary curve text, startOffset, stretch
  Requires: path sampling + glyph placement from Batch 2
  WordArt classification handles simple cases already
  Estimated: 1-2 days

Batch 4 — Edge cases (T-10, T-14):
  spacingAndGlyphs, bidi-override
  Can use infrastructure from Batch 1-2
```

## Exit Criteria

- All 6 writing-mode SVGs render with `vert` attribute
- All 13 dx/dy SVGs render with positioned glyphs (custGeom or EMF)
- All 5 textPath SVGs render (WordArt for matches, custGeom for rest)
- All 10 per-char rotate SVGs render with rotated glyphs
- Feature map text items updated to Done
- 524/525 validation rate maintained
