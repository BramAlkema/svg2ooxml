# SVG → DrawingML Feature Map

Exhaustive catalog of every SVG feature that has no direct DrawingML (OOXML)
equivalent, with the closest possible substitute strategy for each. This is the
reference document for deciding how to handle any SVG construct in svg2ooxml.

Status key:
- **Done** — implemented in svg2ooxml
- **Direct** — direct DrawingML equivalent exists, implemented
- **Planned** — substitute identified, not yet implemented
- **Investigate** — may work but needs testing/verification
- **Rasterize** — no native substitute; must fall back to EMF or PNG
- **Ignore** — not relevant for static PPTX output

---

## 1. Painting & Stroke

### 1.1 Fill

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `fill` solid color | `solidFill` | Direct | |
| `fill` linear gradient | `gradFill` with `lin` | Direct | |
| `fill` radial gradient | `gradFill` with `path` | Direct | |
| `fill` pattern (preset) | `pattFill` | Done | Matches DrawingML preset patterns |
| `fill` pattern (complex) | `blipFill` with `<a:tile>` | Done | Rasterize pattern tile to PNG, tile across shape |
| `fill: none` | No fill element | Direct | |
| `fill-opacity` | `<a:alpha>` on fill color | Direct | |
| `fill-rule: nonzero` | Default winding in custGeom | Direct | |
| `fill-rule: evenodd` | Compound subpaths in single `<a:path>` | Investigate | DrawingML compound paths should use alternate fill (evenodd). PPT drops this but the spec supports it. Verify with custGeom containing subpaths. |
| `color` / `currentColor` | Resolved at parse time | Direct | Substituted before DrawingML emission |

### 1.2 Stroke

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `stroke` solid | `<a:ln>` with `solidFill` | Direct | |
| `stroke` gradient | `<a:ln>` with `gradFill` | Investigate | DrawingML spec allows `gradFill` inside `<a:ln>`. Need to verify PowerPoint/Google Slides actually render it. If not, expand stroke to filled path and apply gradient to fill. |
| `stroke` pattern | `<a:ln>` with `pattFill` or `blipFill` | Investigate | Likely unsupported in renderers. Fallback: stroke-to-fill expansion, then apply pattern to resulting shape. |
| `stroke-width` | `<a:ln w="...">` (EMUs) | Direct | |
| `stroke-linecap: butt` | `cap="flat"` | Direct | |
| `stroke-linecap: round` | `cap="rnd"` | Direct | |
| `stroke-linecap: square` | `cap="sq"` | Direct | |
| `stroke-linejoin: miter` | `<a:miter>` child of `<a:ln>` | Direct | |
| `stroke-linejoin: round` | `<a:round>` child of `<a:ln>` | Direct | |
| `stroke-linejoin: bevel` | `<a:bevel>` child of `<a:ln>` | Direct | |
| `stroke-miterlimit` | `<a:miter lim="...">` | Direct | Value × 100,000 |
| `stroke-dasharray` | `<a:custDash>` with `<a:ds d="..." sp="...">` | Direct | |
| `stroke-dashoffset` | **No DrawingML equivalent** | Planned | Rotate the dash/gap array: consume the offset from the first dash length, shift remaining entries. Pure arithmetic on `d`/`sp` values. Zero visual loss. |
| `stroke-opacity` | `<a:alpha>` on stroke fill | Direct | |
| `paint-order: stroke fill markers` | **No DrawingML equivalent** — always fill-then-stroke | Planned | When `paint-order` puts stroke before fill: emit stroke as a separate shape behind the fill shape (two shapes instead of one). Rare in practice. |
| `vector-effect: non-scaling-stroke` | **No DrawingML equivalent** | Planned | Compute effective transform scale at the element, divide `stroke-width` by that scale factor. Exact at the authored zoom level; diverges if user zooms in PowerPoint. Acceptable for static output. |

### 1.3 Opacity

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `opacity` on element | `<a:alpha>` on fill AND stroke | Direct | Both fill and stroke alpha multiplied |
| `opacity` on `<g>` (no overlap) | Individual child `<a:alpha>` | Planned | Detect non-overlapping children via bbox intersection test. Apply alpha to each child individually. Visually identical. |
| `opacity` on `<g>` (overlap) | **No DrawingML group alpha** | Planned | Detect overlapping children. Rasterize the group to a single PNG via resvg/Skia, wrap in `blipFill` with alpha. Loses editability for that group only. |
| `isolation: isolate` | **No equivalent** | Planned | Creates compositing boundary. Only matters when `mix-blend-mode` is also used. Rasterize the isolated group, or ignore when no blend modes present. |

### 1.4 Blend Modes

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `mix-blend-mode: multiply` | **No DrawingML support** | Rasterize | Pre-composite the blended result as a PNG image. |
| `mix-blend-mode: screen` | **No DrawingML support** | Rasterize | Same. |
| `mix-blend-mode: overlay` | **No DrawingML support** | Rasterize | Same. |
| All other blend modes | **No DrawingML support** | Rasterize | DrawingML has zero blend mode capability. The only option is to rasterize the composited result. Applies to: `darken`, `lighten`, `color-dodge`, `color-burn`, `hard-light`, `soft-light`, `difference`, `exclusion`, `hue`, `saturation`, `color`, `luminosity`. |

---

## 2. Gradients

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `<linearGradient>` | `<a:gradFill>` with `<a:lin>` | Direct | |
| `<radialGradient>` | `<a:gradFill>` with `<a:path>` | Direct | |
| `<stop stop-color="..." offset="...">` | `<a:gs pos="...">` in `<a:gsLst>` | Direct | |
| `stop-opacity` | `<a:alpha>` on gradient stop color | Direct | |
| `gradientUnits="objectBoundingBox"` | Default DrawingML behavior | Direct | Gradient coordinates are bbox-relative. |
| `gradientUnits="userSpaceOnUse"` | **No direct mapping** | Planned | Transform gradient coordinates from absolute userSpace to bbox-relative [0,1] range using the shape's bounding box. Exact when gradient extent covers the shape. |
| `gradientTransform` (pure rotation) | `<a:lin ang="...">` | Planned | Decompose transform matrix → extract rotation angle → set `ang` attribute. Exact for pure rotations. |
| `gradientTransform` (uniform scale) | Adjust stop positions | Planned | Scale gradient stop `offset` values proportionally. Exact. |
| `gradientTransform` (non-uniform scale) | Adjust stop positions + direction | Planned | Scale stop positions and adjust gradient angle to account for aspect ratio change. Close approximation. |
| `gradientTransform` (skew) | **No DrawingML equivalent** | Planned | Approximate: decompose to closest rotation + adjusted stop positions. Lossy for strong skews. |
| `spreadMethod="pad"` | Default DrawingML behavior | Direct | |
| `spreadMethod="reflect"` | Expand stops in `gsLst` | Done | Mirror gradient stops to fill [0,1] range. |
| `spreadMethod="repeat"` | Expand stops in `gsLst` | Done | Duplicate gradient stops N times to fill [0,1] range. |
| `fx`/`fy` (radial focal point ≠ center) | **Limited mapping** | Planned | DrawingML `<a:path>` gradient has `fillToRect` for center positioning but no focal offset. Approximate by shifting `fillToRect` `l`/`t`/`r`/`b` values. Lossy for extreme off-center focal points. |
| `fr` (focal radius, SVG2) | **No DrawingML concept** | Planned | Add a flat-color region from center to `fr` as a zero-width gradient stop, then gradient from `fr` to `r`. Approximate. |
| `color-interpolation: linearRGB` | **DrawingML interpolates in sRGB** | Planned | Pre-compute intermediate gradient stops by sampling in linearRGB space, then convert each sample to sRGB and add as explicit stops. More stops = closer approximation. 10–20 extra stops should be visually indistinguishable. |

---

## 3. Transforms

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `translate(tx, ty)` | `<a:off x="..." y="...">` | Direct | |
| `rotate(angle)` | `<a:xfrm rot="...">` | Direct | Degrees × 60,000 |
| `scale(sx, sy)` | `<a:ext cx="..." cy="...">` (adjust size) | Direct | |
| `skewX(angle)` | **No `xfrm` skew** | Planned | Bake skew into custGeom path coordinates by multiplying each point by the skew matrix. Exact for paths. For text: convert to outlines first, then skew. For images: apply CSS-style skew to blipFill xfrm (needs testing). |
| `skewY(angle)` | **No `xfrm` skew** | Planned | Same approach as `skewX`. |
| `matrix(a,b,c,d,e,f)` (no skew component) | Decompose to `translate` + `rotate` + `scale` | Direct | Standard matrix decomposition. |
| `matrix(a,b,c,d,e,f)` (with skew) | Decompose + bake residual | Planned | Extract translate+rotate+scale into `xfrm`, bake residual skew into geometry. Exact for paths. |
| Nested transforms with accumulated skew | Skew compounds non-linearly | Planned | Flatten the full transform matrix at each leaf element, then decompose once. |

---

## 4. Clipping

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `clip-path` (rectangle) | DrawingML shape clipping | Direct | |
| `clip-path` (simple path) | DrawingML `custGeom` clip | Done | |
| `clip-path` (complex/self-intersecting) | **Limited** | Planned | Boolean path intersection: intersect clip path with shape geometry to produce a new custGeom that is the clipped result. Computationally heavy but exact. Libraries like Clipper2 can do this. |
| `clip-path` on `<g>` (group) | **DrawingML clips individual shapes** | Planned | Apply clip to each child shape individually. Or: if DrawingML `<p:grpSp>` supports clip (needs testing), apply at group level. |
| Nested `clip-path` | **DrawingML: one clip per shape** | Planned | Intersect nested clip paths into a single compound clip using boolean path intersection. |
| `clip-rule: evenodd` | Winding rule on clip geometry | Planned | Set correct winding on the custGeom clip path. Should work if geometry subpaths are emitted correctly. |
| `clip-rule: nonzero` | Default winding on clip geometry | Direct | |
| `clipPathUnits="objectBoundingBox"` | Coordinates in [0,1] range | Planned | Transform clip path coordinates from [0,1] to absolute shape bbox coordinates before applying. |
| `clipPathUnits="userSpaceOnUse"` | Default behavior | Direct | Clip coordinates in same space as content. |

---

## 5. Masking

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `<mask>` uniform opacity (solid rect) | Multiply alpha onto shape fill | Done | Detect single-rect mask with uniform opacity → apply as `<a:alpha>` on fill. |
| `<mask>` luminance (gradient content) | **No DrawingML mask** | Planned | For linear gradient masks: approximate with DrawingML alpha gradient on fill (`gradFill` with varying `<a:alpha>` stops). For complex masks: rasterize. |
| `<mask>` alpha mode | **No DrawingML mask** | Planned | Same strategy as luminance — alpha gradient approximation where possible, rasterize otherwise. |
| `<mask>` with complex content | **No DrawingML mask** | Rasterize | Render mask × content composited result as PNG. |
| `mask-type: luminance` vs `alpha` | Affects which channel is used | Planned | Handled in mask analysis — luminance converts RGB to grayscale alpha, alpha uses alpha channel directly. |
| `maskContentUnits="objectBoundingBox"` | Coordinates in [0,1] range | Planned | Transform mask content coordinates to shape bbox, then apply chosen fallback. |

---

## 6. Patterns

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `<pattern>` matching preset | `<a:pattFill>` | Done | Map to DrawingML preset patterns (dots, lines, diagonal). |
| `<pattern>` complex content | `<a:blipFill>` with `<a:tile>` | Done | Rasterize pattern tile to PNG, embed as media, tile across shape. |
| `patternUnits="objectBoundingBox"` | Tile size relative to shape | Planned | Scale rasterized tile dimensions based on shape bbox. |
| `patternUnits="userSpaceOnUse"` | Tile size in absolute units | Planned | Convert tile px dimensions to EMU, set `sx`/`sy` on `<a:tile>`. |
| `patternContentUnits="objectBoundingBox"` | Pattern content scaled to bbox | Planned | Scale rasterized tile content dimensions to shape bbox proportionally. |
| `patternTransform` (scale) | `<a:tile sx="..." sy="...">` | Planned | Map scale factors to tile `sx`/`sy` values (× 100,000). |
| `patternTransform` (rotation) | **No tile rotation in `blipFill`** | Planned | Pre-rotate the rasterized tile image before embedding. Or test if `<a:xfrm rot="...">` inside `blipFill` works. |
| `patternTransform` (skew) | **No tile skew** | Planned | Pre-apply skew to rasterized tile image. Approximate. |

---

## 7. Text

### 7.1 Font & Style Properties

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `font-family` | `<a:latin typeface="...">`, `<a:ea>`, `<a:cs>` | Direct | |
| `font-size` | `sz` on `<a:rPr>` (hundredths of pt) | Direct | |
| `font-weight: bold` | `b="1"` on `<a:rPr>` | Direct | |
| `font-weight` (numeric 100–900) | `b="1"` for ≥600, else `b="0"` | Direct | DrawingML is binary bold. Intermediate weights need font variant selection. |
| `font-style: italic` | `i="1"` on `<a:rPr>` | Direct | |
| `font-style: oblique` | `i="1"` on `<a:rPr>` | Direct | No oblique vs italic distinction in DrawingML. |
| `font-variant: small-caps` | `cap="small"` on `<a:rPr>` | Investigate | DrawingML has `cap` attribute. Verify rendering. |
| `font-stretch` (condensed/expanded) | **No DrawingML font width** | Planned | Select a condensed/expanded font variant if available in the family. Otherwise ignore — no runtime font stretching in DrawingML. |
| `text-decoration: underline` | `u="sng"` on `<a:rPr>` | Done | |
| `text-decoration: line-through` | `strike="sngStrike"` on `<a:rPr>` | Done | |
| `text-decoration: overline` | **No DrawingML overline** | Planned | Draw a separate thin line shape positioned above the text baseline. Or ignore (rare in SVG content). |
| `letter-spacing` | `spc` on `<a:rPr>` | Done | Value in hundredths of a point. |
| `word-spacing` | **No DrawingML attribute** | Planned | Insert extra space characters between words, or apply `spc` selectively on space-character runs. Approximate. PPT also ignores this. |

### 7.2 Text Layout & Positioning

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `text-anchor: start/middle/end` | `algn` on `<a:pPr>` | Direct | |
| `direction: rtl` | `rtl="1"` on `<a:pPr>` | Done | |
| `writing-mode: vertical-rl` | `vert="vert"` on `<a:bodyPr>` | Investigate | DrawingML supports vertical text via `vert` attribute. Verify CJK rendering. |
| `writing-mode: vertical-lr` | `vert="vert270"` on `<a:bodyPr>` | Investigate | Left-to-right vertical. Less common. |
| `dominant-baseline` | **Limited vertical alignment** | Planned | Adjust vertical offset on text position. Map `central`, `middle`, `hanging` to appropriate `anchor` values on `<a:bodyPr>`. Approximate. |
| `alignment-baseline` | **Limited** | Planned | Same approach as `dominant-baseline`. |
| `baseline-shift: super` | `baseline` on `<a:rPr>` | Investigate | DrawingML has `baseline` attribute (percentage of font size). Map `super` → positive %, `sub` → negative %. |
| `baseline-shift: sub` | `baseline` on `<a:rPr>` | Investigate | Same. |
| Per-character `dx`/`dy` arrays | **No per-character offset in DrawingML** | Planned | Split into individual single-character text boxes, each absolutely positioned. Preserves visual appearance but loses text editability and reflow. |
| Per-character `x`/`y` absolute arrays | **No per-character absolute positioning** | Planned | Same as `dx`/`dy` — individual positioned text boxes. |
| Per-character `rotate` | **No per-glyph rotation** | Planned | Convert each rotated character to a separate rotated text box. Or convert to custGeom glyph outlines with rotation. Both lose editability. |
| `textLength` + `lengthAdjust="spacing"` | **No text length forcing** | Planned | Compute effective `letter-spacing` to achieve target text length → emit as `spc`. Approximate. |
| `textLength` + `lengthAdjust="spacingAndGlyphs"` | **No glyph scaling** | Planned | Approximate with `spc` adjustment + font size tweaking. Lossy. |

### 7.3 Text Path

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `<textPath>` on simple curve | `prstTxWarp` on `<a:bodyPr>` | Planned | Classify the path against WordArt presets (wave, arch, circle, etc.). If confidence exceeds threshold → editable text with warp. Beats PPT (which converts to outlines). |
| `<textPath>` on arbitrary curve | **No arbitrary text path** | Planned | Convert text glyphs to custGeom outlines, position along path with rotation. Loses editability. Matches PPT behavior. |
| `<textPath startOffset="...">` | Offset along path | Planned | When using WordArt: no equivalent. When using custGeom outlines: adjust glyph start position along path. |
| `<textPath method="stretch">` | Glyph distortion along path | Planned | When using custGeom outlines: warp glyph geometry to follow path curvature. Complex but feasible. |

### 7.4 BiDi & Internationalization

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `direction: rtl` | `rtl="1"` on `<a:pPr>` | Done | |
| `direction: ltr` | Default (no attribute) | Done | |
| Auto-detect RTL from content | `rtl="1"` based on Unicode BiDi | Done | Uses bidirectional character category analysis |
| `unicode-bidi: bidi-override` | **No fine-grained BiDi control** | Planned | DrawingML BiDi is paragraph-level only. For mixed-direction runs within a paragraph, split into separate paragraphs or accept paragraph-level direction. |
| `xml:lang` / `lang` | `lang` on `<a:rPr>` | Planned | Map BCP-47 language tags. Auto-detect from Unicode script for Arabic → `ar-SA`, Hebrew → `he-IL`, etc. |

---

## 8. Filters

### 8.1 Mappable to Native DrawingML Effects

| SVG Filter | DrawingML Effect | Status | Notes |
|------------|-----------------|--------|-------|
| `feGaussianBlur` (standalone) | `<a:softEdge rad="...">` | Done | Approximate — `softEdge` fades edges rather than uniform blur. Radius mapping: SVG stdDeviation → EMU radius. |
| `feDropShadow` | `<a:outerShdw>` | Done | Map: `dx`→`dist`+`dir`, `dy`→`dist`+`dir`, `stdDeviation`→`blurRad`, `flood-color`→shadow color. Close match. |
| `feOffset` + `feFlood` + `feComposite` (shadow pattern) | `<a:outerShdw>` | Done | Detect the common drop-shadow filter chain and emit as single shadow effect. |
| `feGaussianBlur` + `feMerge` (glow pattern) | `<a:glow rad="..." >` | Planned | Detect glow pattern: blur + merge with original. Map blur radius to glow radius. |
| `feColorMatrix(type="saturate")` | `<a:satMod>` on color | Planned | Map saturation value to `satMod` percentage (× 100,000). Partial — only works on solid fills. |
| `feColorMatrix(type="hueRotate")` | `<a:hueOff>` on color | Planned | Map rotation angle to `hueOff` degrees. Very approximate — SVG applies to rendered pixels, DrawingML to fill colors. |
| `feFlood` + `feBlend(mode="multiply")` | `<a:duotone>` | Investigate | DrawingML duotone may approximate some color overlay effects. |

### 8.2 Must Rasterize

| SVG Filter | Why | Notes |
|------------|-----|-------|
| `feColorMatrix(type="luminanceToAlpha")` | No DrawingML equivalent | Converts color to alpha mask. Rasterize. |
| `feMorphology(erode)` | No equivalent | Shrinks/thickens shapes. Rasterize. |
| `feMorphology(dilate)` | No equivalent | Same. |
| `feDisplacementMap` | No equivalent | Pixel-level displacement. Rasterize. |
| `feTurbulence` | No equivalent | Procedural noise generation. Rasterize. |
| `feConvolveMatrix` | No equivalent | Arbitrary kernel convolution. Rasterize. |
| `feDiffuseLighting` | Fundamentally different from DrawingML 3D | Could explore `<a:scene3d>` + `<a:sp3d>` with light rigs for simple cases. Mostly rasterize. |
| `feSpecularLighting` | Same | Same. |
| `feComponentTransfer(type="gamma")` | No per-channel gamma | Pre-apply gamma to color values for solid fills. Must rasterize for gradients/images. |
| `feComponentTransfer(type="table")` | No lookup table | Rasterize. |
| `feImage` | External image in filter chain | Could emit as separate blipFill shape in simple cases. Context-dependent. |
| Complex multi-primitive chains | DrawingML effects are not composable | EMF or rasterize the entire filter result. |

---

## 9. Markers

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `marker-start` (simple arrow) | `<a:headEnd>` | Done | Maps to DrawingML line ending presets. |
| `marker-end` (simple arrow) | `<a:tailEnd>` | Done | Same. |
| `marker-start` (complex shape) | Expand to separate custGeom | Done | Create a new shape with marker geometry, positioned and rotated at path start. |
| `marker-end` (complex shape) | Expand to separate custGeom | Done | Same at path end. |
| `marker-mid` | Expand to separate custGeom per vertex | Done | One marker shape per interior vertex. Increases shape count. Could batch identical markers in a group. |
| `orient="auto"` | Rotation computed per vertex | Done | Rotate marker to match path tangent at attachment point. |
| `orient="auto-start-reverse"` | Start marker flipped 180° | Planned | Reverse rotation for start marker. Simple addition. |
| `markerUnits="strokeWidth"` | Scale marker by stroke width | Done | Marker size multiplied by element's stroke-width. |
| `markerUnits="userSpaceOnUse"` | Absolute marker size | Done | Marker size independent of stroke-width. |
| `refX`/`refY` anchor offsets | Translate marker origin | Done | Offset marker position by reference point. |
| `overflow="visible"` on marker | Marker content can exceed marker viewport | Planned | Default is hidden. When visible, don't clip marker content to `markerWidth`/`markerHeight`. |

---

## 10. Document Structure

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `<svg>` viewBox | Viewport mapping | Done | Full viewBox + preserveAspectRatio support. |
| `preserveAspectRatio` (all 9 alignments + meet/slice) | Viewport engine | Done | |
| `<g>` (group) | `<p:grpSp>` | Direct | |
| `<defs>` | Resolved inline | Direct | Referenced elements (gradients, patterns, clips) resolved at point of use. |
| `<use>` | Expanded inline | Done | Style inheritance, viewBox, preserveAspectRatio handled. |
| `<symbol>` | Expanded inline (like `<use>`) | Done | |
| `<switch>` with `systemLanguage` | Resolve at parse time | Planned | Pick best language match. |
| `<switch>` with `requiredFeatures` | Resolve at parse time | Planned | Check against supported feature set. |
| `<foreignObject>` | **No equivalent** | Rasterize | Render HTML content via headless browser, embed as PNG. |
| `<a xlink:href="...">` (hyperlinks) | `<a:hlinkClick r:id="...">` | Planned | Map SVG hyperlinks to DrawingML click actions with relationship to URL. |
| `<title>` / `<desc>` | `<p:cNvPr descr="...">` | Planned | Map accessibility text to shape alt text. |
| `<metadata>` | Ignored | Ignore | No DrawingML equivalent for arbitrary metadata. |
| `overflow: hidden` on `<svg>` | Viewport clipping | Done | Clip content to SVG viewport bounds. |
| `overflow: visible` on nested `<svg>` | No clipping | Planned | Allow content to extend beyond nested SVG viewport. |

---

## 11. CSS & Styling

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `<style>` blocks | Full CSS cascade | Done | Resolved via tinycss2 at parse time. |
| Class selectors (`.foo`) | Resolved at parse time | Done | |
| ID selectors (`#bar`) | Resolved at parse time | Done | |
| Attribute selectors | Resolved at parse time | Done | |
| `@font-face` web fonts | Font embedding in PPTX | Done | Download and embed referenced fonts. |
| `@media` queries | Resolved at fixed viewport | Planned | Evaluate media queries at the SVG's viewport dimensions. |
| `@import` | Follow imports at parse time | Planned | Fetch and merge imported stylesheets. |
| CSS custom properties (`var()`) | Resolved at parse time | Planned | Substitute variable values during CSS cascade. |
| `calc()` | Resolved at parse time | Planned | Evaluate calc expressions during property resolution. |
| `inherit` | Resolved by CSS cascade | Direct | |
| `initial` / `unset` | Resolved by CSS cascade | Planned | Reset to initial or inherited value. |
| Inline `style` attributes | Resolved at parse time | Direct | Highest specificity in cascade. |
| Presentation attributes | Resolved at parse time | Direct | Lowest specificity, overridden by CSS. |

---

## 12. Color

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| Named colors (`red`, `blue`, etc.) | `srgbClr` | Direct | Resolved to hex at parse time. |
| `#rrggbb` / `#rgb` | `srgbClr val="RRGGBB"` | Direct | |
| `#rrggbbaa` / `#rgba` | `srgbClr` + `<a:alpha>` | Direct | |
| `rgb()` / `rgba()` | `srgbClr` + `<a:alpha>` | Direct | |
| `hsl()` / `hsla()` | Convert to sRGB → `srgbClr` | Direct | Converted at parse time. |
| `currentColor` | Resolved at parse time | Direct | Inherits from `color` property. |
| `color-interpolation: linearRGB` | **DrawingML uses sRGB** | Planned | See gradient section (§2). Pre-compute intermediate stops. |
| `color-profile` / ICC colors | **No DrawingML ICC** | Ignore | Convert to sRGB. Lossy for wide-gamut content. |
| `oklab()` / `oklch()` (CSS Color 4) | Convert to sRGB | Planned | Parse and convert to sRGB hex at parse time. |
| System colors (`Canvas`, `CanvasText`) | Map to defaults | Planned | Use sensible defaults (white, black). |

---

## 13. Rendering Hints

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `image-rendering: pixelated` | **No equivalent** | Ignore | DrawingML always interpolates images. Cannot control. |
| `image-rendering: crisp-edges` | **No equivalent** | Ignore | Same. |
| `shape-rendering: crispEdges` | **No equivalent** | Ignore | Renderer decides anti-aliasing. |
| `shape-rendering: geometricPrecision` | **No equivalent** | Ignore | Default rendering. |
| `text-rendering: optimizeLegibility` | **No equivalent** | Ignore | Font renderer decides. |
| `color-interpolation-filters` | **Affects filter math** | Planned | When rasterizing filters, use the correct color space for intermediate computations. |

---

## 14. Images

| SVG | DrawingML | Status | Notes |
|-----|-----------|--------|-------|
| `<image>` with raster (PNG/JPEG) | `<a:blipFill>` | Direct | |
| `<image>` with SVG | Recursive conversion or `blipFill` | Planned | Could recursively convert nested SVG, or rasterize and embed. |
| `<image>` with data URI | Extract and embed | Done | Decode base64 data URI, embed as media. |
| `preserveAspectRatio` on `<image>` | `<a:stretch>` / `<a:tile>` + offset | Done | Map alignment and meet/slice to blipFill crop/stretch. |
| `image-rendering` | See §13 | Ignore | |

---

## Summary: Substitute Complexity Tiers

### Tier A — Arithmetic only (no visual loss)
- `stroke-dashoffset` → rotate dash array
- `gradientTransform` (rotation) → `lin ang`
- `gradientUnits="userSpaceOnUse"` → coordinate transform
- `spreadMethod reflect/repeat` → stop expansion (done)
- Uniform opacity mask → alpha shortcut (done)

### Tier B — Structural changes (minor visual differences possible)
- `opacity` on `<g>` → per-child alpha (non-overlapping) or selective rasterization
- `paint-order` → duplicate shape
- `vector-effect: non-scaling-stroke` → adjust stroke-width by transform scale
- `gradientTransform` (scale) → stop position adjustment
- Gradient masks → alpha gradient approximation
- `word-spacing` → extra space characters
- Radial focal point → `fillToRect` adjustment
- `color-interpolation: linearRGB` → extra interpolated stops

### Tier C — Geometry transformation (exact but computationally heavy)
- `skewX`/`skewY` → bake into custGeom coordinates
- Complex clip-path → boolean path intersection
- Nested clip-paths → intersect to single clip
- `textPath` → custGeom glyph outlines
- Per-character `dx`/`dy`/`rotate` → individual text boxes

### Tier D — Must rasterize (loses editability)
- `mix-blend-mode` → pre-composite to PNG
- Complex filter chains → EMF or PNG
- `opacity` on `<g>` with overlapping children → group rasterization
- `<foreignObject>` → headless browser render
- Luminance masks with complex content → composited PNG
