# PowerPoint Fidelity Phase 2 - Implementation Tasks

**Spec**: `docs/specs/powerpoint-fidelity-phase-2.md`

## Objective

Turn the Phase 2 fidelity spec into an execution plan that improves:

1. PowerPoint-authored animation behavior
2. filter and lighting correctness
3. browser-vs-slideshow feedback quality

while keeping the existing W3C build/open gates green.

## Workstream Overview

### WS1: Animation Authoring Parity

Goal:
- emit PowerPoint-authored animation structures that both appear correctly in the Animation Pane and actually play in slideshow mode

### WS2: Filter and Lighting Fidelity

Goal:
- improve filter correctness with a focus on source-surface handling, lighting semantics, and safe approximation policy

### WS3: Validation and Ranking

Goal:
- keep slideshow/browser comparison authoritative and make the next failures obvious, ranked, and attributable

## Phase 1: Lock The Animation Runtime Baseline

### Task 1.1 - Stabilize Main Sequence and Build Wiring
- [ ] Audit `mainSeq`, click-group, and build-list output in `src/svg2ooxml/drawingml/animation/xml_builders.py`
- [ ] Normalize `grpId` / `bldP` behavior across all animation families
- [ ] Add or extend tests in:
  - `tests/unit/drawingml/animation/test_xml_builders.py`
  - `tests/unit/core/test_pptx_exporter_animation.py`
  - `tests/golden/animation/test_golden_master.py`

### Task 1.2 - Standardize Effect-Family Mapping
- [ ] Document and enforce preferred mappings in the handlers:
  - width/height pulse -> scale effect family
  - opacity pulse -> transparency-style emphasis
  - discrete state changes -> `set` / discrete effects
  - motion -> authored motion behavior where available
  - color changes -> segmented effect groups instead of first/last collapse
- [ ] Update:
  - `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
  - `src/svg2ooxml/drawingml/animation/handlers/opacity.py`
  - `src/svg2ooxml/drawingml/animation/handlers/motion.py`
  - `src/svg2ooxml/drawingml/animation/handlers/color.py`
  - `src/svg2ooxml/drawingml/animation/handlers/set.py`

### Task 1.3 - Keep Slideshow Semantics First-Class
- [ ] Keep slideshow capture stable in:
  - `tools/visual/powerpoint_capture.py`
  - `tools/visual/pptx_window.py`
- [ ] Add explicit regression coverage for:
  - deck open by staged path
  - slideshow startup
  - slideshow teardown
  - pane-visible but inert timing regressions

### Task 1.4 - Build A Small Control Corpus
- [ ] Maintain a minimal manual-control set under `tests/corpus` or `tests/visual/fixtures` for:
  - opacity pulse
  - path motion
  - orbit motion
  - spin/transform pulse
- [ ] Require that each control fixture:
  - shows expected effects in the Animation Pane
  - plays in slideshow mode
  - produces capturable slideshow frames

### Task 1.5 - Preserve SMIL Semantics In IR
- [ ] Revisit begin, repeat, fill, calcMode, additive, and accumulate mapping against Phase 2 behavior goals
- [ ] Keep localized degradation rather than whole-tree suppression
- [ ] Extend warnings/reason codes in:
  - `src/svg2ooxml/core/animation/parser.py`
  - `src/svg2ooxml/drawingml/animation/policy.py`
  - `src/svg2ooxml/drawingml/animation/writer.py`

## Phase 2: Close The Worst Animation Gaps

### Task 2.1 - Begin/Trigger Fidelity
- [ ] Improve emitted start conditions for:
  - absolute delays
  - `with previous`
  - `after previous`
  - target begin/end references
- [ ] Reduce `unsupported_begin_target_missing` occurrences in W3C animation runs

### Task 2.2 - Color Animation Fidelity
- [ ] Keep segmented multi-keyframe color behavior
- [ ] Add fidelity checks for:
  - `color-prop-01-b`
  - `color-prop-02-f`
  - `color-prop-03-t`
  - `color-prop-04-t`
  - `color-prop-05-t`

### Task 2.3 - Motion/Transform Fidelity
- [ ] Improve path-following and transform playback for:
  - `animate-path.svg`
  - `animate-orbit`
  - W3C `coords-transformattr-*`
- [ ] Keep authored grouping visible in the Animation Pane

### Task 2.4 - Animation Telemetry And Ranking
- [ ] Emit stable reason-code counts into the audit/report output
- [ ] Rank animation failures by:
  - slideshow success/failure
  - animation frame count
  - average/min SSIM
  - pixel diff
  - skipped fragment reasons

## Phase 3: Lock The Filter/Lighting Source-Surface Contract

### Task 3.1 - Preserve Real Source Inputs
- [ ] Keep `SourceGraphic` and `SourceAlpha` semantics explicit in:
  - `src/svg2ooxml/drawingml/raster_adapter.py`
  - `src/svg2ooxml/render/filters_lighting.py`
  - `src/svg2ooxml/filters/primitives/lighting.py`
- [ ] Avoid black-only or synthetic placeholder source surfaces unless the primitive explicitly requires them

### Task 3.2 - Keep Approximation Policy Stable
- [ ] Treat generic `approximation_allowed` as the baseline contract
- [ ] Allow primitive-specific overrides without silently disabling existing approximation paths
- [ ] Add focused policy regression tests in:
  - `tests/unit/services/test_filter_service.py`
  - `tests/integration/test_filter_emf_regression.py`

### Task 3.3 - Fix Lighting Composition Semantics
- [ ] Ensure:
  - diffuse lighting behaves as an opaque light map
  - specular lighting behaves as a non-opaque highlight map
  - source-alpha masking stays tied to actual geometry
- [ ] Revalidate:
  - `filters-light-01-f`
  - `filters-light-02-f`
  - `filters-specular-01-f`
  - `filters-diffuse-01-f`

### Task 3.4 - Keep Raster Fallback Local
- [ ] When native DrawingML is visually wrong, rasterize the smallest correct unit
- [ ] Avoid whole-slide or whole-group raster fallback where a local primitive or local subtree fallback is sufficient

## Phase 4: Use Ranked W3C Output To Drive Closure

### Task 4.1 - Static W3C Fidelity Queue
- [ ] Keep a ranked queue of static W3C offenders, starting with:
  - `filters-light-01-f`
  - `filters-specular-01-f`
  - `filters-diffuse-01-f`
  - `filters-gauss-01-b`
  - `text-tspan-01-b`
- [ ] Record before/after evidence for each fix

### Task 4.2 - Animation W3C Fidelity Queue
- [ ] Keep a ranked queue of animation W3C offenders, starting with:
  - `color-prop-04-t`
  - `animate-elem-31-t`
  - `animate-elem-35-t`
  - `animate-elem-34-t`
- [ ] Re-run slideshow/browser comparison after each fix cluster

### Task 4.3 - WPT Pilot
- [ ] Add a small pilot slice from WPT for SVG animation/filter cases not covered well by the legacy W3C fixtures
- [ ] Keep this slice separate from the existing W3C gate until stability is proven

## Phase 5: Reporting, Gating, And Release Rules

### Task 5.1 - Keep Formal Gates Green
- [ ] Continue running:
  - `tests/corpus/w3c/report_gradients.json`
  - `tests/corpus/w3c/report_shapes.json`
  - `tests/corpus/w3c/report_animation.json`
  - `tests/corpus/w3c/report_animation_full.json`
- [ ] Do not accept fidelity fixes that regress build/open validity on the tracked W3C profiles

### Task 5.2 - Promote Visual Outputs To First-Class Review Artifacts
- [ ] Standardize report output for:
  - slideshow render status
  - browser render status
  - SSIM
  - pixel diff
  - fallback counts
  - skipped animation fragment counts
  - reason-code summaries

### Task 5.3 - Release Readiness Rules
- [ ] Treat Phase 2 work as release-ready only when:
  - targeted fixtures have improved visually
  - slideshow capture is stable on the targeted profile
  - no new package/repair regressions are introduced

## Validation Checklist

### Required per animation-heavy PR
- [ ] `pytest tests/golden/animation/test_golden_master.py`
- [ ] targeted `tests/unit/drawingml/animation/...`
- [ ] targeted `tests/unit/core/test_pptx_exporter_animation.py`
- [ ] at least one slideshow control-deck verification
- [ ] targeted W3C animation rerun with before/after comparison

### Required per filter/lighting PR
- [ ] targeted unit/integration filter suite
- [ ] Docker render-lane skia/NumPy run for skia-gated cases
- [ ] slideshow/browser rerun on the affected W3C filter slice
- [ ] no new repair/open regressions

### Required per milestone
- [ ] updated ranked offender list
- [ ] archived reports/artifacts
- [ ] short written note on what improved and what remains broken

## Recommended Execution Order

1. Phase 1 - lock the animation runtime baseline
2. Phase 2 - close the worst animation fidelity gaps
3. Phase 3 - lock the filter/lighting source-surface contract
4. Phase 4 - drive closure from ranked W3C failures
5. Phase 5 - formalize release rules and reporting

## Exit Criteria

Phase 2 is complete when all of the following are true:

- the tracked W3C build/open gates remain green
- slideshow capture is stable for the tracked visual profiles
- the animation control corpus plays correctly by eye and in capture
- top-ranked static and animation W3C offenders are materially reduced
- degradation paths are local, explicit, and telemetry-backed
