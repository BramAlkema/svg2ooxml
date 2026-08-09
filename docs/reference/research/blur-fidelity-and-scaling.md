# `<a:blur>` Fidelity & Scaling — Open Questions

Date: 2026-05-24
Status: open — methodology proposed, captures not yet run.
Related: [anisotropic-blur-emulation.md](./anisotropic-blur-emulation.md),
[drawingml-unused-opportunities.md](./drawingml-unused-opportunities.md).

## The questions

We are leaning more heavily on `<a:blur>` as the primary mimicry path
for true-Gaussian content (2D Gaussian splats, drop shadows, anisotropic
blur emulation). The visual evidence so far says it looks Gaussian. We
have not actually characterized it. Three open questions:

1. **Is PowerPoint's `<a:blur>` a true Gaussian?** Or a box-filter / stacked
   box approximation? (Many renderers cheat for speed.) If it's a box, the
   tails are wrong and the optimizer's trained sigmas won't reproduce.
2. **Does `rad` scale linearly?** PowerPoint's documentation says `rad` is
   "the radius of the blur in EMUs." We have no empirical confirmation that
   doubling `rad` doubles the effective standard deviation in pixel space.
3. **How does cost scale?** With shape count and with `rad`. We have shipped
   20k-splat PPTXes with isotropic blur, so it works, but we have no curve:
   does a `rad=100k` blur cost the same as a `rad=10k` blur on the same
   shape? Does N+1 blurred shapes cost N times one shape's render?

## Why it matters

- **Anisotropic-emulation accuracy.** Recipe N (ellipse + sigmoid stops +
  blur) only works if the blur is sufficiently Gaussian-shaped at the
  emulated minor-axis sigma. If `<a:blur>` is actually box-shaped, our
  trained model's sigmas need a corrective LUT before emission.
- **Performance budgets.** If render cost grows superlinearly with `rad`,
  large background splats become a real cost driver and we want to clamp.
- **Cross-platform behavior.** Desktop PowerPoint (macOS, Windows), Web
  PowerPoint, and Keynote import may not agree on the blur math. The
  splat-rendering work and svg2ooxml's filter exporter both depend on this.

## Proposed methodology

### Q1 — Blur shape (Gaussian vs box vs stacked box)

1. Single white-circle splat on black background, fixed shape size
   (e.g. 500 × 500 EMU per side), one slide per `rad` value:
   `rad ∈ {5_000, 20_000, 50_000, 100_000, 200_000}` EMU.
2. Capture in real PowerPoint (slideshow mode) via
   `tools/ppt_research/powerpoint_capture_cli`.
3. Crop to a fixed window around the splat, extract horizontal intensity
   profile through center.
4. Fit Gaussian (3 params) and box (2 params) and stacked-box (3 params,
   3-pass) models to each profile. Compare residual RMS.
5. Decision: smallest-residual model wins; if Gaussian wins by a clear
   margin across all `rad` values, we can trust `<a:blur>` as Gaussian
   for splat use.

### Q2 — Linearity of `rad`

Falls out of Q1: each fitted profile gives an effective σ in pixels.
Plot σ vs `rad` (EMU). If linear, slope = px/EMU mapping; if not, log
the deviation. Repeat with a second shape size to check size dependence.

### Q3 — Cost scaling

Two grids, captured with `tools/ppt_research/`'s timing-aware mode (or
add a wallclock-around-`capture` wrapper):

- **Shape-count grid**: N white circles uniformly placed, all with the
  same `rad`. `N ∈ {1, 10, 100, 1_000, 5_000, 10_000}`.
- **Radius grid**: 100 shapes, sweep `rad ∈ {1k, 10k, 100k, 1_000k}`.

Measure "slide-open to first painted frame" and "slideshow advance to
next slide" times.

### Cross-platform

Repeat Q1 (the most important test) on:

- macOS desktop PowerPoint (current capture rig).
- Windows desktop PowerPoint (no capture rig yet — needs setup).
- Web PowerPoint (via headless browser if scriptable; otherwise manual).
- LibreOffice / soffice (for completeness, knowing it has rendering bugs
  per [feedback-no-soffice-for-pptx-validation] — but worth knowing the
  delta so svg2ooxml can warn its users).

## What we already know (empirical, not characterized)

- `<a:blur>` works at 20k shapes in real desktop PowerPoint without
  visible artifacts (per SplatThis 20k chameleon test).
- Visual shape is "Gaussian-like" at typical splat sigmas (per kitchen
  sink test in the SplatThis catalog).
- `grow="1"` is required for blur to not get clipped by the shape's
  bounding box.
- LibreOffice misrenders blur + gradient stacks dramatically. Real
  PowerPoint is the ground truth.

## Implementation gap in svg2ooxml

`src/svg2ooxml/filters/primitives/gaussian_blur.py` converts SVG
`stdDeviation` → DrawingML `rad`. The conversion currently assumes the
two represent the same Gaussian σ in their respective units, scaled by
EMU/px. If Q1 says PowerPoint's blur is non-Gaussian or Q2 says `rad`
is non-linear, this converter needs a calibration LUT.

## Out of scope

- Tinted blur (`a:blur` doesn't take a color — it inherits from the
  shape).
- Anisotropic blur via stacking — already characterized in
  [anisotropic-blur-emulation.md](./anisotropic-blur-emulation.md);
  every stacking strategy failed.

## Deliverable

A short follow-up note `blur-fidelity-results.md` with:
- Best-fit model per `rad` value.
- σ-vs-`rad` linearity plot or table.
- Render-time vs `rad` and shape-count curves.
- Recommended `rad` clamp for SplatThis-scale exports.
- Calibration constant (px/EMU at the measured σ) for the svg2ooxml
  filter exporter.
