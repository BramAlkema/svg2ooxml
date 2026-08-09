# `<a:blur>` Fidelity Results

Date: 2026-05-24
Methodology: see [blur-fidelity-and-scaling.md](./blur-fidelity-and-scaling.md).
Companion to [anisotropic-blur-emulation.md](./anisotropic-blur-emulation.md).

## TL;DR

1. **Kernel shape: true Gaussian.** Edge-response measurement fits a pure
   erf with **RMS ≈ 0.001** across rad = 5 / 15 / 30 / 60 px. A box or
   stacked-box kernel cannot produce that profile.
2. **Calibration: `σ ≈ rad / 3.25`** in the same units. So `<a:blur>`'s
   `rad` attribute is closer to a 3σ "outer radius" than a 1σ sigma. The
   svg2ooxml constant for the converter:
   ```python
   A_BLUR_RAD_PER_SIGMA = 3.25
   emu_rad = round(sigma_px * EMU_PER_PX * A_BLUR_RAD_PER_SIGMA)
   ```
3. **Cost scaling: not measured cleanly.** The capture-rig wall-clock
   is dominated by fixed `--delay`/`--slideshow-delay` waits and app
   launch overhead; numbers below are an *upper bound*, not a render-
   cost curve. See Q3 section for what's needed for a real
   measurement.

## Q1 — Is `<a:blur>` a true Gaussian?

### Method

Each cell renders a half-plane (a white rectangle that occupies the
right half of the cell) with `<a:blur rad="..." grow="1"/>`. The
horizontal scan line through the cell vertical-midpoint is the
*edge response* of the blur kernel.

Convolution math: edge response of a step input through a kernel K is
the CDF of K. Edge response through a Gaussian is exactly `erf`. We fit
the two-erf model

    I(x) = A * 0.5 * (erf((x - x_left) / (σ √2)) − erf((x - x_right) / (σ √2))) + bg

to each cell's profile. If the kernel is Gaussian, residual RMS is at
noise floor; if box / stacked-box, the residual is structured and the
fit fails.

### Results

```
 rad_px (slide)   σ_fit (slide-px)   σ/rad    rms       interpretation
       5               1.68          0.337    0.001     erf fit: clean (rectangle reaches full amplitude)
      15               4.69          0.313    0.000     clean
      30               9.23          0.308    0.001     clean
      60              18.45          0.308    0.001     clean
     120              34.36          0.286    0.048     rectangle too narrow — fit underestimates
     240              52.35          0.218    0.039     rectangle far too narrow — see below
```

For rad ≤ 60 px the rectangle (half-cell wide, ~232 slide-px) is wide
enough that the central plateau saturates at full amplitude, and the
two-erf model fits the edges with **RMS ≈ 0.001**. **The kernel is
Gaussian** — no other simple kernel produces clean erf edge responses
across multiple radii.

For rad ≥ 120 the source rectangle's plateau is squeezed below full
amplitude by the wide blur, the two-erf fit's amplitude parameter
becomes ill-constrained, and the recovered σ underestimates the true
σ. This is a measurement-setup limitation, not a kernel anomaly.

## Q2 — Does `rad` scale linearly with σ?

### In the clean regime (rad ≤ 60 px)

Ratios `σ/rad`: **0.337, 0.313, 0.308, 0.308**.

Weighted regression over the four clean points: **σ_slide = 0.308 ×
rad_slide** (zero-intercept).

Slight rolloff at rad=5 (0.337) is consistent with pixel-discretisation
at small absolute values (1.7 slide-px is only ~3.6 capture-px wide).

### Calibration constant for the svg2ooxml exporter

```
σ_blur = rad / 3.25      (same units)
rad   = 3.25 × σ_blur
```

In EMU: a request for `<feGaussianBlur stdDeviation="σ_px"/>` should
emit `<a:blur rad="round(σ_px * EMU_PER_PX * 3.25)" grow="1"/>`.

### Caveat

This is one calibration measurement on **macOS desktop PowerPoint**.
Cross-platform parity is not yet confirmed. Recommended: gate the
constant behind a tested-platforms list and ship as default-on only
after Windows + Web PowerPoint verification.

## Q3 — Cost scaling (NOT cleanly measured)

Attempted with wall-clock of the capture rig (`tools/ppt_research/
powerpoint_capture_cli` in slideshow mode), single-slide PPTX, N
identical 14 px blurred ellipses on a packed grid, rad=114300 EMU:

```
N         capture-rig wall-clock
 100        12.6 s
2 000       15.1 s
10 000      28.9 s
```

**These numbers are an upper bound, not a render-cost curve.** Reasons:

- The capture rig has `--delay 3` + `--slideshow-delay 6` = 9 s of
  fixed waits per run, plus PowerPoint app launch and slideshow-mode
  startup (which themselves are dependent on file size).
- The capture happens at `slideshow-delay = 6 s` after slideshow
  start. If PowerPoint is still rendering at that moment (likely at
  10k shapes), the captured PNG is of a not-fully-rendered frame, not
  the final state. So the timing doesn't even correspond to a
  consistent semantic ("frame fully drawn").
- We have no probe for when PowerPoint is "done compositing." There's
  no signal in slideshow mode that exposes render completion.

So all we can say from this attempt is: **PowerPoint will accept and
slideshow 10 000 blurred shapes without crashing or refusing to
render** on M-series macOS, and the captured frame at +6 s after
slideshow start contains visibly rendered content even at the
high-shape-count end.

The per-shape "ms/shape" figure I initially derived from these wall-
clocks is meaningless — it's mostly the difference in app/slideshow
launch cost driven by file size, not blur-compositing cost.

### What a real Q3 measurement needs

- A render-completion signal. Options:
  - AppleScript probe of slideshow state (untested whether it exposes
    a "render done" event).
  - Pixel-stability detection: capture twice with a short interval and
    declare "rendered" when the frame stops changing.
  - PowerPoint export-to-PDF or export-to-image path, which is
    synchronous and returns when fully rendered. May use a different
    code path than slideshow display though.
- Decouple shape-count from blur-radius — sweep each independently
  while pinning the other, so we can characterize O(N·f(rad)) where
  f is the per-shape blur cost.
- Multiple runs per data point to wash out noise. The first run pays
  cold-cache costs (font loading, theme initialization, etc.).

Until that's built, the only empirically grounded claim about Q3 is
the existence proof above: 10 000 blurred shapes renders in real
PowerPoint.

## Cross-platform — out of scope this round

Not measured:
- **Windows desktop PowerPoint** — no macOS-driven capture rig.
- **Web PowerPoint** — would need a scriptable browser session against
  Office 365.
- **Google Slides import** — would need a Slides upload + render path.
- **LibreOffice / soffice** — known to misrender blur stacks. See
  `feedback-no-soffice-for-pptx-validation` memory note. Cross-platform
  baseline is desktop PowerPoint.

**Recommendation for svg2ooxml maintainers:** ship the calibration as a
feature-flagged opt-in keyed on Mac-Office output, and add Windows
verification before flipping it default-on. The 3.25 constant is likely
within 10% on all platforms because the underlying graphics
implementations rarely diverge in the kernel-shape math; the
uncertainty is whether the `rad` attribute itself is interpreted
identically.

## Artifacts

All artifacts under `~/projects/SplatThis/tmp/`:

| File | Purpose |
|---|---|
| `blur_edge_response_pptx.py` | Test PPTX generator (half-plane edges) |
| `blur_edge_response.pptx` | Test PPTX |
| `blur_edge_response_pptx.png` | Real-PowerPoint slideshow capture |
| `blur_edge_response_analyze.py` | Erf-fitting analyzer |
| `blur_edge_response_fits.png` | Per-cell profiles + fits |
| `blur_edge_response_fits.json` | Raw fit data |
| `blur_scaling_pptx.py` | Q3 generator (`python blur_scaling_pptx.py N`) |
| `blur_scaling_n{100,2000,10000}.pptx` | Q3 scaling test inputs |
| `blur_scaling_n{100,2000,10000}.png` | Q3 captures |

## Recommended next experiments

1. **A clean Q3 rig.** Add render-completion detection to
   `powerpoint_capture_cli` — easiest first cut is pixel-stability
   polling (capture every N ms, declare done when consecutive frames
   match within ε). Until that exists, any wall-clock-based timing is
   dominated by fixed waits and tells us nothing about the kernel.

2. **rad-vs-cost** (once #1 lands): fix N=2000 shapes, sweep rad from
   0 to 600k EMU. Tells us whether per-shape cost goes up linearly
   (separable Gaussian implementation) or super-linearly (e.g. O(rad²)
   naive blur). Splat exporters would benefit from knowing where the
   "big-blur-is-cheap" regime ends.

3. **Cross-platform σ-vs-rad** (Windows desktop / Web PowerPoint /
   Google Slides import). The 3.25 constant in Q2 is empirically solid
   for macOS desktop but may differ elsewhere. Each platform needs its
   own erf-fit sweep with the existing `blur_edge_response.pptx`
   asset.
