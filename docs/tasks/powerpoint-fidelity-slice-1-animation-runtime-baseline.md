# PowerPoint Fidelity Slice 1 - Animation Runtime Baseline

**Spec**: `docs/specs/powerpoint-fidelity-phase-2.md`  
**Task plan**: `docs/tasks/powerpoint-fidelity-phase-2-tasks.md`  
**Slice plan**: `docs/tasks/powerpoint-fidelity-phase-2-slices.md`

## Goal

Make generated animation decks reliably:

1. open in PowerPoint
2. show the expected authored effects in the Animation Pane
3. enter slideshow mode
4. produce capturable slideshow playback

This slice is successful only if the runtime loop is stable enough to trust later fidelity work.

## Non-Goals

- Fix filter/lighting fidelity.
- Add WPT integration.
- Tackle broad text/layout issues.
- Close all animation fidelity gaps.

## Fixtures In Scope

### Manual control fixtures
- `tests/corpus/kelvin_lawrence/animate-opacity.svg`
- `tests/corpus/kelvin_lawrence/animate-path.svg`
- local/manual orbit control fixture
- local/manual spin control fixture

### W3C spot-check fixtures
- `tests/svg/animate-elem-02-t.svg`
- `tests/svg/coords-transformattr-01-f.svg`

## Phase 0: Freeze The Baseline

### Task 0.1 - Capture Current Control Outputs
**Priority**: P0  
**Dependencies**: None

- [ ] Generate fresh PPTX artifacts for the control fixtures with unique names
- [ ] Store or reference:
  - generated PPTX path
  - PowerPoint slideshow screenshot path
  - any diagnostic JSON produced on failure
- [ ] Record the current known-good / known-bad behavior in a short note

**Acceptance**
- Before-state artifacts exist for each control fixture
- We can tell whether each failure is:
  - open failure
  - pane-only/inert
  - slideshow-entry failure
  - screenshot/capture failure

## Phase 1: Build-List And Timing-Tree Stability

### Task 1.1 - Audit Timing Container Output
**Priority**: P0  
**Dependencies**: 0.1

- [ ] Audit `src/svg2ooxml/drawingml/animation/xml_builders.py`
- [ ] Verify:
  - `mainSeq` structure
  - click-group structure
  - begin-trigger structure
  - `delay="indefinite"` vs immediate start behavior
- [ ] Compare one generated control deck against a real PowerPoint-authored control deck

**Acceptance**
- One written note captures the expected authored timing-tree shape for the control corpus

### Task 1.2 - Normalize `grpId` / `bldP` Wiring
**Priority**: P0  
**Dependencies**: 1.1

- [ ] Audit all animation handlers for nonzero effect-group usage
- [ ] Ensure every authored effect group has:
  - consistent `grpId`
  - matching `bldP`
  - correct shape binding
- [ ] Remove any remaining `grpId="0"` output for effect entries that should appear as separate pane items

**Files**
- `src/svg2ooxml/drawingml/animation/xml_builders.py`
- `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
- `src/svg2ooxml/drawingml/animation/handlers/opacity.py`
- `src/svg2ooxml/drawingml/animation/handlers/motion.py`
- `src/svg2ooxml/drawingml/animation/handlers/color.py`
- `src/svg2ooxml/drawingml/animation/handlers/set.py`
- `src/svg2ooxml/drawingml/animation/handlers/transform.py`

**Acceptance**
- Control fixtures show expected grouped effects in the Animation Pane

### Task 1.3 - Keep Pane Visibility Under Test
**Priority**: P1  
**Dependencies**: 1.2

- [ ] Add or extend tests asserting:
  - build-list entries are emitted
  - effect groups are nonzero where expected
  - authored effect families retain pane-visible grouping

**Files**
- `tests/unit/drawingml/animation/test_xml_builders.py`
- `tests/unit/core/test_pptx_exporter_animation.py`
- `tests/golden/animation/test_golden_master.py`

**Acceptance**
- Pane-related XML regressions are caught by automated tests

## Phase 2: Slideshow Entry And Capture Reliability

### Task 2.1 - Stabilize Deck Open And Selection
**Priority**: P0  
**Dependencies**: 0.1

- [ ] Keep staged-deck open behavior deterministic
- [ ] Verify PowerPoint deck matching uses stable, non-looping presentation lookup
- [ ] Ensure open flow works when:
  - PowerPoint is closed
  - PowerPoint is on the Home screen
  - the staged file is already present

**Files**
- `tools/visual/powerpoint_capture.py`
- `tools/visual/pptx_window.py`

**Acceptance**
- No manual file-open interaction is required for the control corpus

### Task 2.2 - Stabilize Slideshow Start
**Priority**: P0  
**Dependencies**: 2.1

- [ ] Verify slideshow-start order:
  - object-model start
  - menu/UI fallback
  - key fallback when enabled
- [ ] Keep explicit diagnostics for:
  - no active presentation
  - edit-view stall
  - slideshow window missing
- [ ] Ensure slideshow settings are compatible with windowed playback on Mac

**Acceptance**
- Control decks enter slideshow mode without manual intervention

### Task 2.3 - Stabilize Slideshow Teardown
**Priority**: P1  
**Dependencies**: 2.2

- [ ] Ensure teardown:
  - exits slideshow if running
  - closes the staged deck, not an arbitrary active deck
  - leaves PowerPoint in a predictable state

**Acceptance**
- Control runs do not leave orphan slideshow sessions or random open decks behind

### Task 2.4 - Keep Runtime Tests Honest
**Priority**: P1  
**Dependencies**: 2.1, 2.2, 2.3

- [ ] Expand test coverage for:
  - staged open flow
  - matching presentation lookup
  - slideshow startup fallbacks
  - targeted close behavior
  - diagnostics on failure

**Files**
- `tests/unit/tools/test_powerpoint_capture.py`
- `tests/unit/tools/test_visual_renderer.py`

**Acceptance**
- Runtime regressions are covered in unit tests, not just manual runs

## Phase 3: Control Corpus Hardening

### Task 3.1 - Formalize The Manual Control Decks
**Priority**: P1  
**Dependencies**: 1.2, 2.2

- [ ] Ensure the control corpus has stable fixture paths for:
  - opacity pulse
  - path motion
  - orbit
  - spin/transform pulse
- [ ] Add short expected-behavior notes for each fixture

**Acceptance**
- Reviewers can tell by eye what each control fixture is supposed to do

### Task 3.2 - Add A Minimal Smoke Runner
**Priority**: P1  
**Dependencies**: 3.1

- [ ] Add or document a single command that:
  - builds the control decks
  - captures slideshow output
  - stores artifacts under a stable report path

**Acceptance**
- One command reproduces the slice validation loop

## Validation Commands

### Required automated tests
```bash
pytest tests/unit/tools/test_powerpoint_capture.py
pytest tests/unit/tools/test_visual_renderer.py
pytest tests/unit/drawingml/animation/test_xml_builders.py
pytest tests/unit/core/test_pptx_exporter_animation.py
pytest tests/golden/animation/test_golden_master.py
```

### Required manual/control verification
```bash
python -m tools.visual.powerpoint_capture <pptx> <png> --mode slideshow
python -m tools.visual.corpus_audit <fixture> --renderer powerpoint --check-animation
```

## PR Acceptance Artifacts

The Slice 1 PR should include:

- before/after PPTX paths for each control fixture
- before/after slideshow screenshots for each control fixture
- any diagnostic JSON for failures that were fixed
- a short note on:
  - pane visibility
  - slideshow entry
  - slideshow capture stability

## Exit Criteria

Slice 1 is complete when all of the following are true:

- control decks show expected effects in the Animation Pane
- control decks enter slideshow mode without manual intervention
- slideshow capture succeeds on the control corpus
- runtime regressions are covered by automated tests
- the slice leaves later fidelity work with a stable slideshow/browser feedback loop
