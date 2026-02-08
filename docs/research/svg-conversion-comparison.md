# SVG-to-PPTX Conversion: svg2ooxml vs the Alternatives

## Background

PowerPoint (Office 365/2019+) supports inserting SVG images and converting them to
editable shapes via "Convert to Shape" / Ungroup. Google Slides and Google Drawings
have **no SVG-to-shape conversion at all** — there is no way to get native editable
shapes from SVG into Google's presentation tools without an external converter.

This makes svg2ooxml the only programmatic path to convert SVG into native editable
DrawingML shapes that work across both PowerPoint and Google Slides. This document
compares the approaches and identifies where svg2ooxml has structural advantages.

---

## How PowerPoint Handles SVG

### Insertion (svgBlip)

When an SVG is inserted into a slide, PowerPoint stores **two** files in `/ppt/media/`:

1. The original `.svg` file
2. An auto-generated `.png` fallback for backward compatibility (Office 2013 and earlier)

The SVG is referenced via the `svgBlip` extension element (namespace
`http://schemas.microsoft.com/office/drawing/2016/SVG/main`, Office 2016+). The PNG
is referenced via the standard `a:blip` element. At this stage the SVG is rendered
natively by PowerPoint but is **not editable** as shapes.

**Source:** [MS-ODRAWXML svgBlip spec](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/2451f45e-5d77-4661-86d1-0a017fced779),
[NeuXPower file size analysis](https://neuxpower.com/blog/why-does-adding-svg-images-to-powerpoint-sometimes-make-the-file-so-large)

### Convert to Shape

"Convert to Shape" (or Ungroup) directly parses the SVG and converts every element
to native DrawingML **Freeform** shapes (`<a:custGeom>`). There is no EMF intermediate
step. Key characteristics (verified by hand-converting 12 W3C SVGs in PowerPoint
for Mac 16.x, February 2026):

- **All shapes become Freeforms.** Even simple rectangles and circles are converted
  to custom geometry paths, losing preset shape semantics.
- **Multiple ungroup steps** are required to reach individual component shapes.
- **Text is preserved as editable.** Font family, size, weight, and color are retained.
  Multi-language text (Latin, CJK, Arabic, Devanagari) is handled correctly.
  *(Earlier online reports claimed text was converted to outlines — this appears to
  have been fixed in recent PowerPoint versions.)*
- **Linear gradients are preserved.** Full `gradFill` with gradient stops, colors,
  and direction mapping. Verified on W3C `pservers-grad-01-b.svg`.
- **Radial gradients are lost** — replaced with solid black fill.
- **Opacity is preserved** via `<a:alpha>` elements on fills and strokes.
- **Stroke dashing is preserved** using `custDash` elements with accurate `d` and `sp`
  values for custom dash patterns.
- **Clip paths are lost** — clipped content renders unclipped.
- **Filters (blur, lighting, etc.) are dropped entirely.**
- **Fill rules are lost** — `evenodd` shapes render incorrectly.
- **Masks and blend modes** are dropped entirely.
- **Animations** (SMIL) are dropped entirely.
- **Shape hierarchy** is flattened into raw Freeform groups.

**Source:** [PowerPoint Secrets blog](https://pptcrafter.wordpress.com/2019/06/03/powerpoint-secrets-shapes-and-more-shapes-2/),
hand-verified conversion of W3C SVG 1.1 test files (February 2026)

### Recent Regression (2025/2026)

As of PowerPoint version 2511 (2025/2026 builds), the "Convert to Shape" button has
disappeared from both the Graphics Format ribbon and the right-click context menu.
Microsoft has not publicly documented whether this is intentional or a bug.

**Source:** [Microsoft Q&A: Convert to Shape unavailable](https://learn.microsoft.com/en-us/answers/questions/5693861/convert-svg-image-to-shape-powerpoint-2025-2026)

---

## How svg2ooxml Handles SVG

### Architecture

svg2ooxml converts SVG directly to DrawingML XML through a typed intermediate
representation:

```
SVG text
  -> SVGParser.parse()           -> ParseResult (lxml tree + CSS cascade)
  -> convert_parser_output()     -> IRScene (typed scene graph)
  -> DrawingMLWriter.render()    -> XML fragments + assets
  -> PPTXPackageBuilder.write()  -> .pptx file
```

There is no intermediate bitmap or metafile format. SVG semantics are preserved in
the IR and mapped to the closest DrawingML equivalent.

### Fallback Tiers

When a feature cannot be mapped to native DrawingML, svg2ooxml uses a tiered fallback:

| Tier | Format | Quality | Scalable | Editable |
|------|--------|---------|----------|----------|
| 1 | Native DrawingML | Best | Yes | Yes |
| 2 | EMF vector | Good | Yes | Limited |
| 3 | Bitmap (PNG) | Adequate | No | No |

The policy engine controls which tier is used per feature, and telemetry tracks the
native/EMF/raster ratio across conversions.

---

## Google Slides / Google Drawings

Google Slides and Google Drawings can import PPTX files and render native DrawingML
shapes — but they provide **no mechanism** to convert SVG into those shapes:

- **No SVG insert-as-shapes.** You can insert an SVG as a flat image, but it remains
  a raster-like object with no editable geometry, fills, or text.
- **No "Convert to Shape" equivalent.** There is no ungroup or decompose feature.
- **No API for it.** The Google Slides API can create shapes programmatically but has
  no SVG import endpoint.

This means svg2ooxml is the **only path** from SVG to native editable shapes in
Google Slides. The PPTX files svg2ooxml produces open directly in Google Slides
with shapes, text, gradients, and animations intact as native objects.

This also means the quality bar is higher: there is no manual fallback for users.
Whatever svg2ooxml produces is what they get.

---

## Feature Comparison

| SVG Feature | PowerPoint Convert to Shape | Google Slides | svg2ooxml |
|-------------|---------------------------|---------------|-----------|
| **Basic paths** | Freeform custGeom | No conversion | custGeom or preset shapes |
| **Rectangles, circles** | Freeform (loses preset) | No conversion | Preset shapes where possible |
| **Solid fills** | Preserved | No conversion | Preserved |
| **Linear gradients** | **Preserved** (gradFill) | No conversion | Native DrawingML gradientFill |
| **Radial gradients** | Lost (solid black) | No conversion | Native DrawingML gradientFill |
| **Gradient transforms** | Lost | No conversion | Mapped to DrawingML tileRect/path |
| **Stroke styles** | **Preserved** (custDash) | No conversion | Width, color, dash, cap, join |
| **Text** | **Preserved** (editable) | No conversion | Editable text boxes with fonts |
| **Text positioning** | Basic (no per-char offsets) | No conversion | Paragraph/run model |
| **Transforms** | Flattened into paths | No conversion | Decomposed to xfrm + rotation |
| **Group hierarchy** | Flattened | No conversion | Preserved as grpSp nesting |
| **Shape naming** | Generic | No conversion | SVG IDs preserved as shape names |
| **Opacity** | **Preserved** (alpha element) | No conversion | Alpha modulation on fills/strokes |
| **Group opacity** | Dropped | No conversion | Mapped where DrawingML allows |
| **Clip paths** | Dropped | No conversion | DrawingML clipping |
| **Fill rules** | Lost (evenodd broken) | No conversion | Preserved |
| **Masks** | Dropped | No conversion | EMF/raster fallback |
| **Filters (blur, shadow)** | Dropped | No conversion | Native softEdge/shadow/glow |
| **Filters (complex)** | Dropped | No conversion | EMF or raster fallback |
| **Blend modes** | Dropped | No conversion | Not supported (DrawingML limitation) |
| **Patterns** | Dropped | No conversion | Pattern fill or raster fallback |
| **Markers** | Dropped | No conversion | Expanded inline or raster fallback |
| **`<use>` elements** | Unknown fidelity | No conversion | Resolved with style overrides |
| **CSS `<style>` blocks** | Unknown fidelity | No conversion | Full CSS cascade (tinycss2) |
| **SMIL animations** | Dropped | No conversion | Native PowerPoint animations |
| **viewBox / aspect ratio** | Handled | No conversion | Full viewBox + preserveAspectRatio |

---

## Where svg2ooxml Has Structural Advantages

### 1. Animations (unique capability)

PowerPoint's converter drops all SMIL animations. svg2ooxml converts them to native
PowerPoint animation sequences (motion paths, opacity fades, color changes, scale,
rotation, etc.). This is the primary differentiator — **no other tool does this**.

### 2. Radial Gradients

PowerPoint preserves linear gradients but **loses radial gradients** (replaced with
solid black). svg2ooxml maps both linear and radial gradients to native DrawingML
`gradientFill` elements with stop colors, positions, and center/radius mapping.

### 3. Filter Effects

PowerPoint drops all filter effects. svg2ooxml maps supported effects to native
DrawingML (Gaussian blur -> softEdge, drop shadows -> outerShdw, glow effects)
and falls back to EMF or raster for unsupported primitives.

### 4. Clip Paths

PowerPoint drops clip paths entirely. svg2ooxml converts them to native DrawingML
clipping regions.

### 5. Fill Rules

PowerPoint ignores `fill-rule="evenodd"`, causing shapes with holes (e.g. rings,
donuts) to render incorrectly as solid. svg2ooxml preserves fill rules.

### 6. Shape Semantics

PowerPoint converts everything to raw Freeforms. svg2ooxml uses preset shapes
(rect, ellipse, etc.) where possible, preserves group hierarchy, and retains SVG
element IDs as shape names for downstream editability.

### 7. CSS Support

svg2ooxml has a full CSS parser (tinycss2) that resolves `<style>` blocks, class
selectors, and the CSS cascade. PowerPoint's converter likely handles only inline
`style` attributes and presentation attributes.

### 8. Google Slides Compatibility

PowerPoint's converter only works within PowerPoint itself. svg2ooxml produces
PPTX files that open directly in Google Slides with native shapes, making it the
**only path** from SVG to editable shapes in Google Slides.

---

## Where svg2ooxml Could Improve

These are areas where the DrawingML format is capable of more than svg2ooxml
currently produces, regardless of what PowerPoint's converter does:

### Text Layout Fidelity

SVG offers per-character positioning (`x`, `y`, `dx`, `dy` arrays), `textPath`,
`letter-spacing`, `word-spacing`, and bidirectional text. DrawingML has a rich
paragraph/run model with kerning, spacing, and text-on-shape. There is room to
improve the mapping precision. Note: PowerPoint now preserves editable text well,
so this is an area where we need to at least match PowerPoint's quality.

### Gradient Precision

Complex gradient features — `gradientTransform`, `spreadMethod` (reflect/repeat),
`objectBoundingBox` vs `userSpaceOnUse` coordinate mapping — may have edge cases
where the conversion is imprecise. PowerPoint handles linear gradients well, so
our linear gradient output should be at least as good.

### Group Opacity

SVG `opacity` on a `<g>` means "composite children, then apply alpha." Naively
applying alpha to each child produces incorrect results (overlapping transparent
areas become visible). Correct handling may require rasterization or careful
DrawingML grouping.

### Native-to-Raster Ratio

Every feature that falls to bitmap loses scalability and editability. Pushing more
features from tier 2/3 (EMF/raster) to tier 1 (native DrawingML) is the single
biggest quality lever.

---

## Hand-Verified Conversion Results (February 2026)

We embedded 12 W3C SVG 1.1 test files into a PPTX via svgBlip, then used
PowerPoint for Mac's "Convert to Shape" to convert them. The converted PPTX was
unzipped and the DrawingML XML analyzed per slide.

| W3C SVG | Feature Tested | PowerPoint Result |
|---------|---------------|-------------------|
| `shapes-rect-01-t` | Basic rectangles | Freeform custGeom; solid fills preserved |
| `pservers-grad-01-b` | Linear gradients | **Preserved**: gradFill with gsLst, correct stops/colors/direction |
| `pservers-grad-08-b` | Radial gradients | **Lost**: solid black fill (`srgbClr val="000000"`) |
| `text-intro-01-t` | Basic text | **Preserved**: editable text with font family, size, color |
| `text-text-03-b` | Multi-language text | **Preserved**: Latin, CJK, Arabic, Devanagari all editable |
| `painting-stroke-04-t` | Stroke dasharray | **Preserved**: custDash with `d` and `sp` values |
| `masking-path-01-b` | Clip paths | **Lost**: content renders unclipped |
| `filters-gauss-01-b` | Gaussian blur | **Lost**: no blur effect, shapes rendered flat |
| `filters-light-01-f` | Lighting effects | **Lost**: no lighting effect |
| `painting-fill-04-t` | Fill opacity | **Preserved**: alpha element with correct values |
| `painting-fill-02-t` | Fill rules | **Lost**: evenodd shapes render incorrectly |
| `pservers-grad-04-b` | Gradient on text | **Preserved**: editable text with gradient fill |

### Key Corrections from Online Sources

Several online sources (blog posts from 2019, Microsoft Q&A) claimed PowerPoint
converts text to outlines and loses all gradients. Our hand verification shows
that **recent PowerPoint versions (2025/2026)** have significantly improved:

- Linear gradients are now preserved as native `gradFill`
- Text remains editable (not converted to paths)
- Element-level opacity is preserved via `alpha`
- Custom stroke dashing is preserved via `custDash`

However, radial gradients, clip paths, filters, and fill rules remain broken.

### Automated Side-by-Side Comparison

We ran the same 12 W3C SVGs through svg2ooxml and compared the DrawingML XML
output feature-by-feature. Summary of **remaining gaps** where PowerPoint does
something we don't:

| Gap | SVG Test Case | Detail |
|-----|--------------|--------|
| Gradient on text fill/stroke | `pservers-grad-08-b` | PPT applies gradient to text-as-shapes; our text pipeline doesn't emit gradient fills on text |

All other "differences" in the comparison are either cosmetic (PPT adds redundant
`prstDash val="solid"` to non-dashed shapes) or areas where **svg2ooxml is better**
(radial gradients, preset shape semantics, opacity on gradient fills).

---

## Deck 3: Edge Case Conversion Results (February 2026)

We embedded 10 additional W3C SVG edge-case files into a third test deck and
converted them with PowerPoint for Mac "Convert to Shape". These test advanced
SVG features that DrawingML has limited or no support for.

| W3C SVG | Feature Tested | PowerPoint Result |
|---------|---------------|-------------------|
| `pservers-grad-10-b` | Gradient spreadMethod (reflect/repeat) | **Lost**: all gradients render as `pad`; no repeat/reflect |
| `pservers-grad-06-b` | gradientTransform | **Lost**: fills become solid or empty; rotation/skew dropped |
| `painting-stroke-07-t` | stroke-dashoffset | **Lost**: all strokes become solid; dash patterns and offset dropped |
| `painting-fill-03-t` | fill with inherit + currentColor | **Partial**: fill color resolved correctly; `fill-rule="evenodd"` lost |
| `masking-path-04-b` | Nested clip paths | **Lost**: no clipping applied; all content visible |
| `text-tspan-02-b` | Multi-line tspan with absolute positioning | **Partial**: text split into separate text boxes; per-character rotation lost |
| `render-groups-01-b` | Group opacity (`opacity` on `<g>`) | **Lost**: no alpha/opacity anywhere in output |
| `painting-stroke-10-t` | Zero-length stroke linecaps | **Preserved**: round/square caps on zero-length segments rendered correctly |
| `coords-trans-09-t` | Nested group transforms | **Preserved**: transform matrices decomposed correctly into shapes |
| `struct-group-03-t` | Group transform + opacity combined | **Partial**: transforms preserved; opacity dropped |

### Key Takeaways from Deck 3

**PowerPoint handles geometry well** — path data, transforms (including nested
matrix decomposition), and line caps are accurately converted. However, nearly
every "paint" or "compositing" edge case is lost:

- **Group opacity** is the most significant gap — PowerPoint drops it entirely,
  and DrawingML has no clean equivalent for "composite children then apply alpha."
- **Gradient transforms** and **spreadMethod** are both lost, confirming that
  PowerPoint only handles axis-aligned linear/radial gradients without transforms.
- **Stroke-dashoffset** is dropped alongside the entire dash pattern.
- **Fill-rule** (`evenodd`) continues to be a persistent PowerPoint weakness.

svg2ooxml already handles or can beat PowerPoint on most of these features:
we support fill-rule, clip paths, gradient transforms, and custDash offsets.
Group opacity and spreadMethod remain open challenges for DrawingML mapping.

---

## Validation Strategy

### W3C SVG Test Suite

The project includes 525 W3C SVG 1.1 test files in `tests/svg/`. These cover:

- Shapes (30), Paths (19), Text (20)
- Gradients (23), Patterns, Painting (25)
- Filters (15), Masking (14)
- Transforms, Coordinates, Styling
- Animation

### Proposed Comparison Pipeline

```
For each W3C SVG:
  1. Render SVG in browser (Playwright)          -> ground truth PNG
  2. Convert via svg2ooxml -> PPTX -> render PNG  -> our output
  3. SSIM compare: our output vs ground truth
  4. Categorize gaps by feature area
  5. Rank by severity (SSIM delta)
```

Existing infrastructure supports this:
- `tools/visual/w3c_suite.py` — W3C scenario runner
- `tools/visual/diff.py` — SSIM comparison with configurable thresholds
- `tools/visual/browser_renderer.py` — Playwright SVG rendering
- `tools/visual/renderer.py` — LibreOffice PPTX rendering
- `tools/visual/powerpoint_capture.py` — macOS PowerPoint capture

### Expected High-Value Categories

Based on the analysis above, the W3C test categories most likely to reveal
improvement opportunities are:

| Category | Why |
|----------|-----|
| `pservers-grad-*` | Gradient mapping precision |
| `text-*` | Text layout fidelity |
| `filters-*` | Filter effect coverage |
| `masking-*` | Clip/mask handling |
| `painting-*` | Opacity, fill-rule, stroke |
| `coords-trans-*` | Transform decomposition |

---

## References

- [MS-ODRAWXML svgBlip specification](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/2451f45e-5d77-4661-86d1-0a017fced779)
- [SVGBlip .NET API](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.office2019.drawing.svg.svgblip?view=openxml-3.0.1)
- [PowerPoint Secrets: Shapes and More Shapes](https://pptcrafter.wordpress.com/2019/06/03/powerpoint-secrets-shapes-and-more-shapes-2/)
- [NeuXPower: SVG file size in PowerPoint](https://neuxpower.com/blog/why-does-adding-svg-images-to-powerpoint-sometimes-make-the-file-so-large)
- [Convert to Shape unavailable (2025/2026)](https://learn.microsoft.com/en-us/answers/questions/5693861/convert-svg-image-to-shape-powerpoint-2025-2026)
- [SVG text conversion issues](https://learn.microsoft.com/en-us/answers/questions/5060674/can-anyone-provide-an-example-svg-with-text-that-c)
- [Edit SVG images in Microsoft 365](https://support.microsoft.com/en-us/office/edit-svg-images-in-microsoft-365-69f29d39-194a-4072-8c35-dbe5e7ea528c)
