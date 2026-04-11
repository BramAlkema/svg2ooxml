# PowerPoint Fidelity Slice 2 - Authored Scale And Opacity Effects

**Spec**: `docs/specs/powerpoint-fidelity-phase-2.md`  
**Task plan**: `docs/tasks/powerpoint-fidelity-phase-2-tasks.md`  
**Slice plan**: `docs/tasks/powerpoint-fidelity-phase-2-slices.md`

## Goal

Replace "legal but weak" animation output for scale and opacity with PowerPoint-authored effect structures that:

1. play in slideshow mode
2. show up correctly in the Animation Pane
3. preserve the intended SVG pulse semantics closely enough for the browser-vs-PowerPoint loop to become useful

This slice is about authored effect-family mapping, not runtime stability. Slice 1 already established the runtime baseline.

## Non-Goals

- Broad begin/trigger overhaul.
- Motion/path fidelity work beyond what is needed to keep combined control fixtures stable.
- Filter or lighting work.
- WPT integration.
- General text/layout fixes.

## Fixtures In Scope

### Primary control fixtures
- `tests/corpus/kelvin_lawrence/animate-opacity.svg`
- `tests/corpus/kelvin_lawrence/animate-size.svg`

### Supporting control fixtures
- `tests/corpus/kelvin_lawrence/animate-spin.svg`
- any local manual PowerPoint-authored reference deck used to compare scale/transparency XML structure

### Spot-check fixture
- `tests/svg/animate-elem-02-t.svg`

## Baseline To Improve

At the start of Slice 2:

- runtime is stable enough to open, enter slideshow mode, and capture the control corpus
- `animate-opacity.svg`, `animate-spin.svg`, and `animate-orbit.svg` still report animation mismatches
- `animate-opacity.svg` remains the primary authored-effect control because it stacks:
  - width pulse
  - opacity pulse
  - repeat
  - autoplay

## Phase 0: Freeze The Slice 2 Baseline

### Task 0.1 - Capture Current Outputs
**Priority**: P0  
**Dependencies**: None

- [ ] Capture current generated PPTX and slideshow output for:
  - `animate-opacity.svg`
  - `animate-size.svg`
- [ ] Record current Pane behavior:
  - number of effects shown
  - whether scale and opacity are separately visible
  - whether playback is visually meaningful or only pane-visible
- [ ] Save current audit outputs under a unique report directory

**Acceptance**
- Before-state artifacts exist and can be compared after the slice lands

## Phase 1: Standardize Authored Scale Effects

### Task 1.1 - Identify Symmetric Pulse Cases
**Priority**: P0  
**Dependencies**: 0.1

- [ ] Audit `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
- [ ] Identify the exact cases that should map to authored scale behavior:
  - width pulse `base -> larger -> base`
  - height pulse `base -> larger -> base`
  - combined width/height pulse
- [ ] Distinguish those from cases that should stay numeric/property based

**Acceptance**
- One deterministic rule exists for "use authored scale effect" vs "stay property animation"

### Task 1.2 - Emit Authored Scale Family Output
**Priority**: P0  
**Dependencies**: 1.1

- [ ] Map symmetric pulse cases to authored scale behavior
- [ ] Preserve:
  - effect grouping
  - autoplay wiring
  - repeat semantics
  - `AutoReverse` where applicable
- [ ] Avoid collapsing to inert `ppt_w` / `ppt_h` no-op behavior

**Files**
- `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
- `src/svg2ooxml/drawingml/animation/xml_builders.py`

**Acceptance**
- Width/height pulse controls behave like real grow/shrink-style effects, not inert property tweens

### Task 1.3 - Keep Scale Effects Visible In Pane
**Priority**: P1  
**Dependencies**: 1.2

- [ ] Verify authored scale effects retain distinct Pane entries
- [ ] Keep `grpId` / `bldP` linkage consistent for scale effects
- [ ] Add XML-level tests for pane-visible scale groups

**Files**
- `tests/unit/drawingml/animation/handlers/test_numeric.py`
- `tests/unit/core/test_pptx_exporter_animation.py`
- `tests/golden/animation/test_golden_master.py`

**Acceptance**
- A regression in scale-effect pane visibility is caught in automated tests

## Phase 2: Standardize Authored Opacity Effects

### Task 2.1 - Separate Visibility/Entrance From Opacity Pulse
**Priority**: P0  
**Dependencies**: 0.1

- [ ] Audit `src/svg2ooxml/drawingml/animation/handlers/opacity.py`
- [ ] Explicitly separate:
  - entrance fade
  - visibility toggles
  - repeating opacity pulse on visible shapes
- [ ] Stop using entrance fade as the generic opacity animation path

**Acceptance**
- Opacity pulse semantics are no longer conflated with entrance semantics

### Task 2.2 - Emit Transparency-Style Emphasis Behavior
**Priority**: P0  
**Dependencies**: 2.1

- [ ] Emit the authored transparency-style effect structure for visible-shape opacity pulse cases
- [ ] Preserve:
  - effect grouping
  - repeat behavior
  - autoplay wiring
- [ ] Keep multi-keyframe or segmented opacity behavior deterministic

**Files**
- `src/svg2ooxml/drawingml/animation/handlers/opacity.py`
- `src/svg2ooxml/drawingml/animation/xml_builders.py`

**Acceptance**
- `animate-opacity.svg` shows real opacity effect playback by eye, not merely pane entries

### Task 2.3 - Keep Opacity Effects Visible In Pane
**Priority**: P1  
**Dependencies**: 2.2

- [ ] Verify opacity emphasis effects show as separate pane-visible entries
- [ ] Keep effect-group bookkeeping consistent
- [ ] Add or refresh XML/golden tests

**Files**
- `tests/unit/drawingml/animation/handlers/test_opacity.py`
- `tests/unit/core/test_pptx_exporter_animation.py`
- `tests/golden/animation/test_golden_master.py`

**Acceptance**
- Opacity-effect pane regressions are caught automatically

## Phase 3: Coordinate Scale + Opacity On The Same Shape

### Task 3.1 - Ensure Stacked Effects Remain Executable
**Priority**: P0  
**Dependencies**: 1.2, 2.2

- [ ] Verify a shape can carry:
  - scale effect
  - opacity effect
  - shared autoplay
  - repeat
- [ ] Ensure neither effect suppresses the other
- [ ] Ensure both remain distinct in the Pane

**Acceptance**
- `animate-opacity.svg` shows both effect families and both contribute to visible playback

### Task 3.2 - Keep Timing And Grouping Deterministic
**Priority**: P1  
**Dependencies**: 3.1

- [ ] Verify concurrent timing on one target is deterministic in generated XML
- [ ] Add integration-style tests for:
  - same target, two effect families
  - repeat/autoreverse combinations

**Files**
- `tests/unit/core/test_pptx_exporter_animation.py`
- `tests/golden/animation/test_golden_master.py`

**Acceptance**
- Stacked scale+opacity output stays stable under refactors

## Phase 4: Validate On Control Fixtures

### Task 4.1 - Re-run `animate-opacity.svg`
**Priority**: P0  
**Dependencies**: 3.1

- [ ] Generate fresh PPTX
- [ ] Capture slideshow output
- [ ] Re-run PowerPoint-backed corpus audit for:
  - `tests/corpus/kelvin_lawrence/animate-opacity.svg`

**Acceptance**
- Pane shows expected effect families
- visible playback improves materially by eye

### Task 4.2 - Re-run `animate-size.svg`
**Priority**: P0  
**Dependencies**: 1.2

- [ ] Generate fresh PPTX
- [ ] Capture slideshow output
- [ ] Re-run PowerPoint-backed corpus audit for:
  - `tests/corpus/kelvin_lawrence/animate-size.svg`

**Acceptance**
- size pulse behaves like an authored scale effect, not an inert numeric tween

### Task 4.3 - Spot-check W3C
**Priority**: P1  
**Dependencies**: 4.1, 4.2

- [ ] Re-run:
  - `tests/svg/animate-elem-02-t.svg`
- [ ] Verify runtime remains stable and note whether the parity score changes

**Acceptance**
- Slice 2 does not regress the Slice 1 runtime baseline on the W3C spot-check

## Validation Commands

### Required automated tests
```bash
pytest tests/unit/drawingml/animation/handlers/test_numeric.py
pytest tests/unit/drawingml/animation/handlers/test_opacity.py
pytest tests/unit/core/test_pptx_exporter_animation.py
pytest tests/golden/animation/test_golden_master.py
pytest tests/unit/tools/test_powerpoint_capture.py
```

### Required manual/control verification
```bash
python -m tools.visual.powerpoint_capture <pptx> <png> --mode slideshow
python -m tools.visual.corpus_audit tests/corpus/kelvin_lawrence/animate-opacity.svg --renderer powerpoint --skip-browser --check-animation
python -m tools.visual.corpus_audit tests/corpus/kelvin_lawrence/animate-size.svg --renderer powerpoint --skip-browser --check-animation
```

## PR Acceptance Artifacts

The Slice 2 PR should include:

- before/after PPTX paths for:
  - `animate-opacity.svg`
  - `animate-size.svg`
- before/after slideshow screenshots
- updated audit outputs
- a short note on:
  - scale effect family mapping
  - opacity effect family mapping
  - Pane visibility
  - visible playback improvement

## Exit Criteria

Slice 2 is complete when all of the following are true:

- scale pulse cases use authored scale behavior instead of inert numeric output
- opacity pulse cases use authored opacity/transparency emphasis instead of generic entrance fade misuse
- `animate-opacity.svg` shows both effect families in the Pane and both contribute to visible playback
- `animate-size.svg` behaves like a real authored size pulse
- Slice 1 runtime stability remains intact
