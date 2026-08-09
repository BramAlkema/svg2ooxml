# SplatThis as a Raster-Handoff Tier

Date: 2026-08-09
Status: assessment — viable in principle, gated on shape budget and one open fidelity question.
Reviewed: `~/projects/SplatThis` @ `281d846`.

## The proposition

For SVG constructs we cannot map natively (mesh gradients, non-`normal` blend
modes, filter chains past `max_filter_primitives`), rasterise the region and
hand the bitmap to SplatThis, which fits 2D anisotropic Gaussians and emits
**native DrawingML ellipse shapes — no bitmap**.

## Why it fits our ladder

Our fallback order is `native → mimic → emf → raster`
(`policy/fidelity.py:148`). Tier 4 ends the conversation: a `<a:blip>` is not
editable, not scalable, and not themeable. SplatThis slots **between `emf` and
`raster`** as a tier that is still made of shapes:

| Tier | Representation | Editable | Scalable |
|---|---|---|---|
| `emf` | Vector metafile | No (opaque blob) | Yes |
| **`splat`** | **N ellipses + gradient fills** | **Yes** | **Yes** |
| `raster` | Embedded bitmap | No | No |

That ordering is the point: it converts "we gave up" into "we approximated in
the target's own primitives." For a project scoped to coverage over minimalism,
that is the right trade to have available.

Its `RawSplat` is `(x, y, sx, sy, theta, r, g, b, a, importance, layer)` in
image-space pixels — a straight affine map to our EMU placement, no impedance
mismatch.

## The governing constraint: shape count

The corpus chameleon is **1,778 shapes for one 364×384 image**. That is the
number that decides viability:

- **Never a whole slide.** A deck of full-slide splat fills would be unusable.
- **Only a bounded region** — one mesh-gradient patch, one blend-mode group,
  one filter result that already has a resolved bounding box.
- `--splats` becomes a policy knob sitting alongside `max_segments` and
  `max_filter_primitives`, with the region's area budgeting the cap.

## The fidelity crux

SplatThis's PPTX emitter carries per-style empirical alpha scalars:

| Style | Fill mechanism | Compensation |
|---|---|---|
| gradient | radial `gradFill`, 8 stops | `PPTX_GRADIENT_ALPHA_SCALE = 0.40` |
| soft-edge | `solidFill` + soft edge | `PPTX_SOFT_EDGE_ALPHA_SCALE = 0.25` |
| blur | `solidFill` + isotropic blur | mass-fraction alpha compensation |

**Established fact.** The fitter's `compositing_space` defaults to `"linear"`
(`converter.py:77`) and `converter.py` never varies it by output format — so
the PPTX population is fit in linear light. PowerPoint alpha-composites in
display sRGB (see
[`../../reference/research/drawingml-srgb-emission-contract.md`](../../reference/research/drawingml-srgb-emission-contract.md),
constraint 2). A `compositing_space="srgb"` mode already exists and is
documented as mirroring browser blending; it is simply not wired to
`--format pptx`.

**Inference, not measurement.** That mismatch plausibly explains part of the
`0.40`: sRGB-space compositing yields more apparent contribution per unit alpha
than linear, so a population fit in linear needs scaling *down* when rendered by
PowerPoint. The direction matches. But three different fill mechanisms carry
three different compensations, which is evidence that the **fill mechanism**,
not the fit space, is the dominant term. The source comment at
`pptx_export.py:361` (`path="shape"` matched the roundtrip better than
`"circle"`) suggests the authors already suspected gradient geometry.

**Discriminating test** — cheap, and the harness already exists: fit one corpus
image twice, `compositing_space="linear"` vs `"srgb"`, both with the scalar
forced to `1.0`, and grade each against the target. If the sRGB fit lands
near-correct unaided, the compositing space dominates and the constant should be
retired. If both still need a similar scalar, it is PowerPoint's gradient-fill
alpha rendering and the constant is load-bearing.

This matters for handoff because a global scalar can only be exactly right at
one alpha and one overlap depth. Our regions would have different splat
densities than their corpus photographs, so we would be inheriting a constant
fitted on a different distribution.

## Note that colour interpolation does *not* bite here

Worth recording because it is the intuitive worry: emission-contract constraint
1 (PowerPoint interpolates gradient stops in linear light) does **not** affect
these splats. All 8 stops of a gradient splat share one `color_hex` and vary
only alpha (`pptx_export.py:369-380`), so there is no colour interpolation to
distort. Only the alpha ramp is in play.

## Dependencies and cost

- **Torch.** SplatThis's runtime set is NumPy, Pillow, and Torch. This can only
  ever be an optional extra, never a core dependency.
- **Fit time.** Each region is an optimiser run over multiple densification
  stages, not a transform. Orders of magnitude more expensive than anything in
  our pipeline. This is an offline/batch path — opt-in per conversion, never
  inline by default.

## Independent finding: their acceptance harness needs ICC conversion

Unrelated to the above, but relevant if we trust their published quality
numbers: `powerpoint_osa.py:49` captures via macOS
`screencapture -x -t png -R` with no ICC conversion anywhere in the module.
Those PNGs are display-tagged, so on a wide-gamut display they are not valid
inputs for comparison against an sRGB reference. Their `DEPLOYED` evidence level
is therefore weaker than it claims. This is the same gap our own visual suite
has (see [`../../testing.md`](../../testing.md)) — it does not explain the alpha
constants above, and should not be conflated with them.

## Read

Viable, and architecturally well-matched — a genuine fifth tier rather than a
bolt-on. Gate adoption on the discriminating test above and on a shape-count
policy that confines it to bounded regions. Do not wire it inline.
