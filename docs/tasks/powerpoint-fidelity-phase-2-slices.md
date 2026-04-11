# PowerPoint Fidelity Phase 2 - Delivery Slices

**Spec**: `docs/specs/powerpoint-fidelity-phase-2.md`  
**Task plan**: `docs/tasks/powerpoint-fidelity-phase-2-tasks.md`

## Purpose

Break Phase 2 into PR-sized slices that can land independently while keeping:

- the W3C build/open gates green
- the slideshow capture path stable
- the browser-vs-PowerPoint loop usable after every merge

## Slicing Rules

Each slice should:

1. improve one narrow failure class
2. ship with before/after evidence
3. avoid mixing animation, filter, and capture-runtime changes unless the slice is specifically about the runtime
4. leave the ranked-failure loop in a better state than before

## Recommended Slice Order

### Slice 1 - Animation Runtime Baseline

**Task file**

- `docs/tasks/powerpoint-fidelity-slice-1-animation-runtime-baseline.md`

**Why first**

Everything else depends on this. If slideshow entry, Animation Pane visibility, or control-deck playback is flaky, every later fidelity change is hard to trust.

**Scope**

- stabilize `mainSeq`, click-group, and build-list behavior
- normalize `grpId` / `bldP` output across animation families
- keep slideshow startup and teardown reliable
- keep a tiny manual control corpus working:
  - opacity pulse
  - path motion
  - orbit
  - spin/transform pulse

**Primary files**

- `src/svg2ooxml/drawingml/animation/xml_builders.py`
- `src/svg2ooxml/drawingml/animation/writer.py`
- `src/svg2ooxml/drawingml/animation/handlers/*.py`
- `tools/visual/powerpoint_capture.py`
- `tools/visual/pptx_window.py`

**Validation**

- `pytest tests/unit/tools/test_powerpoint_capture.py`
- `pytest tests/unit/drawingml/animation/test_xml_builders.py`
- `pytest tests/unit/core/test_pptx_exporter_animation.py`
- control decks visibly play in slideshow mode

**Exit criteria**

- no inert control decks
- effects visible in the Animation Pane for the control corpus
- slideshow capture stable on the control corpus

### Slice 2 - Authored Scale And Opacity Effects

**Task file**

- `docs/tasks/powerpoint-fidelity-slice-2-authored-scale-opacity.md`

**Why second**

This closes the gap between "timing exists" and "PowerPoint is actually doing the right kind of animation."

**Scope**

- standardize width/height pulse -> authored scale effect family
- standardize visible-shape opacity pulse -> transparency-style emphasis behavior
- eliminate entrance-fade misuse for generic opacity changes

**Primary files**

- `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
- `src/svg2ooxml/drawingml/animation/handlers/opacity.py`
- `tests/unit/drawingml/animation/handlers/test_numeric.py`
- `tests/unit/drawingml/animation/handlers/test_opacity.py`

**Validation**

- `animate-opacity.svg`
- animation control corpus
- targeted slideshow/browser comparison

**Exit criteria**

- opacity pulse and scale pulse behave correctly by eye
- no no-op width/height pulse output on the control corpus

### Slice 3 - Begin/Trigger Semantics And Reason Codes

**Why third**

Once authored effect families work, the next largest mismatch is trigger timing and unsupported begin references.

**Scope**

- improve emitted start conditions for:
  - absolute delays
  - `with previous`
  - `after previous`
  - begin/end target references
- reduce `unsupported_begin_target_missing`
- make reason codes first-class in audit output

**Primary files**

- `src/svg2ooxml/core/animation/parser.py`
- `src/svg2ooxml/drawingml/animation/policy.py`
- `src/svg2ooxml/drawingml/animation/writer.py`
- `tools/visual/corpus_audit.py`

**Exit criteria**

- measurable drop in skipped-fragment counts on the W3C animation set
- clear reason-code summaries in reports

### Slice 4 - Motion And Transform Fidelity

**Why fourth**

After triggers, motion/transform is the next highest-value animation family because it has clear browser truth and clear slideshow failure modes.

**Scope**

- improve path-following playback
- tighten transform mapping for orbit/spin/transformattr cases
- keep authored grouping visible in the Animation Pane

**Primary files**

- `src/svg2ooxml/drawingml/animation/handlers/motion.py`
- `src/svg2ooxml/drawingml/animation/handlers/transform.py`

**Validation fixtures**

- `animate-path.svg`
- `animate-orbit`
- W3C `coords-transformattr-*`

### Slice 5 - Lighting Source-Surface Contract

**Why fifth**

This is the filter equivalent of Slice 1: get the core source-surface semantics right before chasing visual tuning.

**Scope**

- preserve `SourceGraphic` and `SourceAlpha` semantics
- avoid black-only placeholder surfaces unless explicitly correct
- keep approximation policy stable

**Primary files**

- `src/svg2ooxml/drawingml/raster_adapter.py`
- `src/svg2ooxml/render/filters_lighting.py`
- `src/svg2ooxml/filters/primitives/lighting.py`
- `src/svg2ooxml/policy/providers/filter.py`

**Exit criteria**

- no synthetic square source-surface artifacts on the lighting fixtures
- policy regressions covered by tests

### Slice 6 - Lighting And Blur W3C Closure

**Why sixth**

Once the source contract is trustworthy, the next step is to close the worst ranked static W3C failures.

**Scope**

- improve:
  - `filters-light-01-f`
  - `filters-light-02-f`
  - `filters-specular-01-f`
  - `filters-diffuse-01-f`
  - `filters-gauss-01-b`
- keep raster fallback local where native output is wrong

**Exit criteria**

- material browser-vs-PowerPoint improvement on the ranked filter slice
- no new slideshow-entry or repair regressions

### Slice 7 - Text And TSpan Closure

**Why seventh**

`text/tspan` is a major visible gap, but it is easier to tackle after animation runtime and filter stability are no longer moving targets.

**Scope**

- improve line layout, inheritance, and spacing on:
  - `text-tspan-01-b`
- keep text editable where possible

### Slice 8 - WPT Pilot And Release Reporting

**Why last**

This slice formalizes the new workflow once the core fidelity loops are already producing reliable signal.

**Scope**

- add a small WPT pilot slice
- standardize release/report outputs
- keep visual metrics and reason-code summaries first-class

## First Slice To Execute

The recommended first implementation slice is **Slice 1 - Animation Runtime Baseline**.

That slice should be treated as its own PR and should not include:

- filter/lighting algorithm changes
- new WPT integration
- broad text/layout work

It is successful if it gives the team a stable answer to this question:

`If a generated deck should animate, can PowerPoint open it, show the authored effects in the pane, enter slideshow mode, and produce capturable playback every time?`

## Slice Review Template

Each slice PR should include:

- `problem`
- `scope`
- `non-goals`
- `fixtures touched`
- `commands run`
- `before/after artifact paths`
- `remaining ranked failures`
