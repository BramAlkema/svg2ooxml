# Anisotropic Gaussian Blur Emulation in DrawingML (PPTX)

Date: 2026-05-24
Source: SplatThis 2D-Gaussian-splat PNG → PPTX pipeline (see
`~/projects/SplatThis/tmp/anisotropy_*.py` and
`tmp/anisotropy_refine_compare.html`).

## The gap

SVG's `<feGaussianBlur>` accepts `stdDeviation="sx sy"` — anisotropic
blur is a single primitive.

DrawingML's `<a:blur>` is **isotropic only**. It takes a single
`rad` (and `grow` flag). There is no `stdDevX` / `stdDevY`. The
DrawingML spec offers no native anisotropic-Gaussian primitive.

For any SVG using anisotropic feGaussianBlur (or any pipeline that
wants anisotropic Gaussian look-and-feel, e.g. 2D Gaussian splats),
DrawingML output has to approximate.

## What does not work

Tested in real PowerPoint via `tools/ppt_research/powerpoint_capture_cli`
(soffice/LibreOffice has a known rendering bug — do not validate PPTX
visuals there):

- **N-shape Gaussian stack** (7 offset blurred shapes along the long
  axis). Disks remain visible at every offset; no smooth Gaussian.
- **`<a:outerShdw>` directional shadow** with high `blurRad`.
  Produces a disconnected blob offset from the source; cannot replace
  the splat itself.
- **Two offset blurred shapes** (main + offset halo). Reads as two
  splats, not one elongated one.
- **`<a:softEdge>`**. Structurally not a Gaussian — it shrinks the
  shape inward and feathers the edge. Leaves a small hard core with a
  feathered halo. Useful effect, wrong shape.
- **Gradient stops alone** (radial / linear with triangular alpha).
  Produces a tiny dim core, abrupt outer halo — the classic
  "stained-glass" splat. Bright area is ~5% of visual size.

## What works — recipe N

After comparing 9 refinement variants in real PowerPoint, the
cleanest anisotropic-Gaussian approximation is:

1. **Ellipse** with the splat's long-axis aspect ratio (the aspect
   ratio is what fakes the anisotropy).
2. **7-stop sigmoid alpha gradient** along the long axis:
   - `t in [0..1]` across the long axis
   - `alpha(t) = (1 / (1 + exp(-k * (t - 0.15)))) * (1 / (1 + exp(k * (t - 0.85)))) * peak_alpha`
   - `k ≈ 12`
   - Flat bright core in the middle ~70%, sharp shoulders near both
     ends. The sigmoid keeps the core flat so the blur owns the
     falloff.
3. **Isotropic `<a:blur>`** with `rad ≈ 25–35% of the minor-axis
   radius (in EMU)`.
   - Smaller blur: ellipse silhouette pokes through.
   - Larger blur: color dilutes too much.

The sigmoid stops are the key insight. Triangular or Gaussian-sampled
stops still let the ellipse silhouette show because the blur has to
do all the smoothing AND fight a tapered alpha at the same time.
Sigmoid keeps the alpha flat in the bright zone so blur only has to
soften the silhouette edge.

## Variants ruled out

| Variant | Recipe | Issue |
|---------|--------|-------|
| C (prior baseline) | rect + 3-stop triangle + iso blur | Crisp center, abrupt top/bottom — bar-like |
| G | ellipse + 3-stop triangle + iso blur | Visible ellipse silhouette bulge |
| H | rect + 7-stop Gaussian gradient + iso blur | ≈ identical to C |
| I | ellipse + 7-stop Gaussian gradient + iso blur | Smoother than G, but tip-points still visible |
| J | ellipse + 7-stop Gaussian + medium blur | Clean, close second to N |
| L | ellipse + sigmoid + small blur | Spotlight-column character |
| K | ellipse Gaussian + stacked halo | Reads as two splats |
| M | ellipse Gaussian + large blur | Over-soft, washed out |
| **N** | **ellipse + sigmoid + medium blur** | **Winner: smooth Gaussian falloff, no silhouette, clean elongation** |

## Implications for svg2ooxml

If/when svg2ooxml grows an anisotropic-Gaussian path (e.g. mapping
`feGaussianBlur stdDeviation="sx sy"` with `sx != sy` to a PPTX
effect chain rather than falling back to a bitmap blip):

- Don't try to reproduce the anisotropy via a second `<a:blur>` layer
  or stacked outerShdw. None of the stacking strategies worked in real
  PowerPoint.
- Convert the bounding shape to an **ellipse with the source
  anisotropy ratio baked into width/height**, then add **sigmoid
  gradient stops** along the long axis and **isotropic `<a:blur>`**
  for the cross-axis softening.
- Validate any new recipe with the `powerpoint_capture_cli` rig, not
  soffice. soffice misrenders blur + gradient stacks in ways that
  look very different from real PowerPoint.

## Cross-format observation

We also reconfirmed via the SVG/PPTX kitchen-sink test that:

- **Both formats have a true Gaussian blur primitive** that is
  dramatically better than gradient-stop approximations.
- **`<feGaussianBlur>` (linearRGB)** and **`<a:blur>`** produce visually
  near-identical Gaussian shapes when matched on radius.
- **Stops produce tiny dim cores in both formats** — same limitation.

So the right strategy in both formats is: use the format-native blur,
let alpha gradients do whatever post-blur tinting they need.

## Validation tooling

- `~/projects/openxml-audit` — local schema validator. Catches
  PowerPoint repair-dialog triggers.
- `~/projects/svg2ooxml/tools/ppt_research/powerpoint_capture_cli` —
  driving real PowerPoint slideshow mode on macOS, used here.
- Reference artefact: `~/projects/SplatThis/tmp/anisotropy_refine.pptx`
  + `tmp/anisotropy_refine_pptx.png` (real PowerPoint capture)
  + `tmp/anisotropy_refine_compare.html` (analysis writeup).
