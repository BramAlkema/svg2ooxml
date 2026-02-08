# SVG → DrawingML Feature Map

Exhaustive catalog of every SVG feature, its DrawingML equivalent or closest
substitute, and which fallback tier applies when native DrawingML is insufficient.
This is the reference document for deciding how to handle any SVG construct in
svg2ooxml.

---

## Fallback Ladder

Every SVG feature is resolved through this ladder, top to bottom. We never skip
to a lower tier without exhausting all higher tiers first.

| Tier | Format | Scalable | Editable | When to use |
|------|--------|----------|----------|-------------|
| **1. Native DrawingML** | OOXML elements | Yes | Yes | Direct mapping exists |
| **2. DrawingML mimic** | OOXML elements (creative use) | Yes | Yes | No direct mapping, but a combination of DrawingML constructs can approximate the visual result |
| **3. EMF vector** | Enhanced Metafile records | Yes | Limited | DrawingML cannot represent it at all, but EMF's GDI primitives can |
| **4. PNG raster** | Embedded bitmap | No | No | Neither DrawingML nor EMF can represent it |

### EMF Capabilities & Limitations

Our EMF path (`io/emf/blob.py`) is procedurally generated — no external renderer
needed. It supports:

**EMF can do:**
- Full 2D affine transforms including skew (`SetWorldTransform`)
- Arbitrary clip paths with combine modes (`SelectClipPath`, intersect/union/XOR)
- Fill rules: even-odd (alternate) and non-zero (winding)
- Complex paths: polygons, polylines, polypolylines, bezier curves
- Custom dash patterns with offset
- Hatch brushes (6 patterns) and DIB pattern brushes (embedded bitmap tiles)
- Save/restore graphics state (`SaveDC`/`RestoreDC`)
- Stroke styles: width, cap, join, miter limit, dash array

**EMF cannot do:**
- Gradients (no `LinearGradientBrush` in our EMF records — would need GDI+ EMF+ extension or tesselation)
- Per-shape opacity / alpha blending (brushes are opaque)
- Blend modes (no compositing operators beyond basic ROP codes)
- Text rendering (supported by EMF spec but we convert text→paths)

This means EMF is the right fallback for **geometry, clipping, and transform**
problems, but not for **paint, compositing, or gradient** problems.

---

## Status Key

- **Direct** — direct DrawingML equivalent exists, implemented
- **Done** — mimic or fallback implemented in svg2ooxml
- **Planned** — substitute identified, not yet implemented
- **Investigate** — may work but needs testing/verification
- **Ignore** — not relevant for static PPTX output

Each non-Direct entry specifies which fallback tier(s) apply.

---

## 1. Painting & Stroke

### 1.1 Fill

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `fill` solid color | `solidFill` | Direct | — | |
| `fill` linear gradient | `gradFill` with `lin` | Direct | — | |
| `fill` radial gradient | `gradFill` with `path` | Direct | — | |
| `fill` pattern (preset) | `pattFill` | Done | — | Matches DrawingML preset patterns |
| `fill` pattern (complex) | `blipFill` with `<a:tile>` | Done | Tier 2 | Rasterize pattern tile to PNG, tile across shape |
| `fill: none` | No fill element | Direct | — | |
| `fill-opacity` | `<a:alpha>` on fill color | Direct | — | |
| `fill-rule: nonzero` | Default winding in custGeom | Direct | — | |
| `fill-rule: evenodd` | Compound subpaths in single `<a:path>` | Investigate | Tier 1→3 | DrawingML compound paths should use alternate fill. If PPT/GSlides don't honor it, EMF supports `SetPolyFillMode(ALTERNATE)` natively. |
| `color` / `currentColor` | Resolved at parse time | Direct | — | Substituted before DrawingML emission |

### 1.2 Stroke

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `stroke` solid | `<a:ln>` with `solidFill` | Direct | — | |
| `stroke` gradient | `<a:ln>` with `gradFill` | Investigate | Tier 1→2→3 | DrawingML spec allows `gradFill` inside `<a:ln>`. If renderers ignore it: **Tier 2** — expand stroke to filled custGeom path, apply gradient to the resulting shape's fill. If that's too complex: **Tier 3** — EMF doesn't support gradients either, so stroke-to-fill expansion is the only vector path. |
| `stroke` pattern | `<a:ln>` with `pattFill`/`blipFill` | Investigate | Tier 2→3 | Likely unsupported in renderers. **Tier 2** — stroke-to-fill expansion, apply pattern to resulting shape. **Tier 3** — EMF supports DIB pattern brushes on pens natively. |
| `stroke-width` | `<a:ln w="...">` (EMUs) | Direct | — | |
| `stroke-linecap: butt` | `cap="flat"` | Direct | — | |
| `stroke-linecap: round` | `cap="rnd"` | Direct | — | |
| `stroke-linecap: square` | `cap="sq"` | Direct | — | |
| `stroke-linejoin: miter` | `<a:miter>` child of `<a:ln>` | Direct | — | |
| `stroke-linejoin: round` | `<a:round>` child of `<a:ln>` | Direct | — | |
| `stroke-linejoin: bevel` | `<a:bevel>` child of `<a:ln>` | Direct | — | |
| `stroke-miterlimit` | `<a:miter lim="...">` | Direct | — | Value × 100,000 |
| `stroke-dasharray` | `<a:custDash>` with `<a:ds d="..." sp="...">` | Direct | — | |
| `stroke-dashoffset` | **No DrawingML equivalent** | Planned | Tier 2→3 | **Tier 2** — rotate the dash/gap array: consume offset from first dash length, shift remaining entries. Pure arithmetic, zero visual loss. **Tier 3** — EMF custom dash patterns support offset natively. |
| `stroke-opacity` | `<a:alpha>` on stroke fill | Direct | — | |
| `paint-order: stroke fill markers` | **No DrawingML equivalent** — always fill-then-stroke | Planned | Tier 2 | Emit stroke as a separate shape behind the fill shape (two shapes). |
| `vector-effect: non-scaling-stroke` | **No DrawingML equivalent** | Planned | Tier 2 | Divide `stroke-width` by effective transform scale. Exact at authored zoom. |

### 1.3 Opacity

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `opacity` on element | `<a:alpha>` on fill AND stroke | Direct | — | |
| `opacity` on `<g>` (no child overlap) | Individual child `<a:alpha>` | Planned | Tier 2 | Detect non-overlapping children via bbox intersection. Apply alpha to each child. Visually identical when no overlap. |
| `opacity` on `<g>` (children overlap) | **No DrawingML or EMF group alpha** | Planned | Tier 4 | EMF has no per-shape opacity either. Must render group to PNG via resvg/Skia, embed as `blipFill` with `<a:alpha>`. Loses editability for that group. |
| `isolation: isolate` | **No equivalent** | Planned | Tier 2→4 | Only matters with blend modes. If no blend modes present, ignore. Otherwise, rasterize the isolated group (Tier 4). |

### 1.4 Blend Modes

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `mix-blend-mode` (all values) | **No DrawingML or EMF support** | Planned | Tier 4 | Neither DrawingML nor EMF supports CSS blend modes. Pre-composite the blended result as PNG. Applies to: `multiply`, `screen`, `overlay`, `darken`, `lighten`, `color-dodge`, `color-burn`, `hard-light`, `soft-light`, `difference`, `exclusion`, `hue`, `saturation`, `color`, `luminosity`. |

---

## 2. Gradients

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<linearGradient>` | `<a:gradFill>` with `<a:lin>` | Direct | — | |
| `<radialGradient>` | `<a:gradFill>` with `<a:path>` | Direct | — | |
| `<stop stop-color="..." offset="...">` | `<a:gs pos="...">` in `<a:gsLst>` | Direct | — | |
| `stop-opacity` | `<a:alpha>` on gradient stop color | Direct | — | |
| `gradientUnits="objectBoundingBox"` | Default DrawingML behavior | Direct | — | |
| `gradientUnits="userSpaceOnUse"` | **No direct mapping** | Planned | Tier 2 | Transform coordinates from userSpace to bbox-relative [0,1] range. Exact when gradient covers the shape. EMF has no gradients so Tier 3 is not useful here. |
| `gradientTransform` (pure rotation) | `<a:lin ang="...">` | Planned | Tier 2 | Decompose matrix → extract rotation → set `ang`. Exact. |
| `gradientTransform` (uniform scale) | Adjust stop positions | Planned | Tier 2 | Scale stop `offset` values proportionally. Exact. |
| `gradientTransform` (non-uniform scale) | Adjust stops + direction | Planned | Tier 2 | Scale positions and adjust angle for aspect ratio. Close approximation. |
| `gradientTransform` (skew) | **No DrawingML or EMF equivalent** | Planned | Tier 2→4 | **Tier 2** — decompose to closest rotation + adjusted stops. Lossy for strong skews. **Tier 4** — for extreme skews, rasterize the gradient region as PNG. EMF has no gradients so Tier 3 doesn't help. |
| `spreadMethod="pad"` | Default DrawingML behavior | Direct | — | |
| `spreadMethod="reflect"` | Expand stops in `gsLst` | Done | Tier 2 | Mirror gradient stops to fill [0,1]. |
| `spreadMethod="repeat"` | Expand stops in `gsLst` | Done | Tier 2 | Duplicate stops N times to fill [0,1]. |
| `fx`/`fy` (focal point ≠ center) | **Limited mapping** | Planned | Tier 2 | Approximate by shifting `fillToRect` values. Lossy for extreme off-center. EMF has no gradients. |
| `fr` (focal radius, SVG2) | **No DrawingML concept** | Planned | Tier 2 | Add flat-color stop from center to `fr`, then gradient from `fr` to `r`. |
| `color-interpolation: linearRGB` | **DrawingML uses sRGB** | Planned | Tier 2 | Pre-compute intermediate stops by sampling in linearRGB, convert to sRGB, insert as explicit stops. 10–20 extra stops ≈ indistinguishable. |

---

## 3. Transforms

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `translate(tx, ty)` | `<a:off x="..." y="...">` | Direct | — | |
| `rotate(angle)` | `<a:xfrm rot="...">` | Direct | — | Degrees × 60,000 |
| `scale(sx, sy)` | `<a:ext cx="..." cy="...">` | Direct | — | |
| `skewX(angle)` | **No `xfrm` skew** | Planned | Tier 2→3 | **Tier 2** — bake skew into custGeom path coordinates (multiply each point by skew matrix). Exact for paths. **Tier 3** — EMF supports `SetWorldTransform` with full affine matrix including skew. Use for complex cases (images, groups). |
| `skewY(angle)` | **No `xfrm` skew** | Planned | Tier 2→3 | Same as `skewX`. |
| `matrix(a,b,c,d,e,f)` (no skew) | Decompose to translate+rotate+scale | Direct | — | |
| `matrix(a,b,c,d,e,f)` (with skew) | Decompose + bake residual | Planned | Tier 2→3 | **Tier 2** — extract translate+rotate+scale into `xfrm`, bake residual skew into geometry. **Tier 3** — EMF `SetWorldTransform` handles full matrix natively for complex element types. |
| Nested transforms with accumulated skew | Skew compounds non-linearly | Planned | Tier 2→3 | Flatten full transform matrix at each leaf, then decompose. |

---

## 4. Clipping

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `clip-path` (rectangle) | DrawingML shape clipping | Direct | — | |
| `clip-path` (simple path) | DrawingML `custGeom` clip | Done | — | |
| `clip-path` (complex/self-intersecting) | **Limited in DrawingML** | Planned | Tier 2→3 | **Tier 2** — boolean path intersection (Clipper2): intersect clip with shape geometry → new custGeom. **Tier 3** — EMF `SelectClipPath` handles arbitrary paths natively including self-intersecting and complex topology. |
| `clip-path` on `<g>` (group) | **DrawingML clips individual shapes** | Planned | Tier 2→3 | **Tier 2** — apply clip to each child individually. **Tier 3** — EMF supports clip on graphics state, affecting all subsequent drawing. Group-level clip is natural in EMF. |
| Nested `clip-path` | **DrawingML: one clip per shape** | Planned | Tier 2→3 | **Tier 2** — intersect nested clips into single compound clip (boolean intersection). **Tier 3** — EMF supports `IntersectClipRect` and `SelectClipPath` with combine modes: can intersect, union, XOR clip regions. Native nested clips. |
| `clip-rule: evenodd` | Winding rule on clip geometry | Planned | Tier 1→3 | **Tier 1** — set correct winding on custGeom subpaths. **Tier 3** — EMF `SetPolyFillMode(ALTERNATE)` for the clip path. |
| `clip-rule: nonzero` | Default winding | Direct | — | |
| `clipPathUnits="objectBoundingBox"` | Coordinates in [0,1] | Planned | Tier 2 | Transform clip coordinates from [0,1] to shape bbox. |
| `clipPathUnits="userSpaceOnUse"` | Default | Direct | — | |

---

## 5. Masking

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<mask>` uniform opacity (solid rect) | Multiply alpha onto shape fill | Done | Tier 2 | Detect single-rect uniform opacity → `<a:alpha>`. |
| `<mask>` gradient (linear alpha fade) | **No DrawingML mask** | Planned | Tier 2→4 | **Tier 2** — approximate with DrawingML alpha gradient: `gradFill` with varying `<a:alpha>` on stops. Works when mask is a simple linear gradient. **Tier 3** — EMF has no alpha/opacity. **Tier 4** — rasterize composited result for complex gradient masks. |
| `<mask>` alpha mode | **No DrawingML mask** | Planned | Tier 2→4 | Same strategy as luminance — alpha gradient approximation where possible (Tier 2), rasterize otherwise (Tier 4). EMF can't help (no alpha). |
| `<mask>` with complex vector content | **No DrawingML mask** | Planned | Tier 3→4 | **Tier 3** — EMF can represent the masked vector content using clip paths as an approximation (clip to mask boundary). Lossy for soft-edged masks. **Tier 4** — rasterize for pixel-accurate mask compositing. |
| `<mask>` with mixed content | **No DrawingML mask** | Done | Tier 3→4 | Current mask_writer routes through EMF (Tier 3) then raster (Tier 4) based on policy. |
| `mask-type: luminance` vs `alpha` | Affects compositing channel | Planned | — | Handled in mask analysis: luminance converts RGB→grayscale alpha, alpha uses alpha channel directly. Affects which rasterization approach is used. |
| `maskContentUnits="objectBoundingBox"` | Coordinates in [0,1] | Planned | — | Transform mask content coordinates to shape bbox before applying chosen fallback. |

---

## 6. Patterns

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<pattern>` matching preset | `<a:pattFill>` | Done | Tier 1 | |
| `<pattern>` complex content | `<a:blipFill>` with `<a:tile>` | Done | Tier 2 | Rasterize tile to PNG, embed as media, tile. |
| `<pattern>` with vector-only content | EMF DIB pattern brush | Planned | Tier 3 | **Tier 3** — EMF supports `CreateDIBPatternBrushPt` with embedded bitmap tiles AND hatch brushes for simple patterns. Could render pattern tile → small bitmap → EMF DIB brush. Preserves vector wrapper. |
| `patternUnits="objectBoundingBox"` | Tile size relative to shape | Planned | Tier 2 | Scale tile dimensions based on shape bbox. |
| `patternUnits="userSpaceOnUse"` | Tile size in absolute units | Planned | Tier 2 | Convert tile px → EMU, set `sx`/`sy` on `<a:tile>`. |
| `patternContentUnits="objectBoundingBox"` | Content scaled to bbox | Planned | Tier 2 | Scale tile content to shape bbox proportionally. |
| `patternTransform` (scale) | `<a:tile sx="..." sy="...">` | Planned | Tier 2 | Map scale to tile `sx`/`sy` (× 100,000). |
| `patternTransform` (rotation) | **No tile rotation in DrawingML** | Planned | Tier 2→3 | **Tier 2** — pre-rotate the rasterized tile image before embedding. **Tier 3** — EMF `SetWorldTransform` can rotate the pattern brush coordinate system. |
| `patternTransform` (skew) | **No tile skew** | Planned | Tier 2→3 | **Tier 2** — pre-skew tile image. **Tier 3** — EMF affine transform on brush. |

---

## 7. Text

### 7.1 Font & Style Properties

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `font-family` | `<a:latin typeface="...">`, `<a:ea>`, `<a:cs>` | Direct | — | |
| `font-size` | `sz` on `<a:rPr>` (hundredths of pt) | Direct | — | |
| `font-weight: bold` | `b="1"` on `<a:rPr>` | Direct | — | |
| `font-weight` (numeric 100–900) | `b="1"` for ≥600 | Direct | — | Binary bold. Intermediate weights → font variant selection. |
| `font-style: italic` | `i="1"` on `<a:rPr>` | Direct | — | |
| `font-style: oblique` | `i="1"` on `<a:rPr>` | Direct | — | No oblique vs italic distinction. |
| `font-variant: small-caps` | `cap="small"` on `<a:rPr>` | Investigate | Tier 1 | Verify rendering in PPT/GSlides. |
| `font-stretch` | **No DrawingML font width** | Planned | Tier 2 | Select condensed/expanded font variant if available. Otherwise no substitute. |
| `text-decoration: underline` | `u="sng"` on `<a:rPr>` | Done | — | |
| `text-decoration: line-through` | `strike="sngStrike"` on `<a:rPr>` | Done | — | |
| `text-decoration: overline` | **No DrawingML overline** | Planned | Tier 2→3 | **Tier 2** — draw separate thin line shape above baseline. **Tier 3** — EMF `Polyline` positioned above text. |
| `letter-spacing` | `spc` on `<a:rPr>` | Done | — | |
| `word-spacing` | **No DrawingML attribute** | Planned | Tier 2 | Insert extra space chars or apply `spc` on space-character runs. |

### 7.2 Text Layout & Positioning

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `text-anchor: start/middle/end` | `algn` on `<a:pPr>` | Direct | — | |
| `direction: rtl` | `rtl="1"` on `<a:pPr>` | Done | — | |
| `writing-mode: vertical-rl` | `vert="vert"` on `<a:bodyPr>` | Investigate | Tier 1 | Verify CJK rendering. |
| `writing-mode: vertical-lr` | `vert="vert270"` on `<a:bodyPr>` | Investigate | Tier 1 | |
| `dominant-baseline` | **Limited vertical alignment** | Planned | Tier 2 | Map to vertical offset on text position. Approximate. |
| `alignment-baseline` | **Limited** | Planned | Tier 2 | Same. |
| `baseline-shift: super` | `baseline` on `<a:rPr>` | Investigate | Tier 1 | DrawingML `baseline` attribute (% of font size). |
| `baseline-shift: sub` | `baseline` on `<a:rPr>` | Investigate | Tier 1 | Same. |
| Per-character `dx`/`dy` arrays | **No per-char offset in DrawingML** | Planned | Tier 2→3 | **Tier 2** — split into individual single-character text boxes, absolutely positioned. Preserves appearance, loses text editability. **Tier 3** — EMF can record text with per-character `dx` array via `ExtTextOut` with character widths. Native per-character positioning. |
| Per-character `x`/`y` absolute arrays | **No per-char absolute positioning** | Planned | Tier 2→3 | Same as `dx`/`dy`. **Tier 3** — EMF `ExtTextOut` calls per character with absolute positions. |
| Per-character `rotate` | **No per-glyph rotation** | Planned | Tier 2→3 | **Tier 2** — individual rotated text boxes. **Tier 3** — EMF `SetWorldTransform` rotation per character + `ExtTextOut`. Or convert to custGeom outlines (Tier 2) / EMF path outlines (Tier 3). |
| `textLength` + `lengthAdjust="spacing"` | **No text length forcing** | Planned | Tier 2 | Compute effective `letter-spacing` → `spc`. |
| `textLength` + `lengthAdjust="spacingAndGlyphs"` | **No glyph scaling** | Planned | Tier 2→3 | **Tier 2** — approximate with `spc` + font size adjustment. **Tier 3** — EMF `SetWorldTransform` with non-uniform scale on text. |

### 7.3 Text Path

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<textPath>` on simple curve | `prstTxWarp` on `<a:bodyPr>` | Planned | Tier 2 | Classify path against WordArt presets. If match → editable text with warp. Beats PPT. |
| `<textPath>` on arbitrary curve | **No arbitrary text path** | Planned | Tier 2→3 | **Tier 2** — convert text glyphs to custGeom outlines positioned along path. **Tier 3** — EMF path with glyph outlines, benefits from affine transforms for rotation per glyph. |
| `<textPath startOffset="...">` | Offset along path | Planned | Tier 2→3 | Adjust glyph start position along path. |
| `<textPath method="stretch">` | Glyph distortion along path | Planned | Tier 2→3 | **Tier 2** — warp custGeom glyph geometry along path curvature. **Tier 3** — EMF with warped glyph outlines. |

### 7.4 BiDi & Internationalization

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `direction: rtl` | `rtl="1"` on `<a:pPr>` | Done | — | |
| `direction: ltr` | Default | Done | — | |
| Auto-detect RTL from content | `rtl="1"` based on Unicode BiDi | Done | — | |
| `unicode-bidi: bidi-override` | **Paragraph-level only** | Planned | Tier 2→3 | **Tier 2** — split mixed-direction runs into separate paragraphs. **Tier 3** — EMF text with explicit character order. |
| `xml:lang` / `lang` | `lang` on `<a:rPr>` | Planned | Tier 1 | Map BCP-47 tags. Auto-detect from Unicode script. |

---

## 8. Filters

### 8.1 Mappable to Native DrawingML Effects (Tier 1–2)

| SVG Filter | DrawingML Effect | Status | Fallback | Notes |
|------------|-----------------|--------|----------|-------|
| `feGaussianBlur` (standalone) | `<a:softEdge rad="...">` | Done | Tier 2 | Approximate — softEdge fades edges vs uniform blur. |
| `feDropShadow` | `<a:outerShdw>` | Done | Tier 1 | Close match for standard drop shadows. |
| `feOffset`+`feFlood`+`feComposite` (shadow) | `<a:outerShdw>` | Done | Tier 2 | Detect shadow pattern → single shadow effect. |
| `feGaussianBlur`+`feMerge` (glow) | `<a:glow rad="...">` | Planned | Tier 2 | Detect glow pattern: blur + merge with original. |
| `feColorMatrix(saturate)` | `<a:satMod>` | Planned | Tier 2 | Partial — only works on solid fills. |
| `feColorMatrix(hueRotate)` | `<a:hueOff>` | Planned | Tier 2 | Very approximate. |
| `feFlood`+`feBlend(multiply)` | `<a:duotone>` | Investigate | Tier 2 | DrawingML duotone may approximate some overlays. |

### 8.2 EMF Vector Fallback (Tier 3)

For filters that cannot map to DrawingML effects but where the underlying
geometry is still vector-representable:

| SVG Filter | EMF Strategy | Status | Notes |
|------------|-------------|--------|-------|
| `feColorMatrix(luminanceToAlpha)` | EMF path with computed alpha fill | Planned | Pre-compute luminance → alpha for each shape's fill color, emit as EMF with adjusted fills. Only works for simple (non-gradient) fills. |
| `feDiffuseLighting` (simple) | EMF + `scene3d`/`sp3d` hybrid | Investigate | Simple top-down lighting → try DrawingML 3D lighting first (Tier 2). If too different, EMF with pre-shaded fills. |
| `feSpecularLighting` (simple) | EMF + 3D hybrid | Investigate | Same as diffuse. |
| `feComponentTransfer(gamma)` on solid fills | EMF with pre-computed colors | Planned | Apply gamma to each shape's fill color before emission. Exact for solid fills. |
| Filter on pure-geometry shapes (no gradients) | EMF with geometry + adjusted fills | Planned | When filtered content has no gradients/images, compute filter effect on fill colors and emit geometry as EMF with modified colors. |
| Filter EMF diagnostic icons | Current schematic visualizations | Done | Present behavior: symbolic EMF icons (96×64px) showing filter type. Not pixel-accurate but vector. ADR-018 plans enrichment. |

### 8.3 Must Rasterize (Tier 4)

Only when both DrawingML mimic AND EMF vector are insufficient:

| SVG Filter | Why Tier 4 | Notes |
|------------|-----------|-------|
| `feMorphology(erode/dilate)` | Pixel-level shape expansion/contraction — requires sampling | No vector representation of morphological operations on arbitrary content. |
| `feDisplacementMap` | Per-pixel displacement — fundamentally raster | Displaces pixels by sampling another image. No vector equivalent. |
| `feTurbulence` | Procedural Perlin noise — fundamentally raster | Generates noise texture. Could embed as DIB in EMF (Tier 3 hybrid) per ADR-018, but the noise itself must be rasterized. |
| `feConvolveMatrix` | Arbitrary kernel — fundamentally raster | Pixel neighborhood sampling. No vector equivalent. |
| `feComponentTransfer(table/discrete)` on gradients/images | Lookup table on pixel values | Cannot pre-compute for continuous gradient content. |
| `feImage` (complex context) | External image in filter chain | Could emit as blipFill for simple cases; rasterize when used in composite filter chains. |
| Complex multi-primitive chains with pixel operations | DrawingML effects are not composable, EMF can't compute | When a filter chain mixes vector-representable and pixel operations, the entire chain must be rasterized. |
| `feTurbulence` → hybrid EMF | Embed rasterized noise tile in EMF DIB brush | Planned (ADR-018) | Intermediate: noise is rasterized but wrapped in vector EMF container with DIB pattern brush. Better than pure PNG. |

---

## 9. Markers

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `marker-start` (simple arrow) | `<a:headEnd>` | Done | Tier 1 | |
| `marker-end` (simple arrow) | `<a:tailEnd>` | Done | Tier 1 | |
| `marker-start` (complex shape) | Expand to separate custGeom | Done | Tier 2 | |
| `marker-end` (complex shape) | Expand to separate custGeom | Done | Tier 2 | |
| `marker-mid` | Expand to custGeom per vertex | Done | Tier 2 | |
| `orient="auto"` | Rotation per vertex tangent | Done | — | |
| `orient="auto-start-reverse"` | Start marker flipped 180° | Planned | Tier 2 | |
| `markerUnits="strokeWidth"` | Scale marker by stroke width | Done | — | |
| `markerUnits="userSpaceOnUse"` | Absolute marker size | Done | — | |
| `refX`/`refY` anchor offsets | Translate marker origin | Done | — | |
| `overflow="visible"` on marker | Content exceeds marker viewport | Planned | Tier 2→3 | **Tier 2** — don't clip marker custGeom to markerWidth/Height. **Tier 3** — EMF save/restore clip state around marker. |
| Marker with gradient fill | Marker shape needs gradient | Planned | Tier 2 | Expanded marker custGeom inherits fill from marker definition → emit with `gradFill`. DrawingML handles this. |
| Marker with filter effect | Marker shape needs filter | Planned | Tier 2→3→4 | Route marker content through the same filter fallback ladder. |

---

## 10. Document Structure

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<svg>` viewBox | Viewport mapping | Done | — | |
| `preserveAspectRatio` (all 9 + meet/slice) | Viewport engine | Done | — | |
| `<g>` (group) | `<p:grpSp>` | Direct | — | |
| `<defs>` | Resolved inline | Direct | — | |
| `<use>` | Expanded inline | Done | — | |
| `<symbol>` | Expanded inline | Done | — | |
| `<switch>` with `systemLanguage` | Resolve at parse time | Planned | — | |
| `<switch>` with `requiredFeatures` | Resolve at parse time | Planned | — | |
| `<foreignObject>` | **No DrawingML or EMF equivalent** | Planned | Tier 3→4 | **Tier 3** — render HTML via headless browser, embed result in EMF as `StretchDIBits` (bitmap inside vector container — preserves EMF wrapper, scalable container). **Tier 4** — embed as PNG `blipFill`. Either way the HTML content itself is rasterized, but EMF wrapper is preferable. |
| `<a xlink:href="...">` (hyperlinks) | `<a:hlinkClick r:id="...">` | Planned | Tier 1 | |
| `<title>` / `<desc>` | `<p:cNvPr descr="...">` | Planned | Tier 1 | |
| `<metadata>` | Ignored | Ignore | — | |
| `overflow: hidden` on `<svg>` | Viewport clipping | Done | — | |
| `overflow: visible` on nested `<svg>` | No clipping | Planned | Tier 2 | |

---

## 11. CSS & Styling

All CSS features are resolved at parse time and do not need DrawingML or EMF
fallbacks. They affect how SVG properties are resolved, not how they are emitted.

| SVG | Status | Notes |
|-----|--------|-------|
| `<style>` blocks / class/ID/attribute selectors | Done | Full CSS cascade via tinycss2. |
| `@font-face` web fonts | Done | Download and embed in PPTX. |
| `@media` queries | Planned | Evaluate at SVG viewport dimensions. |
| `@import` | Planned | Fetch and merge imported stylesheets. |
| CSS custom properties (`var()`) | Planned | Substitute during cascade. |
| `calc()` | Planned | Evaluate during property resolution. |
| `inherit` / `initial` / `unset` | Done/Planned | Resolved by cascade. |
| Inline `style` + presentation attributes | Done | |

---

## 12. Color

All color values are resolved at parse time to sRGB + alpha. No fallback tiers
needed — conversion happens before DrawingML emission.

| SVG | Status | Notes |
|-----|--------|-------|
| Named colors, `#hex`, `rgb()`, `rgba()`, `hsl()`, `hsla()` | Direct | |
| `currentColor` | Direct | Resolved from `color` property. |
| `color-interpolation: linearRGB` | Planned | See §2 gradients — extra interpolated stops. |
| `color-profile` / ICC | Ignore | Convert to sRGB. Lossy for wide-gamut. |
| `oklab()` / `oklch()` (CSS Color 4) | Planned | Convert to sRGB at parse time. |
| System colors | Planned | Map to sensible defaults. |

---

## 13. Rendering Hints

Not applicable to OOXML output — rendering decisions are made by the viewer
(PowerPoint, Google Slides). No fallback tiers.

| SVG | Status | Notes |
|-----|--------|-------|
| `image-rendering` | Ignore | Viewer controls interpolation. |
| `shape-rendering` | Ignore | Viewer controls anti-aliasing. |
| `text-rendering` | Ignore | Viewer controls font hinting. |
| `color-interpolation-filters` | Planned | Affects filter rasterization color space, not output format. |

---

## 14. Images

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<image>` raster (PNG/JPEG) | `<a:blipFill>` | Direct | — | |
| `<image>` SVG | Recursive conversion | Planned | Tier 1→4 | **Tier 1** — recursively convert nested SVG to DrawingML shapes. **Tier 4** — rasterize and embed as PNG if recursion fails. |
| `<image>` data URI | Extract and embed | Done | — | |
| `preserveAspectRatio` on `<image>` | `<a:stretch>` / crop | Done | — | |

---

## Summary: Fallback Tier Map

### Tier 1 — Native DrawingML (editable, scalable)
Everything with "Direct" status plus simple mimics that use standard DrawingML
attributes in their intended way.

### Tier 2 — DrawingML Mimic (editable, scalable, creative use of spec)
- `stroke-dashoffset` → rotate dash array
- `gradientTransform` → decompose to `lin ang` / stop adjustment
- `gradientUnits="userSpaceOnUse"` → coordinate transform
- `spreadMethod reflect/repeat` → stop expansion (done)
- Uniform opacity mask → alpha shortcut (done)
- Group opacity (no overlap) → per-child alpha
- `paint-order` → duplicate shape
- `vector-effect: non-scaling-stroke` → adjust width by transform scale
- Gradient masks (simple) → alpha gradient approximation
- `word-spacing` → extra space characters
- `textPath` (preset match) → WordArt `prstTxWarp`
- Per-character positioning → individual text boxes
- Simple filter patterns → native effects (shadow, glow, softEdge)
- `color-interpolation: linearRGB` → extra interpolated stops
- Pattern tiles → `blipFill` + `<a:tile>` (done)

### Tier 3 — EMF Vector (scalable, limited editability)
Use when DrawingML mimics are insufficient but vector quality must be preserved:
- `skewX`/`skewY` transforms on complex elements (images, groups)
- Complex/self-intersecting clip paths → EMF `SelectClipPath`
- Nested clip paths → EMF clip combine modes (intersect)
- Group-level clip paths → EMF graphics state clipping
- `fill-rule: evenodd` (if DrawingML renderers don't honor it) → EMF `SetPolyFillMode`
- Per-character `dx`/`dy`/`rotate` → EMF `ExtTextOut` with per-char positioning
- `textPath` on arbitrary curves → EMF glyph outlines
- Text with complex layout (overline, bidi-override) → EMF text records
- Pattern with rotation/skew transforms → EMF affine on brush
- Masks on vector content → EMF clip-path approximation
- Filter on geometry-only content → EMF with pre-computed fill colors
- `<foreignObject>` → EMF `StretchDIBits` wrapper (raster content in vector container)
- `feTurbulence` hybrid → EMF with DIB pattern brush (ADR-018)

### Tier 4 — PNG Raster (last resort, not scalable)
Only when the visual result fundamentally requires pixel composition:
- `mix-blend-mode` (all values) — no vector compositing operators anywhere
- `opacity` on `<g>` with overlapping children — neither DrawingML nor EMF has group alpha
- Complex filter chains with pixel operations (`feDisplacementMap`, `feMorphology`, `feConvolveMatrix`)
- `feTurbulence` (pure noise, unless hybrid EMF per ADR-018)
- Luminance/alpha masks with complex gradient content
- Nested `<image>` SVG when recursive conversion fails
