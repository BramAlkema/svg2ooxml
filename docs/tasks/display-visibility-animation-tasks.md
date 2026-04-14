# Display And Visibility Animation - Implementation Tasks

**Spec**: `docs/specs/display-visibility-animation-spec.md`

## Phase 0: Baseline And Guardrails

### Task 0.1 - Freeze The Current `animate-elem-31-t` Baseline
**Priority**: P0
**Dependencies**: None

- [ ] Generate the current PPTX for `tests/svg/animate-elem-31-t.svg`
- [ ] Capture current live PowerPoint playback under a unique report directory
- [ ] Record the current visible mismatches:
  - top row not matching bottom row
  - missing `display`-driven circles
  - missing "Test running..." text

**Acceptance**
- Before-state artifacts exist under `reports/visual/`

### Task 0.2 - Add Explicit Regression Guards
**Priority**: P0
**Dependencies**: 0.1

- [ ] Add a test asserting no raw `<p:attrName>display</p:attrName>` is emitted
- [ ] Add a test asserting `display` / `visibility` do not route through numeric handling

**Files**
- `tests/unit/core/test_pptx_exporter_animation.py`
- `tests/unit/drawingml/animation/handlers/test_numeric.py`

**Acceptance**
- A future regression cannot silently reintroduce raw SVG `display` into emitted PPTX timing XML

## Phase 1: Classification And Routing

### Task 1.1 - Add Visibility Attribute Classification
**Priority**: P0
**Dependencies**: 0.2

- [ ] Add explicit constant groups for:
  - `display`
  - `visibility`
  - PowerPoint-native `style.visibility`
- [ ] Keep the constant layout coherent with the rest of `drawingml.animation.constants`

**Files**
- `src/svg2ooxml/drawingml/animation/constants.py`
- `tests/unit/drawingml/animation/test_constants.py`

**Acceptance**
- The codebase has one explicit source of truth for show/hide attribute routing

### Task 1.2 - Reject `display` / `visibility` In Numeric Handler
**Priority**: P0
**Dependencies**: 1.1

- [ ] Update `NumericAnimationHandler.can_handle()` to reject:
  - `display`
  - `visibility`
  - any normalized show/hide aliases handled elsewhere
- [ ] Add targeted tests

**Files**
- `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
- `tests/unit/drawingml/animation/handlers/test_numeric.py`

**Acceptance**
- Discrete show/hide attributes cannot fall into numeric interpolation logic

### Task 1.3 - Stop Passing Raw `display` Through `SetAnimationHandler`
**Priority**: P0
**Dependencies**: 1.1

- [ ] Ensure `display` is never emitted as a raw PowerPoint animation property
- [ ] Keep `style.visibility` as the native PowerPoint property target
- [ ] Add tests for both `display` and `visibility`

**Files**
- `src/svg2ooxml/drawingml/animation/handlers/set.py`
- `tests/unit/drawingml/animation/handlers/test_set.py`

**Acceptance**
- `display` is treated as compiler input only, not as emitted PowerPoint runtime XML

## Phase 2: Visibility Timeline Compiler

### Task 2.1 - Introduce Compiler Data Structures
**Priority**: P0
**Dependencies**: 1.2, 1.3

- [ ] Add datatypes for:
  - visibility intervals
  - compiled visibility plans
  - strategy selection metadata
- [ ] Keep the types local to a new visibility compiler module unless reuse pressure appears

**Files**
- `src/svg2ooxml/drawingml/animation/visibility_compiler.py`
- `tests/unit/drawingml/animation/test_visibility_compiler.py`

**Acceptance**
- Compiler output is typed, inspectable, and unit-testable without writing slide XML

### Task 2.2 - Collect Static And Animated Ancestor State
**Priority**: P0
**Dependencies**: 2.1

- [ ] Walk self + ancestor chains for `display`
- [ ] Walk self + ancestor chains for `visibility`
- [ ] Collect related SMIL animations affecting those properties
- [ ] Preserve `inherit` resolution information

**Files**
- `src/svg2ooxml/drawingml/animation/visibility_compiler.py`
- `tests/unit/drawingml/animation/test_visibility_compiler.py`

**Acceptance**
- The compiler can evaluate a leaf shape’s inherited visibility inputs without guessing

### Task 2.3 - Compute Breakpoints And Piecewise-Constant Intervals
**Priority**: P0
**Dependencies**: 2.2

- [ ] Build the breakpoint list from:
  - begin times
  - end times
  - repeat boundaries
  - discrete `keyTimes`
- [ ] Evaluate visibility state across each half-open interval
- [ ] Collapse adjacent equal-state intervals

**Files**
- `src/svg2ooxml/drawingml/animation/visibility_compiler.py`
- `tests/unit/drawingml/animation/test_visibility_compiler.py`

**Acceptance**
- The compiler produces deterministic visible/hidden intervals for a rendered leaf shape

### Task 2.4 - Cover The `animate-elem-31-t` Cases
**Priority**: P0
**Dependencies**: 2.3

- [ ] Add unit cases for:
  - green reveal
  - dodgerblue `<set display>`
  - blue hide
  - yellow reveal via `inherit`
  - cyan repeated blink
  - final ancestor hide at 6s
  - red text reveal

**Files**
- `tests/unit/drawingml/animation/test_visibility_compiler.py`

**Acceptance**
- The compiler reproduces the intended top-row visibility timeline from the fixture

## Phase 3: Writer Integration For Slice 1

### Task 3.1 - Inject Visibility Compilation Into Export Pipeline
**Priority**: P0
**Dependencies**: 2.4

- [ ] Insert a visibility compilation stage between parsed animation collection and final XML emission
- [ ] Replace or remove original `display` animations after compilation
- [ ] Preserve unrelated non-visibility animations

**Files**
- `src/svg2ooxml/core/pptx_exporter.py`
- `src/svg2ooxml/drawingml/animation/writer.py`
- `tests/unit/core/test_pptx_exporter_animation.py`

**Acceptance**
- Exported slides carry synthetic native visibility plans rather than raw SVG `display` animations

### Task 3.2 - Emit Native `style.visibility` Plans
**Priority**: P0
**Dependencies**: 3.1

- [ ] Map visible interval starts to `style.visibility = visible`
- [ ] Map hidden interval starts to `style.visibility = hidden`
- [ ] Establish an initial hidden state where required
- [ ] Keep the result editable

**Files**
- `src/svg2ooxml/drawingml/animation/writer.py`
- `src/svg2ooxml/drawingml/animation/xml_builders.py`
- `tests/unit/core/test_pptx_exporter_animation.py`

**Acceptance**
- `animate-elem-31-t.svg` exports with native visibility timing and no raw `display`

### Task 3.3 - Use Native Appear/Disappear Only Where Needed
**Priority**: P1
**Dependencies**: 3.2

- [ ] Add a controlled path for `Appear` / `Disappear` wrappers when plain visibility sets are unstable
- [ ] Keep the default semantics instant, not fade
- [ ] Do not let decorative fade become the default show/hide behavior

**Files**
- `src/svg2ooxml/drawingml/animation/writer.py`
- `src/svg2ooxml/drawingml/animation/xml_builders.py`
- `tests/unit/core/test_pptx_exporter_animation.py`

**Acceptance**
- The writer has a native fallback for unstable set-only playback without changing the semantic target

## Phase 4: Visual Validation For Slice 1

### Task 4.1 - Validate `animate-elem-31-t` Live In PowerPoint
**Priority**: P0
**Dependencies**: 3.2

- [ ] Generate fresh PPTX output
- [ ] Capture live slideshow playback
- [ ] Compare:
  - top purple vs bottom purple
  - top green vs bottom green
  - top dodgerblue vs bottom dodgerblue
  - top blue vs bottom blue
  - top yellow vs bottom yellow
  - top cyan vs bottom cyan
  - red "Test running..." text

**Commands**
- `./.venv/bin/python -m tools.visual.w3c_proof_deck --output reports/visual/display-visibility-spec --animation-scenarios animate-elem-31-t`

**Acceptance**
- The top row and bottom row are synchronized closely enough to pass manual review

### Task 4.2 - Lock In Tests And Artifacts
**Priority**: P1
**Dependencies**: 4.1

- [ ] Save the report directory for the fixed output
- [ ] Add or refresh any golden XML assertions required by the new visibility writer path
- [ ] Document any residual mismatch explicitly if full parity is not yet achieved

**Acceptance**
- The slice can be reviewed without reproducing the entire investigation from scratch

## Phase 5: Follow-On Slice For Clone Stack

### Task 5.1 - Add Clone-Stack Strategy Selection
**Priority**: P1
**Dependencies**: 4.1

- [ ] Detect cases where a single-shape visibility timeline is too unstable or too segmented
- [ ] Select `clone_stack` for those plans
- [ ] Keep shape duplication isolated to the compiler strategy layer

**Files**
- `src/svg2ooxml/drawingml/animation/visibility_compiler.py`
- `src/svg2ooxml/core/pptx_exporter.py`

**Acceptance**
- Repeated blinking and segmented visibility can stay editable without abusing raw PowerPoint properties

### Task 5.2 - Preserve Other Animations On Cloned Shapes
**Priority**: P1
**Dependencies**: 5.1

- [ ] Copy or clip concurrent color / transform / motion effects to the relevant clone interval
- [ ] Avoid double-playing unrelated effects across all clones

**Acceptance**
- Clone stacking does not break unrelated animation fidelity

## Phase 6: Follow-On Slice For Timing-Base Dependencies

### Task 6.1 - Support `display` As A Timing Base
**Priority**: P2
**Dependencies**: 4.1

- [ ] Handle `syncBase.begin + 1s`
- [ ] Handle `repeatBase.repeat(n)`
- [ ] Prove the compiler output can still expose the right timing anchors

**Files**
- `src/svg2ooxml/core/animation/parser.py`
- `src/svg2ooxml/drawingml/animation/visibility_compiler.py`
- `tests/unit/core/animation/test_smil_parser.py`
- `tests/unit/drawingml/animation/test_visibility_compiler.py`

**Acceptance**
- `animate-elem-61-t.svg` becomes reachable without redesigning the visibility compiler

## Execution Notes

- Slice 1 is complete only when live PowerPoint playback is correct enough by eye.
- Do not merge a partial implementation that merely swaps one raw XML property for another.
- Keep the primary semantic target as visibility parity, not fade aesthetics.
