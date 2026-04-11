# PowerPoint Fidelity Phase 2 Specification

- **Status:** Draft
- **Date:** 2026-04-09
- **Scope:** authoring-accurate PowerPoint animation, filter/lighting fidelity, and browser-vs-slideshow validation
- **Related docs:**
  - [Animation Fidelity Specification](./animation-fidelity.md)
  - [Animation SMIL Parity Specification](./animation-smil-parity-spec.md)
  - [Visual Fidelity Gaps Specification](./visual-fidelity-gaps.md)
  - [Animation W3C Suite Execution Specification](./animation-w3c-suite-execution-spec.md)

## 1. Purpose

This spec defines the next major phase of `svg2ooxml`: move from "valid PPTX that PowerPoint can open" to "PowerPoint output that behaves and looks like the SVG on purpose."

We now have three enabling capabilities:

1. formal corpus/build validation is green on the current W3C profiles
2. PowerPoint slideshow capture works end to end on macOS
3. browser-vs-PowerPoint visual comparison can rank failures automatically

That changes the problem. The bottleneck is no longer package validity. It is fidelity.

## 2. Current Baseline

### 2.1 Formal build/open baseline

The current W3C corpus gate is already green:

- `tests/corpus/w3c/report_gradients.json`: `24/24` decks valid
- `tests/corpus/w3c/report_shapes.json`: `22/22` decks valid
- `tests/corpus/w3c/report_animation.json`: `20/20` decks valid
- `tests/corpus/w3c/report_animation_full.json`: `40/40` decks valid

This means the converter is no longer blocked on basic package validity for the tracked W3C slices.

### 2.2 Visual baseline

The visual baseline is still poor:

- static W3C parity remains weak, especially around filters and text
- animation W3C decks now render in PowerPoint, but many are still visually wrong or semantically inert relative to the SVG source
- the current worst offenders are concentrated in:
  - lighting/specular/diffuse filter cases
  - gaussian blur/filter composition cases
  - `text/tspan` layout cases
  - color, begin-trigger, and multi-effect animation cases

### 2.3 Design consequence

Open XML validity and PowerPoint acceptance are necessary, but no longer sufficient.

Phase 2 therefore treats:

- browser rendering as the source-of-truth visual reference
- PowerPoint slideshow output as the Office runtime truth
- build validity as a floor, not the finish line

## 3. Research Findings

### 3.1 SVG animation semantics are SMIL-driven

SVG 1.1 animation is a host-language integration of SMIL animation. That means `begin`, `dur`, `repeatCount`, `repeatDur`, `fill`, `additive`, `accumulate`, `set`, `animate`, `animateMotion`, and `animateTransform` are not optional presentation hints; they are the semantics we are trying to preserve.

Implication:

- parser and IR work must stay faithful to SMIL semantics
- but PowerPoint output cannot stop at schema-valid `<p:timing>` if the authored behavior still does not play

### 3.2 PresentationML animation is SMIL-shaped but PowerPoint-authored behavior matters

Microsoft's PresentationML animation model is explicitly described as loosely based on SMIL. The generic `<p:anim>` model is valid and useful, and the allowed `tav` attribute set includes `ppt_x`, `ppt_y`, `ppt_w`, `ppt_h`, `ScaleX`, `ScaleY`, `style.opacity`, and `style.visibility`.

However, our recent debugging showed a practical distinction:

- schema-valid generic `<p:anim>` is not always enough to make PowerPoint actually play the effect
- PowerPoint-authored structures such as proper build groups, `mainSeq` wiring, effect families, and runtime context can be the difference between "visible in the pane" and "actually runs"

Implication:

- Phase 2 must prefer PowerPoint-authored effect structures over merely legal PresentationML where behavior diverges

### 3.3 PowerPoint has authored effect families that map better than raw property tweens

PowerPoint exposes named authored effect families such as `Grow/Shrink` and `Transparency`, plus timing controls like `AutoReverse`, `RepeatCount`, `RepeatDuration`, and show types such as `Window` and `Kiosk`.

Implication:

- symmetric pulse effects should prefer authored scale/effect families over ad hoc width/height property tweens
- opacity pulses should prefer authored transparency semantics over entrance-fade misuse
- slideshow validation must use actual slideshow output, not edit-canvas screenshots

### 3.4 SVG filter lighting depends on source-surface correctness

The SVG filter model distinguishes:

- `SourceGraphic`: the original RGBA source
- `SourceAlpha`: the same source alpha with black RGB
- `feDiffuseLighting`: opaque light map from the alpha bump map, intended to be multiplied with a texture
- `feSpecularLighting`: non-opaque highlight map intended to be added to the textured image

Implication:

- lighting fidelity is primarily a source-surface correctness problem
- if the source surface loses alpha, luminance, or composition boundaries, the lighting pass is already wrong before any PowerPoint export decision is made

### 3.5 W3C is still useful, but must be interpreted correctly

The old W3C SVG test suite is explicitly described as testing the specification rather than certifying browser conformance, and the W3C notes that testing is moving toward `web-platform-tests`.

Implication:

- W3C remains a strong spec-facing regression corpus for `svg2ooxml`
- but Phase 2 should treat W3C and WPT as complementary:
  - W3C for legacy SVG 1.1 coverage and known fixture names
  - WPT for modern spec-facing additions and browser-grounded behavior

## 4. Goals

1. Make supported SVG animation produce PowerPoint-authored behavior that actually plays in slideshow mode.
2. Improve filter and lighting fidelity without breaking current package validity guarantees.
3. Use browser-vs-PowerPoint slideshow comparison as the primary release signal for fidelity work.
4. Keep degradations explicit, local, and observable in telemetry.
5. Reduce unnecessary raster fallback while preserving correctness.

## 5. Non-Goals

- Full DOM/script/event parity for SVG.
- General browser runtime emulation inside PowerPoint.
- Perfect support for every filter primitive or animation graph in one phase.
- Replacing browser rendering as the reference model.
- Windows-specific automation as a prerequisite for Phase 2.

## 6. Core Principles

### P1: Prefer authored behavior over minimal legality

If a generic PresentationML structure is legal but does not behave like a PowerPoint-authored deck, Phase 2 should prefer the authored shape.

### P2: Validate what users actually see

PowerPoint edit view is not the acceptance surface. Slideshow output is.

### P3: Preserve source-surface semantics first

For filter work, correctness of `SourceGraphic`, `SourceAlpha`, luminance, alpha coverage, and filter input routing comes before any export optimization.

### P4: Degrade locally, not globally

Unsupported fragments should be skipped or rasterized as locally as possible. A single unsupported fragment should not suppress an otherwise-valid timing tree or whole slide unless strictly necessary.

### P5: Keep fidelity decisions measurable

Every non-native or non-spec-preserving decision must be attributable in code, telemetry, and review output.

## 7. Workstreams

### 7.1 Animation Authoring Parity

#### A1. Trigger and autoplay semantics

Required outcomes:

- `mainSeq`, click-group, and build-list structure must match PowerPoint-authored expectations closely enough to autoplay reliably
- `begin`, `with previous`, `after previous`, shape-targeted begin references, and delay offsets must remain explicit in IR and in emitted timing
- slideshow runtime behavior must be verified by captured playback, not pane visibility alone

#### A2. Effect-family mapping

Phase 2 standardizes the preferred authored representation per SVG behavior:

| SVG behavior | Preferred PowerPoint representation | Avoid by default |
|---|---|---|
| symmetric width/height pulse | authored scale effect (`animScale` / Grow-Shrink style) with `AutoReverse` and repeat control | raw `ppt_w`/`ppt_h` tweens when authored scale semantics are available |
| opacity pulse on visible shape | transparency-style emphasis behavior | entrance fade used as a generic opacity animation |
| stepwise visibility or discrete state change | `set` / discrete effect groups | linear interpolation |
| path motion | authored motion/path behavior where possible | flattening to independent x/y tweens when path semantics matter |
| color change | authored color/change effect groups or segmented steps | first/last-only collapse of multi-keyframe color |

#### A3. Coordination and grouping

Required outcomes:

- per-shape effect groups must appear correctly in the Animation Pane
- build-list entries and `grpId` wiring must stay consistent
- stacked effects on one target must remain distinct and executable
- multi-effect animations must not collapse to inert timing trees

#### A4. Animation telemetry

Phase 2 must keep deterministic reason codes for:

- unsupported begin targets
- skipped motion fragments
- rotate-auto downgrade
- calc-mode downgrade
- additive/accumulate downgrade
- property-to-effect remapping
- raster fallback caused by unsupported animation behavior

### 7.2 Filter and Lighting Fidelity

#### F1. Source-surface contract

`drawingml/raster_adapter.py` and related filter adapters must preserve:

- actual fill/stroke color when needed for luminance-sensitive filters
- actual alpha coverage for `SourceAlpha`
- no invented fill when the original source is not filled
- no silent replacement of source geometry with generic placeholder tiles

#### F2. Lighting semantics

Required outcomes:

- `feDiffuseLighting` must behave as an opaque light map derived from the input bump map
- `feSpecularLighting` must behave as a non-opaque highlight map intended for additive composition
- masking to the source alpha/shape boundary must happen correctly
- filter inputs must remain tied to the actual shape geometry, not a synthetic square source surface

#### F3. Approximation policy contract

Phase 2 must keep one stable policy contract:

- existing generic `approximation_allowed` remains valid
- primitive-specific overrides may refine behavior
- policy keys must not silently disable previously-supported approximation paths

#### F4. Native vs raster decision matrix

Required rule:

- choose native DrawingML only when it preserves the effect family with acceptable error
- choose local raster fallback when native output would be visibly wrong
- avoid whole-slide or whole-group raster fallback unless the semantics force it

### 7.3 Validation and Measurement

#### V1. Required gates

Every major fidelity PR in Phase 2 must keep:

- formal W3C build/open gate green
- slideshow startup and capture path green for the targeted visual profile
- before/after visual evidence on the changed corpus slice

#### V2. Required measurement axes

At minimum, the review artifact set must track:

- PPTX build success
- slideshow-entry success
- PowerPoint render success
- browser render success
- browser-vs-PowerPoint SSIM
- max pixel diff percentage
- fallback counts by type
- animation fragments emitted vs skipped
- reason-code counts for degradations

#### V3. Corpus tiers

Phase 2 uses four tiers:

1. `tests/corpus/w3c` formal build/open gates
2. curated W3C static slideshow/browser diff set
3. W3C animation slideshow/browser diff set
4. focused real-world stress cases such as Gallardo, text-path, and filter-heavy SVGs

#### V4. Reference hierarchy

When a result is ambiguous, use this order:

1. browser rendering of the original SVG
2. PowerPoint slideshow capture
3. authored PowerPoint control decks for structure comparison
4. package validity and XML inspection

## 8. Implementation Plan

### Milestone 1: Authoring-accurate animation baseline

Deliverables:

- stabilize authored trigger/main-sequence/build-list semantics
- standardize preferred effect-family mapping for scale, opacity, motion, color, and discrete changes
- keep Animation Pane visibility and slideshow execution aligned

Required demo/control cases:

- `animate-opacity.svg`
- `animate-path.svg`
- `animate-spin`
- `animate-orbit`

Exit criteria:

- all four control decks visibly animate in PowerPoint slideshow capture
- no inert/no-op timing trees on those controls
- no slideshow-entry failures on the animation control set

### Milestone 2: Lighting and filter correctness

Deliverables:

- correct source-surface generation for lighting-sensitive filters
- correct masking/compositing for diffuse/specular output
- stable approximation policy behavior

Priority fixtures:

- `filters-light-01-f`
- `filters-light-02-f`
- `filters-specular-01-f`
- `filters-diffuse-01-f`
- `filters-gauss-01-b`

Exit criteria:

- all priority fixtures reach slideshow capture successfully
- no synthetic square/tile source-surface artifacts remain
- each priority fixture shows a material browser-vs-PowerPoint improvement from the 2026-04-08 baseline, or the remaining gap is explicitly documented

### Milestone 3: Ranked-failure closure

Deliverables:

- use the automated ranking loop to close the top visual offenders in descending order
- keep build/open baselines green while reducing visual mismatch

Exit criteria:

- no new slideshow-entry failures in the tracked W3C visual profiles
- top-ranked offender list shrinks release-over-release
- skipped animation fragment counts decline materially on the W3C animation suite

## 9. Files and Systems Likely To Change

- `src/svg2ooxml/core/animation/`
- `src/svg2ooxml/drawingml/animation/`
- `src/svg2ooxml/filters/primitives/`
- `src/svg2ooxml/drawingml/raster_adapter.py`
- `src/svg2ooxml/services/filter_service.py`
- `src/svg2ooxml/policy/providers/filter.py`
- `tools/visual/powerpoint_capture.py`
- `tools/visual/browser_renderer.py`
- `tools/visual/corpus_audit.py`
- `tools/visual/w3c_animation_suite.py`

## 10. Review Checklist

Before approving Phase 2 work, reviewers should ask:

1. Did this change improve slideshow output, or only XML legality?
2. Does the result match browser output more closely on the targeted fixtures?
3. Was the fallback decision local and justified?
4. Are reason codes and measurements present for any downgrade?
5. Did W3C build/open gates remain green?
6. Did slideshow capture remain stable on the touched validation profile?

## 11. References

Official references used for this spec:

- W3C SVG 1.1 Animation: https://www.w3.org/TR/2003/REC-SVG11-20030114/animate.html
- W3C SVG 1.1 Filter Effects: https://www.w3.org/TR/2010/WD-SVG11-20100622/filters.html
- W3C SVG Test Suite Overview: https://www.w3.org/Graphics/SVG/WG/wiki/Test_Suite_Overview
- web-platform-tests project: https://github.com/web-platform-tests/wpt
- Microsoft Learn, Working with animation: https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-animation
- Microsoft Learn, `tav` allowed attribute names: https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/981b17ff-5594-42cf-ad8d-7cb39e653afa
- Microsoft Learn, `CommonBehavior.RuntimeContext`: https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.commonbehavior.runtimecontext?view=openxml-3.0.1
- Microsoft Learn, `MsoAnimEffect`: https://learn.microsoft.com/en-us/office/vba/api/powerpoint.msoanimeffect
- Microsoft Learn, `Timing.AutoReverse`: https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing.autoreverse
- Microsoft Learn, `Timing.RepeatCount`: https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing.repeatcount
- Microsoft Learn, `SlideShowSettings.Run`: https://learn.microsoft.com/zh-cn/office/vba/api/powerpoint.slideshowsettings.run
- Microsoft Learn, `SlideShowSettings.ShowType`: https://learn.microsoft.com/en-us/office/vba/api/powerpoint.slideshowsettings.showtype
- Microsoft Learn, `PpSlideShowType`: https://learn.microsoft.com/en-us/office/vba/api/powerpoint.ppslideshowtype
