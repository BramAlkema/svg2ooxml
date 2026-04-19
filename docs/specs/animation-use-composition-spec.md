# Animated `<use>` Composition Specification

- **Status:** Draft
- **Date:** 2026-04-12
- **Primary Fixture:** `tests/svg/animate-elem-30-t.svg`
- **Primary Modules:**
  - `src/svg2ooxml/core/pptx_exporter.py`
  - `src/svg2ooxml/drawingml/animation/constants.py`
  - `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
  - `src/svg2ooxml/drawingml/animation/handlers/transform.py`
  - `src/svg2ooxml/core/styling/use_expander.py`
  - `tools/visual/w3c_proof_deck.py`
  - `tools/visual/structure_compare.py`

## 1. Problem

`animate-elem-30-t.svg` exercises animated `<use>` instances whose referenced
`<defs>` content is also animated. The current PowerPoint output is XML-valid and
plays, but several elements end in the wrong place or use the wrong motion
model.

This is not a single `animMotion` bug. It is a composition bug:

1. source-local geometry changes are being normalized as whole-shape motion
2. outer `<use>` transforms are being emitted independently from inner geometry
3. native PowerPoint effects are emitted even when the combined SVG behavior has
   not been proven representable in DrawingML

## 2. Fixture Contract

The W3C test describes six animated clones. The grey silhouettes show the start
and end states that the moving objects should match.

- **Line:** inner `x1: 30 -> 90`, outer `<use x>: 10 -> 70`
  - Expected result: the rendered line moves right while its endpoint geometry
    changes, producing a visible angle/length change rather than pure
    translation.
- **Rectangle:** inner `height: 20 -> 40` and `fill: white -> blue`, outer
  `translate(0,0 -> 140,0)` plus `scale(1,1 -> 0.5,1)`
  - Expected result: blue rectangle, moved right, horizontally compressed, with
    the combined end pose matching the right-hand silhouette.
- **Circle:** inner `cy: 100 -> 130` plus `scale: 1 -> 1.5`, outer `<use x>:
  10 -> 70`
  - Expected result: diagonal movement plus growth, landing on the end
    silhouette.
- **Polyline:** inner `animateMotion` moves down and `stroke-width: 2 -> 9`,
  outer `rotate: 0 -> 15`
  - Expected result: the stroked path moves down and rotates, with the final
    orientation matching the grey reference.
- **Polygon:** inner `fill: white -> blue`, outer `animateMotion` down plus
  `scaleY: 1 -> 2`
  - Expected result: blue polygon moves down and stretches vertically.
- **Image:** inner `y: 5 -> 145`, outer `scaleY: 0.25 -> 1`
  - Expected result: bitmap moves downward while scaling to full height.

## 3. Current Observed Failure

The original failure mode was broad. After the fixes implemented on
2026-04-12, live PowerPoint capture now shows a narrower residual mismatch.

Current live status:

- the line now shows endpoint-driven motion and length change instead of two
  duplicate pure translations
- the rectangle now moves and scales in the correct general direction
- the circle, polygon, and image now all animate in live PowerPoint capture
- the remaining fidelity gap is the exact landing pose of the scale-driven
  shapes, especially the circle and bitmap image

Residual mismatches:

- the circle lands close to, but not exactly on, the grey end silhouette
- the image lands too low in the captured PowerPoint end frame
- the polygon/vertical rectangle and polyline are improved but still need
  end-pose tightening

This means the current output is not semantically equivalent even though
PowerPoint accepts and plays the timing tree.

## 4. Evidence

### 4.1. IR Expansion

The IR scene already expands the `<use>` content into concrete shapes and keeps
both the source and instance ids in metadata:

- line: `['lineID', 'anim-target-0']`
- rectangle: `['rectID', 'anim-target-2']`
- circle: `['circleID', 'anim-target-1']`
- polyline: `['polylineID', 'anim-target-3']`
- polygon: `['polygonID', 'anim-target-4']`
- image: `['imageID', 'anim-target-5']`

That means the missing piece is not instance identification. The missing piece
is how the final rendered shape composes the source-local animation and the
outer instance animation.

### 4.2. Generated Timing Anomaly

The initial generated slide contained two identical `animMotion` paths for the
line shape. Both were `M 0 0 L 0.125000 0 E`.

That duplication proves the bug:

- inner `x1` was treated as whole-shape x motion
- outer `<use x>` was also treated as whole-shape x motion
- the two were emitted as equivalent translations even though the SVG semantics
  are different

That specific bug has now been fixed by composing simple line endpoint changes
into one motion effect plus one scale effect.

### 4.3. Motion-Space Matrix Gap

The second bug class was inherited-transform loss. Numeric position changes and
`animateTransform translate` were emitted in local SVG units even when the
target lived under an outer transformed `<g>` or `<use>` chain.

Example from this fixture:

- outer group: `translate(20 0) scale(1.3 1.3)`
- inner numeric or translate animations were still emitted using unscaled
  deltas

That caused the moving shapes to under-travel.

This has now been fixed by:

- recording `motion_space_matrix` for motion-like numeric / translate / scale
  animations during SMIL parse
- projecting numeric and translate deltas through the inherited linear
  transform before writing PowerPoint motion paths

### 4.4. Faulty Mapping Site

`src/svg2ooxml/drawingml/animation/constants.py` currently maps:

- `x1`, `x2` -> `ppt_x`
- `y1`, `y2` -> `ppt_y`
- `cx`, `cy` -> `ppt_x` / `ppt_y`

`src/svg2ooxml/drawingml/animation/handlers/numeric.py` then routes those
mapped values into `animMotion`.

That shortcut is only safe for attributes that are semantically whole-shape
translation on the rendered primitive. It is not safe for line endpoints and it
is not generally safe once `<use>` composition is involved.

## 5. Requirements

### R1. Preserve Geometry-Local Meaning

Geometry-local attributes must not be normalized to whole-shape motion unless
the exporter can prove equivalence for the specific rendered primitive.

At minimum this applies to:

- `x1`, `y1`, `x2`, `y2`
- primitive-local width/height changes that alter shape geometry rather than
  only slide position

### R2. Compose on the Rendered Shape

Animations must be composed per rendered PowerPoint shape, not per authored SVG
node in isolation.

The composition input for a rendered shape is:

- source element id(s)
- expanded `<use>` instance id
- local geometry animation(s)
- local transform animation(s)
- outer instance position/transform animation(s)

### R3. Respect SVG Transform Order

For animated clones, the exporter must preserve the SVG order:

- source geometry/local transforms
- `<use>` placement and `<use>` transform
- animation-time transform additions

DrawingML output must be derived from the composed world-space behavior, not by
blindly stacking independent PowerPoint effects and hoping their runtime order
matches SVG.

### R4. Emit Native Only When Representable

If the composed SVG behavior cannot be represented by a stable combination of
PowerPoint effects, the exporter must not emit a misleading native animation.

Fallback order remains:

1. native editable
2. native mimic
3. EMF / raster according to policy

### R5. E2E Validation Is Mandatory

Animation work on this area is not complete when:

- unit tests are green
- XML validates
- the animation pane shows entries

It is complete only when live PowerPoint capture matches the authored W3C
behavior closely enough to satisfy the per-shape review.

## 6. Design

### 6.1. Attribute Classification

Replace the current broad attribute-name shortcut with an explicit
classification stage.

Each animated property must be classified as one of:

- **world-position**
  - examples: outer `<use x>`, outer `<use y>`, composed translate on a fully
    positioned primitive
- **local-geometry**
  - examples: `x1`, `y1`, `x2`, `y2`, primitive `height`, primitive `width`,
    circle center/radius changes when they affect the primitive itself
- **local-style**
  - examples: fill/stroke/opacity/stroke-width
- **local-transform**
  - examples: animateTransform scale/rotate on the source element

Native emission decisions must use this classification instead of only the raw
attribute name.

### 6.2. Per-Shape Composition Pass

Introduce a composition pass before XML emission:

1. group animations by final rendered shape using `metadata["element_ids"]`
2. collect all source-local and instance-level animations affecting that shape
3. derive the composed world-space start/end behavior for each authored segment
4. emit DrawingML only from the composed behavior

This pass belongs logically between scene enrichment and animation XML writing.

### 6.3. Primitive-Specific Native Strategies

#### Line Endpoint Strategy

For line endpoint animation, compute the authored line segment at each keyframe
and derive:

- world-space center translation
- length scaling
- heading delta

If those values are stable, emit a composed native combination:

- `animMotion` for center translation
- `animScale` for line length change
- `animRot` for heading change

If the decomposition is not stable, do not emit a fake pure translation.

#### Rect / Circle / Image Strategy

When local size/center changes combine with outer `<use>` transforms, derive the
final world-space box or center from the composed SVG transform stack first,
then emit native scale/motion around the correct anchor.

The current center-anchored compensation is better than the original output but
still not exact for all scale-driven clones. The residual gap appears to be the
choice of scale origin for additive `scale` on cloned content:

- current implementation uses the rendered element center in slide space
- residual evidence suggests the correct SVG origin is sometimes the clone's
  local user-space origin after inherited transforms, not slide `(0, 0)`

#### Path / Polygon Strategy

For non-primitive geometry, prefer composition into world-space translation /
rotation / scale only when the rendered path remains representable as a shape
transform. If the path itself changes in a way that requires vertex animation,
native emission is not valid.

### 6.4. Coalescing Rules

`_coalesce_simple_position_motions()` must not merge animations that only happen
to touch x/y-like values. It may merge only when both fragments are explicitly
classified as world-position on the rendered shape.

That rule blocks the current false equivalence between `x1` and outer `<use x>`.

At timing-XML level, concurrent simple motion fragments must also collapse to a
single plain `animMotion` effect. The merged result must not carry PowerPoint
runtime-only baggage (`ppt_x`, `ppt_y`, `rCtr`, additive sum) when the path
already encodes the total displacement. Live PowerPoint capture showed those
extra attributes could suppress motion playback for some shape types.

## 8. Implemented Fixes

Implemented in this slice:

- removed line endpoint attributes from generic x/y motion mapping
- composed simple line endpoint + outer position changes into one motion plus
  one scale effect
- added writer-side merge of concurrent simple `animMotion` fragments so
  PowerPoint only sees one motion path per shape/timing bucket
- projected numeric position, numeric scale-anchor, and translate-transform
  deltas through inherited motion-space matrices
- simplified merged motion XML to a plain `animMotion` form that PowerPoint
  actually plays across shape types

Validated with:

- targeted unit coverage across parser, exporter, numeric handler, transform
  handler, and writer
- live proof-deck capture runs in:
  - `reports/visual/w3c-proof-deck-animate-elem-30-line-compose`
  - `reports/visual/w3c-proof-deck-animate-elem-30-motion-merge6`

## 9. Remaining Slice

The next slice should focus only on scale-origin fidelity for additive
`scale` on cloned content:

1. resolve the correct local origin for scale compensation on `<use>` clones
2. validate the circle, polygon, and image end poses against the W3C fixture
3. only then widen the same logic to the rest of the animation corpus

## 7. E2E Execution Spec

### 7.1. Single-Scenario Proof Run

Run the existing proof-deck pipeline on the target scenario:

```bash
.venv/bin/python -m tools.ppt_research.w3c_proof_deck \
  --skip-static \
  --animation-scenarios animate-elem-30-t \
  --animation-duration 4 \
  --fps 4 \
  --output reports/visual/w3c-proof-deck-animate-elem-30
```

Required artifacts:

- browser montage and APNG
- native montage and APNG
- mimic montage and APNG
- rasterised montage and APNG
- generated PPTX for each PowerPoint tier

### 7.2. Structural Audit

Run structural comparison on the generated native PPTX to confirm shape count
and baseline geometry order before diagnosing animation playback.

This catches shape expansion regressions separately from timing regressions.

### 7.3. Live Review Checklist

For `animate-elem-30-t`, review all six moving elements against the W3C
silhouettes.

The run passes only if:

1. line shows endpoint-driven shape change, not pure translation
2. rectangle lands on the expected compressed blue pose
3. circle lands diagonally and scales correctly
4. polyline rotates and thickens while moving down
5. polygon lands on the expected blue stretched pose
6. image reaches the expected end position and full height

## 8. Implementation Slices

### Slice A: Guardrails

- stop treating line endpoints as generic whole-shape position
- tighten motion coalescing to world-position-only inputs
- add unit tests for the bad `x1`/`<use x>` merge

### Slice B: Composition Infrastructure

- add rendered-shape composition grouping
- define classification metadata for animation fragments
- feed composed fragments into XML emission

### Slice C: Line Endpoint Native Path

- implement endpoint decomposition for line primitives
- validate that `animate-elem-30-t` line emits one composed motion/rotation
  result instead of duplicate motion

### Slice D: Use-Clone Scale/Motion Composition

- compose inner size/center changes with outer `<use>` motion/scale
- validate rectangle, circle, polygon, and image end poses

### Slice E: Regression Sweep

- rerun the proof deck for `animate-elem-30-t`
- rerun the broader W3C animation suite
- inspect any changes in `animate-elem-31-t`, `animate-elem-53-t`, and other
  transform-heavy fixtures

## 9. Exit Criteria

This spec is complete when all of the following are true:

- `animate-elem-30-t` passes the live PowerPoint review
- the line no longer emits duplicate equivalent `animMotion` fragments
- world-position coalescing no longer swallows geometry-local animation
- proof-deck artifacts exist for browser, native, mimic, and rasterised modes
- no regression appears in the wider animation W3C sweep
