# DrawingML sRGB Emission Contract

Date: 2026-08-09
Status: contract — one rule is enforced by test, two are consumer constraints.

## The rule we enforce

`<a:srgbClr val="RRGGBB">` carries **display-sRGB bytes, verbatim**. Whatever
byte triple the author wrote in the SVG is the byte triple that lands in the
slide part. No gamma transform, in either direction, on the way out.

This holds for every emission site: solid fills, line colours, gradient stops,
effect colours. Alpha rides the same contract — `stop-opacity` is *scaled* to
PPT units (`opacity_to_ppt`, ×100000), never curved.

Enforced end-to-end by
`tests/integration/test_pptx_exporter.py::test_srgb_clr_carries_display_srgb_bytes_verbatim`,
which converts an SVG through the full package pipeline, unzips
`ppt/slides/slide1.xml`, and asserts byte equality on gradient stops, a solid
fill, and a stroke. It uses mid-tone probes (`#808080`, `#336699`, `#CC3300`)
because `#000000` and `#FFFFFF` are fixpoints of both transfer functions and
would let a stray transform through unnoticed. It also asserts that no
gamma-shifted variant of any probe appears anywhere in the part.

The one place linearisation is correct is the raster filter pipeline
(`render/filters_region.py`, `render/filters_executor.py`), which implements
SVG's `color-interpolation-filters="linearRGB"` semantics. That is filter
math on pixel buffers, not vector colour emission, and is out of scope here.
OKLab conversions in `color/` likewise run only when *parsing* `oklab()` /
`oklch()` authored colours **into** display sRGB.

## Consumer constraint 1 — PowerPoint interpolates gradients in linear light

PowerPoint interpolates between `<a:gs>` stops in linear light. SVG specifies
gradient interpolation in gamma-encoded sRGB (absent
`color-interpolation="linearRGB"`). So for the same two endpoints, PowerPoint's
gradient **midpoint is lighter** than the SVG reference renderer's.

**This is not ours to compensate for.** The tempting fix — pre-linearising stop
colours so the midpoint lands where SVG would put it — trades a correct
midpoint for two wrong endpoints, and the endpoints are the only colours the
author actually specified. A designer who picks `#808080` and sees `#373737` in
the PPTX has been handed a bug; a designer whose gradient midpoint sits a few
percent light has been handed a renderer difference. The regression test above
exists specifically to make the "fix" fail loudly.

Consequence for validation: a mid-gradient pixel diff against an SVG reference
render is **expected** and is not a conversion defect. Compare gradient
*endpoints* for correctness. If a suite needs mid-gradient tolerance, widen the
tolerance for gradient regions rather than changing what we emit.

## Consumer constraint 2 — PowerPoint alpha-composites in display sRGB

Alpha compositing happens in display sRGB, not linear light — the opposite of
the gradient rule above. A 50%-alpha shape over a background yields the
gamma-space average of the two colours, matching SVG's default compositing.

Consequence for validation: semi-transparent overlays should match an SVG
reference closely. A *systematic* discrepancy on alpha-composited regions
points at a real defect, unlike the gradient case. The two rules pull in
opposite directions, so do not generalise a finding from one to the other.

## Consumer constraint 3 — macOS captures need ICC conversion before comparison

Screenshots taken on macOS are tagged with the **display's** colour profile,
not sRGB. On a P3 display, a `#336699` shape screenshots to bytes that are not
`336699`. Comparing such a capture against an sRGB reference render produces
colour deltas across the entire frame that have nothing to do with the
conversion.

Any capture entering a pixel comparison must be ICC-converted to sRGB first.
Untagged or display-tagged captures are not valid comparison inputs. The visual
suite does not perform this conversion today — see
[`../../testing.md`](../../testing.md) for the current state.

## Why this is split this way

The conversion formula was never in question; the acceptance framing was.
Rule 1 is a property of our output, so it belongs in a test that fails when
someone changes it. Rules 2 and 3 are properties of the consumer and of the
capture path — nothing we emit can satisfy or violate them — so they belong in
the heads of whoever reads a red pixel diff.
