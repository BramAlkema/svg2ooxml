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

### Policy Controls Tier Switching

The fallback ladder describes *what each tier can do*. The **policy engine**
decides *when to switch* between tiers at runtime. Three policy domains control
the three main fallback decision points:

```
User / API / preset
    ↓
PolicyEngine.evaluate()
    ↓
    ├── geometry policy  →  apply_geometry_policy()  →  render_mode ∈ {native, emf, bitmap}
    ├── filter policy    →  _resolve_strategy()      →  strategy ∈ {auto, native, vector, emf, raster}
    └── mask policy      →  _determine_vector_strategy() → fallback_order iteration
```

**Quality presets** set baseline behavior. Four presets are built in:

| Preset | Geometry | Filters | Masks | Use case |
|--------|----------|---------|-------|----------|
| `high` | EMF+bitmap allowed, 2000 segment limit | `native` strategy, no raster preference | Full ladder (native→mimic→emf→raster), 8K segment limit | Maximum fidelity |
| `balanced` (default) | EMF+bitmap allowed, 1000 segment limit | `auto` strategy | Full ladder, 6K segment limit | General use |
| `low` | EMF+bitmap allowed, 500 segment limit | `raster` strategy preferred | Skip native/mimic, go EMF→raster, 4K segment limit | Speed / small files |
| `compatibility` | EMF+bitmap allowed, 300 segment limit | `emf` strategy | Raster preferred | Maximum viewer support |

**Per-domain policy keys** override presets for fine-grained control:

#### Geometry policy (`policy/providers/path.py` → `policy/geometry.py`)

Controls when paths fall from native DrawingML to EMF or bitmap.

| Key | Type | Default | Controls |
|-----|------|---------|----------|
| `force_emf` | bool | `False` | Skip Tier 1–2, go straight to EMF for all geometry |
| `force_bitmap` | bool | `False` | Skip Tier 1–3, go straight to raster for all geometry |
| `allow_emf_fallback` | bool | `True` | Whether Tier 3 is available when complexity exceeds thresholds |
| `allow_bitmap_fallback` | bool | `True` | Whether Tier 4 is available |
| `max_segments` | int | `1000` | Path segment count before triggering fallback |
| `max_complexity_ratio` | float | `0.8` | Complexity score ratio threshold |
| `simplify_paths` | bool | `True` | Attempt path simplification before falling back |

Decision flow in `apply_geometry_policy()`:
1. Check force flags → immediate tier selection
2. Count segments → if over threshold, try simplification, else fall to EMF
3. Score complexity → if over ratio, fall to EMF
4. Check allow flags → if target tier is disabled, revert to native

#### Filter policy (`policy/providers/filter.py` → `services/filter_service.py`)

Controls the rendering strategy for SVG filter effects.

| Key | Type | Default | Controls |
|-----|------|---------|----------|
| `strategy` | str | `"auto"` | Master strategy: `auto`, `native`, `vector`, `emf`, `raster` |
| `prefer_rasterization` | bool | `False` | In `auto` mode, prefer raster over vector attempts |
| `native_blur` | bool | `True` | Allow `feGaussianBlur` → `softEdge` (Tier 2) |
| `native_shadow` | bool | `True` | Allow `feDropShadow` → `outerShdw` (Tier 1) |
| `approximation_allowed` | bool | `True` | Allow lossy DrawingML approximations |
| `max_filter_primitives` | int | `5` | Primitive count before forcing fallback |

Strategy meanings:
- `auto` — try native → vector → EMF → raster, return first success
- `native` — only Tier 1–2 DrawingML effects, skip if unmappable
- `vector` — Tier 1–3, no raster
- `emf` — prefer EMF (Tier 3)
- `raster` — go directly to Tier 4

#### Mask policy (`policy/providers/mask.py` → `services/mask_service.py`)

Controls the fallback order for mask rendering.

| Key | Type | Default | Controls |
|-----|------|---------|----------|
| `fallback_order` | tuple | `("native","mimic","emf","raster")` | Explicit tier order — iterated top to bottom |
| `allow_vector_mask` | bool | `True` | Whether `native` and `mimic` tiers are available |
| `force_emf` | bool | `False` | Jump to EMF tier |
| `force_raster` | bool | `False` | Jump to raster tier |
| `max_emf_segments` | int | `6000` | EMF complexity limit — exceeding falls through to next tier |
| `max_emf_commands` | int | `9000` | EMF command count limit |

The mask fallback order is the most explicit of the three — it is a literal
tuple that the mask service iterates. Each tier is attempted and either succeeds
(content fits within limits) or fails through to the next.

#### Variant-based multi-tier rendering

`slide_orchestrator.py:build_fidelity_tier_variants()` can produce multiple
slides from the same SVG, each at a different quality tier:

| Variant | Geometry | Filters | Result |
|---------|----------|---------|--------|
| Direct | No EMF, no bitmap | native only | Maximum editability, may lose complex content |
| Mimic | EMF allowed, no bitmap | EMF strategy | Vector-quality fallback |
| Bitmap | EMF + bitmap allowed | raster strategy | Maximum fidelity, least editable |

This lets the user or downstream tooling pick the best trade-off per slide.

#### Override format

Policy overrides are passed as `dict[target_name, dict[key, value]]`:

```python
policy_overrides = {
    "geometry": {"allow_emf_fallback": False, "max_segments": 500},
    "filter":   {"strategy": "emf"},
    "mask":     {"fallback_order": ("emf", "raster"), "force_emf": True},
}
```

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
| `fill-rule: evenodd` | EMF `SetPolyFillMode(ALTERNATE)` | Done | Tier 1→3 | Implemented in clip_service, emf_path_adapter, clip_overlay. EMF uses ALTERNATE fill mode. |
| `color` / `currentColor` | Resolved at parse time | Direct | — | Substituted before DrawingML emission |

### 1.2 Stroke

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `stroke` solid | `<a:ln>` with `solidFill` | Direct | — | |
| `stroke` gradient | `<a:ln>` with `gradFill` | Done | Tier 1 | `stroke_to_xml()` emits `gradFill` inside `<a:ln>` for LinearGradientPaint/RadialGradientPaint strokes. |
| `stroke` pattern | `<a:ln>` with pattern fill | Done | Tier 1 | `stroke_to_xml()` emits `_pattern_to_fill_elem()` inside `<a:ln>` for PatternPaint strokes. |
| `stroke-width` | `<a:ln w="...">` (EMUs) | Direct | — | |
| `stroke-linecap: butt` | `cap="flat"` | Direct | — | |
| `stroke-linecap: round` | `cap="rnd"` | Direct | — | |
| `stroke-linecap: square` | `cap="sq"` | Direct | — | |
| `stroke-linejoin: miter` | `<a:miter>` child of `<a:ln>` | Direct | — | |
| `stroke-linejoin: round` | `<a:round>` child of `<a:ln>` | Direct | — | |
| `stroke-linejoin: bevel` | `<a:bevel>` child of `<a:ln>` | Direct | — | |
| `stroke-miterlimit` | `<a:miter lim="...">` | Direct | — | Value × 100,000 |
| `stroke-dasharray` | `<a:custDash>` with `<a:ds d="..." sp="...">` | Direct | — | |
| `stroke-dashoffset` | Rotate `custDash` array | Done | Tier 2 | `_apply_dash_offset()` in `paint_runtime.py` rotates the dash/gap array by the offset before emitting `<a:custDash>`. Pure arithmetic, zero visual loss. |
| `stroke-opacity` | `<a:alpha>` on stroke fill | Direct | — | |
| `paint-order: stroke fill markers` | Shape duplication: stroke-only + fill-only | Done | Tier 2 | When stroke before fill, emits two shapes at same position via `dataclasses.replace()`. Parsed from CSS and attribute. |
| `vector-effect: non-scaling-stroke` | Default DrawingML behavior | Done | — | DrawingML `<a:ln w>` doesn't scale with shape transforms — matches non-scaling-stroke by default. |

### 1.3 Opacity

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `opacity` on element | `<a:alpha>` on fill AND stroke | Direct | — | |
| `opacity` on `<g>` (no child overlap) | Individual child `<a:alpha>` | Done | Tier 2 | Shapes inherit alpha when children don't overlap. |
| `opacity` on `<g>` (children overlap) | Rasterize group to PNG via Skia | Done | Tier 4 | `_rasterize_group()` renders children to offscreen Skia surface, embeds as `p:pic` with `alphaModFix`. Falls back to per-child alpha when Skia unavailable. |
| `isolation: isolate` | Parsed; rasterize when blend modes present | Done | Tier 2→4 | Parsed in style extractor. No-op without blend modes. With blend modes, group rasterization via Skia handles isolation implicitly. |

### 1.4 Blend Modes

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `mix-blend-mode` (all values) | Rasterize via Skia | Done | Tier 4 | Parsed in style extractor. When present, element is rasterized to PNG. Falls back to normal rendering without Skia. Covers all 16 blend modes. |

---

## 2. Gradients

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<linearGradient>` | `<a:gradFill>` with `<a:lin>` | Direct | — | |
| `<radialGradient>` | `<a:gradFill>` with `<a:path>` | Direct | — | |
| `<stop stop-color="..." offset="...">` | `<a:gs pos="...">` in `<a:gsLst>` | Direct | — | |
| `stop-opacity` | `<a:alpha>` on gradient stop color | Direct | — | |
| `gradientUnits="objectBoundingBox"` | Default DrawingML behavior | Direct | — | |
| `gradientUnits="userSpaceOnUse"` | Normalize to bbox-relative [0,1] | Done | Tier 2 | `_normalize_gradient_units()` in `paint_runtime.py` converts absolute coords to bbox-relative before emitting DrawingML. All 16 userSpaceOnUse test SVGs pass. |
| `gradientTransform` (pure rotation) | `<a:lin ang="...">` | Done | Tier 2 | Resvg gradient adapter handles transform decomposition. 2/2 SVGs pass. |
| `gradientTransform` (uniform scale) | Adjust stop positions | Done | Tier 2 | Resvg gradient adapter handles transform decomposition. 2/2 SVGs pass. |
| `gradientTransform` (non-uniform scale) | Adjust stops + direction | Done | Tier 2 | Resvg gradient adapter handles transform decomposition. 2/2 SVGs pass. |
| `gradientTransform` (skew) | **No DrawingML or EMF equivalent** | Done | Tier 2→4 | Resvg gradient adapter handles transform decomposition. 2/2 SVGs pass. |
| `spreadMethod="pad"` | Default DrawingML behavior | Direct | — | |
| `spreadMethod="reflect"` | Expand stops in `gsLst` | Done | Tier 2 | Mirror gradient stops to fill [0,1]. |
| `spreadMethod="repeat"` | Expand stops in `gsLst` | Done | Tier 2 | Duplicate stops N times to fill [0,1]. |
| `fx`/`fy` (focal point ≠ center) | Shift `fillToRect` center | Done | Tier 2 | Gradient center blended 50% toward focal point. Lossy for extreme off-center but visible improvement. |
| `fr` (focal radius, SVG2) | **No DrawingML concept** | Planned | Tier 2 | Add flat-color stop from center to `fr`, then gradient from `fr` to `r`. |
| `color-interpolation: linearRGB` | **DrawingML uses sRGB** | Done | Tier 2 | Pre-computed intermediate stops sampled in linearRGB, converted to sRGB. 6/6 SVGs pass. |

---

## 3. Transforms

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `translate(tx, ty)` | `<a:off x="..." y="...">` | Direct | — | |
| `rotate(angle)` | `<a:xfrm rot="...">` | Direct | — | Degrees × 60,000 |
| `scale(sx, sy)` | `<a:ext cx="..." cy="...">` | Direct | — | |
| `skewX(angle)` | Bake into custGeom path coordinates | Done | Tier 2 | `is_axis_aligned()` detects skew → falls through to path converter which applies full CTM via `_transform_segments()`. All 12 skew test SVGs pass. |
| `skewY(angle)` | Bake into custGeom path coordinates | Done | Tier 2 | Same as `skewX`. |
| `matrix(a,b,c,d,e,f)` (no skew) | Decompose to translate+rotate+scale | Direct | — | |
| `matrix(a,b,c,d,e,f)` (with skew) | Full CTM baked into custGeom | Done | Tier 2 | Path converter applies full matrix. Same mechanism as skewX/Y. |
| Nested transforms with accumulated skew | CTM flattened at each leaf | Done | Tier 2 | Traversal flattens full CTM stack; path converter applies it to geometry. |

---

## 4. Clipping

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `clip-path` (rectangle) | DrawingML shape clipping | Direct | — | |
| `clip-path` (simple path) | DrawingML `custGeom` clip | Done | — | |
| `clip-path` (complex/self-intersecting) | **Limited in DrawingML** | Done | Tier 2→3 | Handled by clip service fallback ladder. All clip SVGs pass validation. |
| `clip-path` on `<g>` (group) | Apply clip per child via fallback ladder | Done | Tier 2 | `clip_service.py` handles group clips. All 14 group-clip test SVGs pass validation. |
| Nested `clip-path` | Intersect via fallback ladder | Done | Tier 2 | Nested clips handled by clip service. All 10 nested-clip test SVGs pass validation. |
| `clip-rule: evenodd` | Winding rule on clip geometry | Done | Tier 1→3 | Implemented in clip_service, emf_path_adapter, clip_overlay. |
| `clip-rule: nonzero` | Default winding | Direct | — | |
| `clipPathUnits="objectBoundingBox"` | Transform to shape bbox | Done | Tier 2 | Handled by clip coordinate conversion. All 7 clipPathUnits test SVGs pass. |
| `clipPathUnits="userSpaceOnUse"` | Default | Direct | — | |

---

## 5. Masking

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<mask>` uniform opacity (solid rect) | Multiply alpha onto shape fill | Done | Tier 2 | Detect single-rect uniform opacity → `<a:alpha>`. |
| `<mask>` gradient (linear alpha fade) | **No DrawingML mask** | Done | Tier 2→4 | Handled by mask service fallback ladder. 9/9 mask SVGs pass. |
| `<mask>` alpha mode | **No DrawingML mask** | Done | Tier 2→4 | Handled by mask classification and fallback ladder. 9/9 mask SVGs pass. |
| `<mask>` with complex vector content | **No DrawingML mask** | Done | Tier 3→4 | Handled by mask service fallback ladder. 9/9 mask SVGs pass. |
| `<mask>` with mixed content | **No DrawingML mask** | Done | Tier 3→4 | Current mask_writer routes through EMF (Tier 3) then raster (Tier 4) based on policy. |
| `mask-type: luminance` vs `alpha` | Affects compositing channel | Done | — | Handled by mask classification. Luminance converts RGB→grayscale alpha, alpha uses alpha channel directly. |
| `maskContentUnits="objectBoundingBox"` | Coordinates in [0,1] | Done | — | Handled by mask classification and coordinate transform. |

---

## 6. Patterns

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<pattern>` matching preset | `<a:pattFill>` | Done | Tier 1 | |
| `<pattern>` complex content | `<a:blipFill>` with `<a:tile>` | Done | Tier 2 | Rasterize tile to PNG, embed as media, tile. |
| `<pattern>` with vector-only content | EMF DIB pattern brush | Planned | Tier 3 | **Tier 3** — EMF supports `CreateDIBPatternBrushPt` with embedded bitmap tiles AND hatch brushes for simple patterns. Could render pattern tile → small bitmap → EMF DIB brush. Preserves vector wrapper. |
| `patternUnits="objectBoundingBox"` | Tile size relative to shape | Done | Tier 2 | 13/13 patternUnits SVGs pass validation. |
| `patternUnits="userSpaceOnUse"` | Tile size in absolute units | Done | Tier 2 | 13/13 patternUnits SVGs pass validation. |
| `patternContentUnits="objectBoundingBox"` | Content scaled to bbox | Done | Tier 2 | Passes validation. |
| `patternTransform` (scale) | `<a:tile sx="..." sy="...">` | Done | Tier 2 | 2/2 patternTransform SVGs pass validation. |
| `patternTransform` (rotation) | **No tile rotation in DrawingML** | Done | Tier 2→3 | Pre-rotated rasterized tile before embedding. 2/2 patternTransform SVGs pass. |
| `patternTransform` (skew) | **No tile skew** | Done | Tier 2→3 | Pre-skewed tile image. 2/2 patternTransform SVGs pass. |

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
| `font-variant: small-caps` | `cap="small"` on `<a:rPr>` | Done | Tier 1 | Parsed from SVG element, emitted on `<a:rPr>`. Validated with .NET SDK. |
| `font-stretch` | Font family suffix | Done | Tier 2 | Appends width keyword (Condensed, Expanded, etc.) to font family name. |
| `text-decoration: underline` | `u="sng"` on `<a:rPr>` | Done | — | |
| `text-decoration: line-through` | `strike="sngStrike"` on `<a:rPr>` | Done | — | |
| `text-decoration: overline` | Separate line shape above baseline | Done | Tier 2 | Emits `<p:cxnSp>` line positioned at text top. Color matches text fill. |
| `letter-spacing` | `spc` on `<a:rPr>` | Done | — | |
| `word-spacing` | Approximated via `spc` inflation | Done | Tier 2 | Word-spacing distributed as proportional extra spc across the run. |

### 7.2 Text Layout & Positioning

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `text-anchor: start/middle/end` | `algn` on `<a:pPr>` | Direct | — | |
| `direction: rtl` | `rtl="1"` on `<a:pPr>` | Done | — | |
| `writing-mode: vertical-rl` | `vert="vert"` on `<a:bodyPr>` | Done | Tier 1 | Parsed from SVG element/CSS, emitted on bodyPr. Validated with .NET SDK. |
| `writing-mode: vertical-lr` | `vert="vert270"` on `<a:bodyPr>` | Done | Tier 1 | Same as vertical-rl. |
| `dominant-baseline` | Y-offset from font metrics | Done | Tier 2 | Maps central/hanging/text-bottom etc. to y-offset using approximate ascent/descent. |
| `alignment-baseline` | Y-offset from font metrics | Done | Tier 2 | Same mechanism as dominant-baseline. |
| `baseline-shift: super` | `baseline` on `<a:rPr>` | Done | Tier 1 | Emitted when IR Run has non-zero `baseline_shift`. Validated with .NET SDK. |
| `baseline-shift: sub` | `baseline` on `<a:rPr>` | Done | Tier 1 | Same as super — negative baseline_shift value. |
| Per-character `dx`/`dy` arrays | Glyph outlines via Skia | Done | Tier 2 | Each character rendered as custGeom shape at computed position. Uses Skia for glyph paths and metrics. |
| Per-character `x`/`y` absolute arrays | Glyph outlines via Skia | Done | Tier 2 | Same infrastructure as dx/dy with absolute positioning. |
| Per-character `rotate` | Rotated glyph outlines via Skia | Done | Tier 2 | Each glyph rotated by specified angle before emitting as custGeom. |
| `textLength` + `lengthAdjust="spacing"` | Computed `spc` | Done | Tier 2 | Effective letter-spacing = (targetWidth - naturalWidth) / (charCount - 1). |
| `textLength` + `lengthAdjust="spacingAndGlyphs"` | Approximated via `spc` + font size | Done | Tier 2 | Same spacing mechanism as `lengthAdjust="spacing"`. Glyph scaling approximated. |

### 7.3 Text Path

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<textPath>` on simple curve | `prstTxWarp` on `<a:bodyPr>` | Done | Tier 2 | Implemented via path classification to WordArt presets; falls back when confidence is low. |
| `<textPath>` on arbitrary curve | custGeom outlines via resvg path fallback | Done | Tier 2 | Text rendered as path geometry. WordArt `prstTxWarp` used when curve matches preset (simple arcs). |
| `<textPath startOffset="...">` | Handled by resvg text pipeline | Done | Tier 2 | Resvg applies startOffset during path text layout. |
| `<textPath method="stretch">` | Resvg path layout + custGeom | Done | Tier 2 | Resvg handles stretch layout; result rendered as custGeom shapes. |

### 7.4 BiDi & Internationalization

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `direction: rtl` | `rtl="1"` on `<a:pPr>` | Done | — | |
| `direction: ltr` | Default | Done | — | |
| Auto-detect RTL from content | `rtl="1"` based on Unicode BiDi | Done | — | |
| `unicode-bidi: bidi-override` | RTL handling via existing pipeline | Done | Tier 2 | Existing RTL detection and `rtl="1"` emission handles most bidi cases. |
| `xml:lang` / `lang` | `lang` on `<a:rPr>` | Done | Tier 1 | Extracted from SVG `xml:lang` attribute, emitted on `<a:rPr>`. |

---

## 8. Filters

### 8.1 Mappable to Native DrawingML Effects (Tier 1–2)

| SVG Filter | DrawingML Effect | Status | Fallback | Notes |
|------------|-----------------|--------|----------|-------|
| `feGaussianBlur` (standalone) | `<a:softEdge rad="...">` | Done | Tier 2 | Approximate — softEdge fades edges vs uniform blur. |
| `feDropShadow` | `<a:outerShdw>` | Done | Tier 1 | Close match for standard drop shadows. |
| `feOffset`+`feFlood`+`feComposite` (shadow) | `<a:outerShdw>` | Done | Tier 2 | Detect shadow pattern → single shadow effect. |
| `feGaussianBlur`+`feMerge` (glow) | `<a:glow rad="...">` | Done | Tier 2 | Handled by filter pipeline. |
| `feColorMatrix(saturate)` | `<a:satMod>` | Done | Tier 2 | Handled by filter pipeline. 2/2 feColorMatrix SVGs pass. |
| `feColorMatrix(hueRotate)` | `<a:hueOff>` | Done | Tier 2 | Handled by filter pipeline. 2/2 feColorMatrix SVGs pass. |
| `feFlood`+`feBlend(multiply)` | Raster fallback | Done | Tier 4 | Handled via filter rasterization pipeline. Native `<a:duotone>` mapping not attempted. |

### 8.2 EMF Vector Fallback (Tier 3)

For filters that cannot map to DrawingML effects but where the underlying
geometry is still vector-representable:

| SVG Filter | EMF Strategy | Status | Notes |
|------------|-------------|--------|-------|
| `feColorMatrix(luminanceToAlpha)` | EMF path with computed alpha fill | Done | Handled by filter pipeline. 2/2 feColorMatrix SVGs pass. |
| `feDiffuseLighting` (simple) | Raster fallback via resvg | Done | Tier 4 | Handled by `lighting.py` primitive — rasterized via resvg. |
| `feSpecularLighting` (simple) | Raster fallback via resvg | Done | Tier 4 | Same as diffuse — rasterized via resvg. |
| `feComponentTransfer(gamma)` on solid fills | EMF with pre-computed colors | Done | Handled by filter primitives. |
| Filter on pure-geometry shapes (no gradients) | EMF with geometry + adjusted fills | Done | Handled by filter pipeline. |
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
| `orient="auto-start-reverse"` | Start marker flipped 180° | Done | Tier 2 | Implemented for start markers (adds 180° relative to auto orientation). |
| `markerUnits="strokeWidth"` | Scale marker by stroke width | Done | — | |
| `markerUnits="userSpaceOnUse"` | Absolute marker size | Done | — | |
| `refX`/`refY` anchor offsets | Translate marker origin | Done | — | |
| `overflow="visible"` on marker | Content exceeds marker viewport | Done | Tier 2→3 | 11/11 marker SVGs pass validation. |
| Marker with gradient fill | Marker shape needs gradient | Done | Tier 2 | 11/11 marker SVGs pass validation. |
| Marker with filter effect | Marker shape needs filter | Done | Tier 2→3→4 | 11/11 marker SVGs pass validation. |

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
| `<switch>` with `systemLanguage` | Resolve at parse time | Done | — | Implemented in switch evaluator and traversal hook selection. |
| `<switch>` with `requiredFeatures` | Resolve at parse time | Done | — | Implemented in switch evaluator and traversal hook selection. |
| `<foreignObject>` | **No DrawingML or EMF equivalent** | Planned | Tier 3→4 | **Tier 3** — render HTML via headless browser, embed result in EMF as `StretchDIBits` (bitmap inside vector container — preserves EMF wrapper, scalable container). **Tier 4** — embed as PNG `blipFill`. Either way the HTML content itself is rasterized, but EMF wrapper is preferable. |
| `<a xlink:href="...">` (hyperlinks) | `<a:hlinkClick r:id="...">` | Done | Tier 1 | Implemented for valid action/hyperlink targets; bookmark/custom-show action URIs are intentionally not emitted. |
| `<title>` / `<desc>` | `<p:cNvPr descr="...">` | Done | Tier 1 | Extracted in traversal hooks, emitted as `descr` attribute on all shape templates. |
| `<metadata>` | Ignored | Ignore | — | |
| `overflow: hidden` on `<svg>` | Viewport clipping | Done | — | |
| `overflow: visible` on nested `<svg>` | No clipping | Done | Tier 2 | Handled — no clip applied when overflow is visible. | |

---

## 11. CSS & Styling

All CSS features are resolved at parse time and do not need DrawingML or EMF
fallbacks. They affect how SVG properties are resolved, not how they are emitted.

| SVG | Status | Notes |
|-----|--------|-------|
| `<style>` blocks / class/ID/attribute selectors | Done | Full CSS cascade via tinycss2. |
| `@font-face` web fonts | Done | Download and embed in PPTX. |
| `@media` queries | Done | `_process_media_rule` evaluates min/max-width/height against viewport, includes matching child rules. |
| `@import` | Planned | Fetch and merge imported stylesheets. |
| CSS custom properties (`var()`) | Done | `:root` custom properties collected, `var()` references substituted during declaration parsing via `_resolve_var`. |
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
| `color-interpolation: linearRGB` | Done | Extra interpolated stops in linearRGB→sRGB. 6/6 SVGs pass. |
| `color-profile` / ICC | Ignore | Convert to sRGB. Lossy for wide-gamut. |
| `oklab()` / `oklch()` (CSS Color 4) | Done | Parsed via `_parse_oklab`/`_parse_oklch` in color parser, converted to sRGB using existing OKLab module. |
| System colors | Done | `_SYSTEM_COLORS` dict in color parser maps CSS system color keywords to sRGB hex defaults. |

---

## 13. Rendering Hints

Not applicable to OOXML output — rendering decisions are made by the viewer
(PowerPoint, Google Slides). No fallback tiers.

| SVG | Status | Notes |
|-----|--------|-------|
| `image-rendering` | Ignore | Viewer controls interpolation. |
| `shape-rendering` | Ignore | Viewer controls anti-aliasing. |
| `text-rendering` | Ignore | Viewer controls font hinting. |
| `color-interpolation-filters` | Done | Parsed in `resolve_color_mode()` in filter pipeline. Affects rasterization color space selection. |

---

## 14. Images

| SVG | DrawingML | Status | Fallback | Notes |
|-----|-----------|--------|----------|-------|
| `<image>` raster (PNG/JPEG) | `<a:blipFill>` | Direct | — | |
| `<image>` SVG | Recursive conversion | Done | Tier 1→4 | Rasterization fallback exists for nested SVG images. |
| `<image>` data URI | Extract and embed | Done | — | |
| `preserveAspectRatio` on `<image>` | `<a:stretch>` / crop | Done | — | |

---

## Summary: Fallback Tier Map

### Tier 1 — Native DrawingML (editable, scalable)
Everything with "Direct" status plus simple mimics that use standard DrawingML
attributes in their intended way.

### Tier 2 — DrawingML Mimic (editable, scalable, creative use of spec)
- `stroke-dashoffset` → rotate dash array
- `gradientTransform` → decompose to `lin ang` / stop adjustment (done)
- `gradientUnits="userSpaceOnUse"` → coordinate transform (done)
- `spreadMethod reflect/repeat` → stop expansion (done)
- Uniform opacity mask → alpha shortcut (done)
- Gradient/alpha/complex masks → mask service fallback ladder (done)
- Group opacity (no overlap) → per-child alpha (done)
- `paint-order` → duplicate shape
- `vector-effect: non-scaling-stroke` → adjust width by transform scale
- `word-spacing` → extra space characters
- `textPath` (preset match) → WordArt `prstTxWarp`
- Per-character positioning → individual text boxes
- Simple filter patterns → native effects (shadow, glow, softEdge) (done)
- `color-interpolation: linearRGB` → extra interpolated stops (done)
- Pattern tiles → `blipFill` + `<a:tile>` (done)
- `patternUnits` and `patternTransform` → tile scaling/rotation (done)

### Tier 3 — EMF Vector (scalable, limited editability)
Use when DrawingML mimics are insufficient but vector quality must be preserved:
- `skewX`/`skewY` transforms on complex elements (images, groups)
- Complex/self-intersecting clip paths → EMF `SelectClipPath` (done)
- Nested clip paths → EMF clip combine modes (intersect) (done)
- Group-level clip paths → EMF graphics state clipping (done)
- `fill-rule: evenodd` → EMF `SetPolyFillMode` (done)
- Per-character `dx`/`dy`/`rotate` → EMF `ExtTextOut` with per-char positioning
- `textPath` on arbitrary curves → EMF glyph outlines
- Text with complex layout (overline, bidi-override) → EMF text records
- Pattern with rotation/skew transforms → EMF affine on brush (done)
- Masks on vector content → EMF clip-path approximation (done)
- Filter on geometry-only content → EMF with pre-computed fill colors (done)
- `<foreignObject>` → EMF `StretchDIBits` wrapper (raster content in vector container)
- `feTurbulence` hybrid → EMF with DIB pattern brush (ADR-018)

### Tier 4 — PNG Raster (last resort, not scalable)
Only when the visual result fundamentally requires pixel composition:
- `mix-blend-mode` (all values) — no vector compositing operators anywhere
- `opacity` on `<g>` with overlapping children — neither DrawingML nor EMF has group alpha
- Complex filter chains with pixel operations (`feDisplacementMap`, `feMorphology`, `feConvolveMatrix`)
- `feTurbulence` (pure noise, unless hybrid EMF per ADR-018)
- Nested `<image>` SVG when recursive conversion fails

---

## 8. Animation (SMIL → PresentationML)

Animation maps SVG/SMIL elements to `<p:timing>` XML inside the slide.
PowerPoint's playback engine walks `<p:cTn>` children directly — preset IDs
are cosmetic Animation-Pane metadata, not runtime input. The oracle at
`src/svg2ooxml/assets/animation_oracle/` carries empirically verified XML
shapes; the compound slot (`emph/compound` + `emph/behaviors/*`) is the
universal mapping target for stacked SMIL animations on one element.

See also: `docs/specs/svg-animation-native-mapping-spec.md` for full
match-level taxonomy; `docs/specs/animation-fidelity.md` for known playback
bugs; `docs/research/powerpoint-animation-oracle-ssot.md` for the oracle
methodology.

### 8.1 Animation Elements

| SVG Element | DrawingML | Oracle Slot | Status | Notes |
|---|---|---|---|---|
| `<animate>` opacity 0→1 | `<p:animEffect filter="fade" transition="in">` | `entr/fade` | Done | Entrance fade, visually verified. Handler gated. |
| `<animate>` opacity 1→0 | `<p:animEffect filter="fade" transition="out">` | `exit/fade` | Done | Exit fade, visually verified. Handler gated. |
| `<animate>` opacity partial | `<p:animEffect filter="image" prLst="opacity:X">` | `emph/transparency` | Done | Emphasis transparency, visually verified. Handler gated. |
| `<animate>` fill/stroke color | `<p:animClr>` on `fillcolor`/`stroke.color` | `emph/color`, `emph/shape_fill_color`, `emph/stroke_color` | Done | Three oracle slots by target scope. Handler partially gated. |
| `<animate>` text color | `<p:animClr>` on `style.color` | `emph/text_color` | Done | Visually verified. Not yet wired from SMIL routing. |
| `<animate>` x/y position | `<p:animMotion path="M 0 0 L dx dy E">` | `path/motion` | Partial | Oracle slot verified. Coordinate normalization has gaps. |
| `<animate>` width/height | `<p:animScale>` + anchor `<p:animMotion>` | `emph/scale` (+ `path/motion`) | Partial | Oracle verified individually. Anchor compensation not composed. |
| `<animate>` visibility | `<p:set>` on `style.visibility` | `entr/appear` | Done | Visually verified. Handler gated. |
| `<animate>` display | Compiled to descendant `style.visibility` sets | — | Partial | Parser handles; writer compilation incomplete. |
| `<animate>` stroke-width | `<p:anim>` on `stroke.weight` — **dead path** | dead: `anim-stroke-weight` → flipbook | Partial | PPT silently drops native. Flipbook fallback available. |
| `<animate>` font-size | `<p:anim>` on `style.fontSize` (scalar multiplier) | compound (preset 28 recipe) | Partial | Works ONLY inside full preset 28 compound with color siblings. Isolated `style.fontSize` is a dead path. Needs oracle slot. |
| `<animate>` font-weight | `<p:set>` on `style.fontWeight` | `emph/bold` | Done | Visually verified. Not yet wired from SMIL routing. |
| `<animate>` text-decoration | `<p:set>` on `style.textDecorationUnderline` | `emph/underline` | Done | Visually verified. Not yet wired from SMIL routing. |
| `<animate>` path `d`/`points` | No shape-morph primitive | flipbook | Partial | Flipbook with pre-rendered custGeom keyframes. |
| `<animateColor>` | Same as `<animate>` color | Same color slots | Done | Deprecated SVG element; parser routes to same IR. |
| `<animateTransform type="translate">` | `<p:animMotion>` | `path/motion` | Partial | Oracle verified. Multi-keyframe needs expand. |
| `<animateTransform type="scale">` | `<p:animScale>` + origin compensation | `emph/scale` (compound `scale` fragment) | Partial | Oracle verified. Origin compensation gap for off-center transforms. |
| `<animateTransform type="rotate">` | `<p:animRot>` (+ orbital `<p:animMotion>` if cx/cy) | `emph/rotate` (compound `rotate` fragment) | Partial | Oracle verified. cx/cy orbit composition incomplete. |
| `<animateTransform type="skewX/Y">` | No native skew animation | morph-transition or flipbook | Partial | Morph: smooth vertex interpolation via slide duplication (sole animation only). Flipbook: discrete frames (mixed animations). Both verified. |
| `<animateTransform type="matrix">` | Decompose → translate + scale + rotate | compound fragments | Gap | Decomposition exists in handler; not oracle-wired. |
| `<animateMotion>` path | `<p:animMotion path="...">` | `path/motion` | Partial | Oracle verified. SVG→PPT coordinate normalization has gaps. |
| `<animateMotion>` mpath | Resolve `<mpath href>` → `<p:animMotion>` | `path/motion` | Partial | Parser resolves mpath; writer partially wired. |
| `<animateMotion>` rotate=auto | `rAng` for fixed; sampled for tangent | — | Gap | No oracle slot for auto-rotate yet. |
| `<set>` visibility/display | `<p:set>` on `style.visibility` | `entr/appear` | Done | Visually verified. |
| `<set>` numeric/color | `<p:set>` with appropriate target | — | Partial | Handler exists; oracle routing only for visibility. |

### 8.2 Entrance & Exit Effects (Filter Vocabulary)

| SVG Pattern | PPT Filter | Oracle Slot | Status |
|---|---|---|---|
| Opacity 0→1 | `fade` | `entr/filter_effect` | Done (verified) |
| Opacity 1→0 | `fade` | `exit/filter_effect` | Done (verified) |
| Generic entrance | `dissolve`, `wipe(dir)`, `wedge`, `wheel(n)`, `circle(in\|out)`, `strips(dir)`, `blinds(dir)`, `checkerboard(dir)`, `barn(dir)`, `randombar(dir)` | `entr/filter_effect` | Done (17 verified, 12 derived) |
| Generic exit | Same vocabulary, `transition="out"` | `exit/filter_effect` | Done (structurally equivalent) |
| Stroke-dashoffset reveal | `wipe(dir)` mimic | `entr/filter_effect` | Partial | Line-drawing effect approximated via directional wipe. |

### 8.3 Emphasis Effects (Compound Behaviors)

| SVG Pattern | Behavior Fragment | Oracle Slot | Status |
|---|---|---|---|
| Partial opacity change | `transparency` | `emph/transparency` or compound | Done (verified) |
| Fill color change on shape | `fill_color` | `emph/shape_fill_color` or compound | Done (verified) |
| Text color change | `text_color` | `emph/text_color` or compound | Done (verified) |
| Stroke color change | `stroke_color` | `emph/stroke_color` or compound | Done (verified) |
| Color pulse (autoReverse) | — | `emph/color_pulse` | Done (verified) |
| Rotation | `rotate` | `emph/rotate` or compound | Done (verified) |
| Scale | `scale` | `emph/scale` or compound | Done (verified) |
| Motion | `motion` | `path/motion` or compound | Done (verified) |
| Bold toggle | `bold` | `emph/bold` or compound | Done (verified) |
| Underline toggle | `underline` | `emph/underline` or compound | Done (verified) |
| Blink (visibility toggle) | `blink` | `emph/blink` or compound | Done (verified) |
| Stacked multi-behavior | N behaviors composed | `emph/compound` | Done (verified) |

### 8.4 Timing & Scheduling

| SVG | DrawingML | Status | Notes |
|---|---|---|---|
| `begin="0s"` / offset | `<p:stCondLst><p:cond delay="X">` | Done | |
| `begin="click"` | `evt="onClick"` condition | Done | |
| `begin="element.click"` | `evt="onClick"` + target shape | Done | When target maps to a shape ID. |
| `begin="element.begin"` | `evt="onBegin"` condition | Partial | Needs oracle verification. |
| `begin="element.end"` | `evt="onEnd"` condition | Partial | Needs oracle verification. |
| `begin="indefinite"` | Remap to click in bookmark cases | Partial | Composed-native for bookmark case only. |
| `begin="element.repeat(n)"` | No confirmed PPT equivalent | Gap | Parsed, skipped by policy. |
| `begin="accessKey()"` | No PPT keyboard trigger | Unsupported | Parsed, skipped by policy. |
| `begin="wallclock()"` | No PPT equivalent | Unsupported | Parsed, skipped by policy. |
| `dur="Xs"` | `<p:cTn dur="X">` | Done | |
| `dur="indefinite"` | Long duration / wait-state mimic | Partial | No exact finite-slide equivalent. |
| `end` offset | `<p:endCondLst>` | Partial | Wired, needs oracle verification. |
| `end` event refs | `<p:endCondLst>` event conditions | Partial | Wired, needs oracle verification. |
| `repeatCount="n"` | `<p:cTn repeatCount="n*1000">` | Done | Thousandths encoding. |
| `repeatCount="indefinite"` | `repeatCount="indefinite"` | Done | |
| `repeatDur` | `repeatDur` on `<p:cTn>` | Partial | Wired, needs oracle verification. |
| `fill="freeze"` | `fill="hold"` | Partial | Inconsistent across handlers; oracle tokens have `INNER_FILL`. |
| `fill="remove"` | `fill="remove"` | Partial | Same inconsistency. |
| `restart` | `restart` on outer `<p:cTn>` | Partial | Wired, needs oracle verification. |
| `min` / `max` | — | Gap | Parser only; no PPT emission. |

### 8.5 Interpolation

| SVG | DrawingML | Status | Notes |
|---|---|---|---|
| `calcMode="linear"` | Native from/to, TAV linear | Done | Default and preferred. |
| `calcMode="paced"` numeric | Pre-computed paced keyTimes → TAV | Partial | Scalar pacing works; vector pacing incomplete. |
| `calcMode="paced"` motion | Path-distance keyTimes | Partial | Depends on path-length approximation. |
| `calcMode="discrete"` | `<p:set>` segments or discrete TAV | Gap | TAV builder always interpolates linearly. Oracle `emph/blink` shows the pattern. |
| `calcMode="spline"` | Sampled cubic → dense linear TAVs | Gap | PPT has accel/decel but not arbitrary cubic per segment. |
| `keyTimes` | TAV `tm` values | Done | Preserved as non-uniform segment timing. |
| `keySplines` | Sampled into TAV segments | Gap | Raw spline metadata preserved in IR. |
| `keyPoints` (motion) | Retimed motion path samples | Gap | Needs path-progress conversion. |

### 8.6 Additive & Accumulate

| SVG | DrawingML | Status | Notes |
|---|---|---|---|
| `additive="replace"` | Default (omit attr) | Done | |
| `additive="sum"` simple motion | Native composition for limited cases | Gap | Needs pre-computed absolute values. |
| `additive="sum"` generic numeric | Pre-compute absolute values | Gap | Requires animation composition solver. |
| `additive="sum"` color | No semantic color addition | Gap | Skip unless explicit policy. |
| `accumulate="none"` | Default (omit attr) | Done | |
| `accumulate="sum"` finite | Expand repeats into sequenced segments | Gap | Timeline grows with repeat count. |
| `accumulate="sum"` indefinite | No finite equivalent | Unsupported | Needs bounded cap if mimicked. |

### 8.7 Attribute Targets

| SVG Attribute | PPT `attrName` | Oracle Verified | Notes |
|---|---|---|---|
| `opacity` | `style.opacity` | Yes (vocabulary) | Via `emph/transparency` or `entr/fade`/`exit/fade`. |
| `fill` (color) | `fillcolor` | Yes (vocabulary) | Via `emph/color` or `emph/shape_fill_color`. |
| `stroke` (color) | `stroke.color` | Yes (vocabulary) | Via `emph/stroke_color`. |
| `color` (text) | `style.color` | Yes (vocabulary) | Via `emph/text_color`. |
| `visibility` | `style.visibility` | Yes (vocabulary) | Via `<p:set>` / `entr/appear`. |
| `x` / `cx` | `ppt_x` | Yes (vocabulary) | Via `<p:animMotion>`. |
| `y` / `cy` | `ppt_y` | Yes (vocabulary) | Via `<p:animMotion>`. |
| `width` | `ppt_w` | Yes (vocabulary) | Via `<p:animScale>`. |
| `height` | `ppt_h` | Yes (vocabulary) | Via `<p:animScale>`. |
| `transform: rotate` | `r` / `style.rotation` | Yes (vocabulary) | Via `<p:animRot>`. |
| `font-weight` | `style.fontWeight` | Yes (vocabulary) | Via `<p:set>` bold. |
| `text-decoration` | `style.textDecorationUnderline` | Yes (vocabulary) | Via `<p:set>` underline. |
| `font-size` | `style.fontSize` | Dead (requires compound) | Isolated `<p:anim>` silently dropped. |
| `fill-opacity` | — | Dead (`anim-fill-opacity`) | Use `emph/transparency` instead. |
| `stroke-opacity` | — | Dead (`anim-stroke-opacity`) | No native path; EMF fallback only. |
| `stroke-width` | — | Dead (`anim-stroke-weight`) | No native path; EMF fallback only. |
| `fill.type` | `fill.type` | Yes (vocabulary, primer) | Primer for fill color change. |
| `fill.on` | `fill.on` | Yes (vocabulary, primer) | Primer for fill color change. |
| `stroke.on` | `stroke.on` | Yes (vocabulary, primer) | Primer for stroke color change. |

### 8.8 Known Dead Paths (silently dropped by PPT)

These XML shapes parse validly but produce no animation at slideshow runtime.
SSOT: `animation_oracle/dead_paths.xml`.

| Dead Path ID | Element + Attr | Verdict | Verified Replacement |
|---|---|---|---|
| `anim-fill-opacity` | `<p:anim>` on `fill.opacity` | silently-dropped | `emph/transparency` |
| `anim-stroke-opacity` | `<p:anim>` on `stroke.opacity` | silently-dropped | flipbook (pre-rendered keyframes) |
| `anim-stroke-weight` | `<p:anim>` on `stroke.weight` | silently-dropped | flipbook (pre-rendered keyframes) |
| `anim-line-weight` | `<p:anim>` on `line.weight` | silently-dropped | flipbook (pre-rendered keyframes) |
| `anim-style-fontsize-isolated` | `<p:anim>` on `style.fontSize` alone | requires-compound | Preset 28 compound: `animClr style.color` + `animClr fillcolor` + `set fill.type` + `anim style.fontSize` as siblings in one `cTn`. Works with `override="childStyle"` + `bldP build="p"`. Needs oracle slot. |
| `animeffect-image-isolated` | `<p:animEffect filter="image">` alone | requires-compound | `emph/transparency` (pair with `<p:set>`) |
| `anim-style-opacity-tavlst` | `<p:anim>` on `style.opacity` via TAV | silently-dropped | `emph/transparency` or `entr/fade`/`exit/fade` |
