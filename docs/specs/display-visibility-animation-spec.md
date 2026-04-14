# Display And Visibility Animation Specification

- **Status:** Draft
- **Date:** 2026-04-12
- **Primary Fixture:** `tests/svg/animate-elem-31-t.svg`
- **Secondary Fixture:** `tests/svg/animate-elem-61-t.svg`
- **Primary Modules:**
  - `src/svg2ooxml/core/animation/parser.py`
  - `src/svg2ooxml/core/pptx_exporter.py`
  - `src/svg2ooxml/drawingml/animation/constants.py`
  - `src/svg2ooxml/drawingml/animation/handlers/set.py`
  - `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
  - `src/svg2ooxml/drawingml/animation/writer.py`
  - `tools/visual/w3c_proof_deck.py`
  - `tools/visual/powerpoint_capture.py`

## 1. Problem

The current animation pipeline has no explicit semantic model for SVG
`display` and `visibility`.

That produces two different classes of failure:

1. `display` animations are not compiled into anything PowerPoint actually
   understands at slideshow runtime.
2. inherited group-level show/hide behavior is treated as if it were a
   leaf-level numeric or raw property animation.

This is not a small handler bug. It is a missing compilation stage.

PowerPoint does support native show/hide behavior, but not the SVG rendering
tree model:

- PowerPoint exposes native visibility and entrance/exit animation concepts.
- SVG `display="none"` removes an element and its descendants from rendering.
- SVG `visibility="hidden"` suppresses painting but keeps the element in the
  rendering tree.

So `display` cannot be emitted as a one-to-one PowerPoint property. It must be
compiled into a visibility timeline on the final rendered PowerPoint shapes.

## 2. Fixture Contract

`animate-elem-31-t.svg` is the primary target because it isolates the exact
semantic gap.

The fixture contract is:

- the top grey rectangle uses `display` to show and hide circles
- the bottom grey rectangle uses `visibility` as the reference behavior
- circles with the same color must be visible at the same time
- the cyan case includes repeated blinking with parent and child visibility
  changes
- the file also includes a text node revealed by `<set attributeName="display">`

The fixture exercises these cases:

- always-visible baseline
- group reveal from `display="none"`
- leaf reveal via `<set attributeName="display">`
- hide after visible
- `inherit` under a hidden parent
- repeated show/hide with `values=...` and `repeatCount`
- ancestor gating of all descendants near the end of the slide

`animate-elem-61-t.svg` is the secondary follow-on fixture because it uses
`<set attributeName="display">` as a timing base for other animations. That is
not required for the first delivery slice, but it should shape the design so we
do not dead-end the architecture.

## 3. Current Failure Mode

The current codebase fails this class of SVG for structural reasons.

### 3.1. `SET` Passes Through Raw Attributes

`SetAnimationHandler` currently maps unknown attributes through unchanged and
emits a generic `<p:set>` container for all non-color values.

That means:

- `visibility` is emitted as raw `visibility`
- `display` would also be emitted as raw `display`
- there is no guarantee that PowerPoint slideshow playback recognizes either
  name as an actual runtime property

This behavior is visible in:

- `src/svg2ooxml/drawingml/animation/handlers/set.py`

### 3.2. Numeric Routing Is Too Broad

`NumericAnimationHandler.can_handle()` currently accepts every `ANIMATE`
attribute that is not explicitly filtered out as line endpoint, fade, or color.

That means `animate attributeName="display"` and
`animate attributeName="visibility"` can fall into the numeric path even though
they are categorical, inherited, non-numeric properties.

This behavior is visible in:

- `src/svg2ooxml/drawingml/animation/handlers/numeric.py`

### 3.3. The Pipeline Has No Inherited Visibility State

There is no pass that:

- walks ancestor chains
- evaluates `display` and `visibility` over time
- computes visible intervals per rendered PowerPoint shape

Without that pass, any XML emission is guesswork.

### 3.4. Existing PowerPoint Evidence Points To Visibility, Not Display

Our local PowerPoint sample research found recurring use of:

- `set style.visibility`
- `animEffect` wrappers for entrance presets

It did not find a native PowerPoint concept equivalent to the SVG `display`
render-tree switch.

That evidence is captured in:

- `reports/research/pptx-animation-samples/summary.md`

## 4. Non-Goals

This spec is intentionally narrower than full SMIL parity.

Not in scope for the first implementation slice:

- complete support for all CSS `display` keywords
- DOM-equivalent hit-testing semantics
- optimization of Animation Pane readability before correctness
- `begin="other.repeat(n)"` and similar event-timeline dependencies from
  `animate-elem-61-t.svg`
- group-level emission compaction when leaf-level emission is already correct

## 5. Requirements

### R1. Treat `display` And `visibility` As Discrete Semantic Attributes

They must never be routed through numeric interpolation logic.

### R2. Respect Inheritance

The compiled result must honor:

- static ancestor `display`
- static ancestor `visibility`
- animated ancestor `display`
- animated ancestor `visibility`
- `inherit` on both properties

### R3. Compile To Final Rendered Targets

The exporter must compute show/hide behavior per final rendered PowerPoint
shape, not per authored SVG node in isolation.

### R4. Prefer Editable Native Output

The exporter should prefer an editable PowerPoint representation whenever the
timing can be represented stably.

### R5. Never Emit Raw SVG `display` Into PowerPoint Animation XML

`display` is an SVG semantic input, not a PowerPoint runtime property.

### R6. Support Repeated And Segmented Visibility

The implementation must handle:

- multiple visible intervals
- repeated blinking
- parent/child gating
- `fill="freeze"` vs `fill="remove"`
- `keyTimes` on discrete visibility changes

### R7. Preserve Coexistence With Other Effects

Visibility compilation must not silently discard unrelated color, motion,
transform, or scale animations that target the same rendered shape.

### R8. Validation Must Be Live

Completion requires live PowerPoint capture, not only unit tests or XML
validation.

## 6. Semantic Model

For this spec, the exporter computes two booleans at time `t` for every
rendered SVG leaf:

- `rendered(t)`: whether the element exists in the SVG rendering tree
- `painted(t)`: whether the rendered element is actually visible

The rules are:

- `display="none"` on self or any ancestor forces `rendered(t) = false`
- supported non-`none` display values are treated as render-enabled
- `display="inherit"` resolves against the nearest ancestor value
- `visibility="hidden"` on self or any ancestor forces `painted(t) = false`
  unless a descendant overrides with `visible`
- `visibility="collapse"` is treated as `hidden` in the first slice
- `visibility="inherit"` resolves against the nearest ancestor value
- final visible state is `visible(t) = rendered(t) and painted(t)`

This is the state that must be preserved in PowerPoint.

## 7. Design

### 7.1. Add Explicit Attribute Classification

Introduce explicit classification for show/hide attributes in
`drawingml.animation.constants` or an adjacent visibility module.

Minimum groups:

- `DISPLAY_ATTRIBUTES = {"display"}`
- `VISIBILITY_ATTRIBUTES = {"visibility", "style.visibility"}`
- `DISCRETE_VISIBILITY_ATTRIBUTES = DISPLAY_ATTRIBUTES ∪ VISIBILITY_ATTRIBUTES`

Routing changes:

- `NumericAnimationHandler.can_handle()` must reject `display` and `visibility`
- `SetAnimationHandler` must not pass raw `display` through to PowerPoint

### 7.2. Add A Visibility Timeline Compiler

Add a new compilation pass before final animation XML writing.

Suggested module:

- `src/svg2ooxml/drawingml/animation/visibility_compiler.py`

The compiler input is:

- rendered scene / shape mapping
- parsed SMIL animation definitions
- static `display` and `visibility` attributes from SVG nodes
- begin time, duration, repeat count, fill mode, and keyTimes for discrete
  animations

The compiler output is:

- per-rendered-shape visibility intervals
- strategy decision metadata
- synthetic native animation plan for the writer

Suggested data structures:

```python
@dataclass
class VisibilityInterval:
    start_ms: int
    end_ms: int
    visible: bool
    source_attributes: tuple[str, ...]
    source_element_ids: tuple[str, ...]


@dataclass
class CompiledVisibilityPlan:
    target_shape_id: str
    intervals: list[VisibilityInterval]
    strategy: Literal["native_set", "appear_disappear", "clone_stack", "fallback"]
    clone_shape_ids: tuple[str, ...] = ()
```

### 7.3. Compile On Leaf Shapes, Not Authored Groups

The compiler must resolve behavior on final rendered leaves first.

Reason:

- SVG groups may or may not map one-to-one onto PowerPoint groups
- parent and child `display` may both animate
- clone expansion, `<use>` expansion, and later geometry composition already
  work on rendered shapes

A later optimization may target a PowerPoint group only if all descendants share
an identical visibility plan.

### 7.4. Interval Extraction

For each target leaf shape:

1. collect its own static `display` and `visibility`
2. collect ancestor static `display` and `visibility`
3. collect all self and ancestor `display` / `visibility` animations
4. derive a sorted list of breakpoints from:
   - begin
   - end
   - repeat boundaries
   - keyTimes boundaries
5. evaluate the semantic state on each half-open interval
6. collapse adjacent intervals with the same final visible state

The result is a piecewise-constant visibility timeline.

### 7.5. Native Emission Strategies

The compiler must choose from the following strategy order.

#### Strategy A. Native Visibility Set

Use native set behavior when the shape can remain a single editable object.

Rules:

- show interval start emits `style.visibility = visible`
- hide interval start emits `style.visibility = hidden`
- initial hidden state must be established before the first visible interval
- no raw `display` property is emitted

This is the most semantically direct editable mapping.

#### Strategy B. Appear / Disappear Wrapper

Use `Appear` / `Disappear`-style wrappers when a plain set is unstable in
PowerPoint playback or when the writer needs an explicit effect container.

Rules:

- default to instant show/hide semantics, not fade, unless the source SVG also
  requires a fade-like visual
- use `Appear`, not `Fade`, for pure `display` / `visibility` parity

This is a native editable strategy, but it is still a mimic of SVG `display`,
not a semantic equivalent.

#### Strategy C. Clone Stack

Duplicate the target shape when the visibility timeline cannot be stably
represented on one PowerPoint shape.

Use this when:

- the shape has several disjoint visible windows
- parent and child show/hide interactions make a single runtime state hard to
  preserve
- repeated blinking becomes unreliable as repeated state toggles on one object

Rules:

- one clone per visible interval
- each clone is visible only for its assigned interval
- clone stacking is allowed only when unrelated concurrent animations can also
  be copied or clipped safely

This is still editable, but it increases shape count.

#### Strategy D. Existing Fallback Stack

If native or clone strategies would distort the source behavior, fall back to
the existing non-editable routes under current policy.

Fallback order remains:

1. native editable
2. native mimic
3. EMF / raster fallback

### 7.6. Do Not Treat Sample Fade Decks As The Semantic Target

Our local sample PowerPoint decks commonly combine:

- `set style.visibility = visible`
- `animEffect transition="in" filter="fade"`

That is useful as proof that PowerPoint uses native visibility internally, but
it is not the default semantic target for `animate-elem-31-t.svg`.

The fixture requires synchronized show/hide timing, not a decorative fade.

So the exporter must:

- use visibility behavior as the semantic baseline
- use fade only if a later policy explicitly asks for that visual mimic

### 7.7. Pipeline Placement

The new pass belongs between parsed animation collection and final handler
emission.

Proposed sequence:

1. parse SMIL into `AnimationDefinition`
2. classify visibility/display-related animations
3. compile per-shape visibility plans
4. remove or replace original `display` animations with synthetic native plans
5. emit all remaining non-visibility animations through the normal writer
6. merge visibility plans into the same timing tree

This prevents the downstream handlers from having to understand SVG inheritance
directly.

## 8. Implementation Slices

### Slice 1. `animate-elem-31-t` Correctness

Scope:

- `display`
- `visibility`
- `none`, `inline`, `inherit`
- `visible`, `hidden`, `inherit`, `collapse -> hidden`
- time-offset `begin`
- numeric `repeatCount`
- `fill="freeze"` and `fill="remove"`
- `keyTimes` for discrete value sequences
- leaf-targeted plans

Acceptance target:

- live PowerPoint playback for `animate-elem-31-t.svg` matches the bottom
  reference row closely enough to pass manual review

### Slice 2. Structured Reuse And Clone Strategy

Scope:

- robust clone stacking for repeated or segmented intervals
- interaction with concurrent color / transform / motion effects
- group-target optimization when safe

Acceptance target:

- cyan repeated blinking remains stable in slideshow mode without collapsing to
  raster fallback

### Slice 3. Event-Timeline Dependencies

Scope:

- `syncBase.begin + 1s`
- `repeatBase.repeat(1)`
- related timing-base semantics from `animate-elem-61-t.svg`

Acceptance target:

- `display`-based timing dependencies compose correctly with `<set>` timing
  chains

## 9. Test Plan

### 9.1. Unit Tests

Add targeted tests for:

- visibility attribute classification
- `NumericAnimationHandler` rejecting `display` / `visibility`
- compiler evaluation of:
  - green reveal
  - dodgerblue `<set display>`
  - blue hide
  - yellow reveal through `inherit`
  - cyan repeated blinking
  - end-of-slide ancestor gating
  - text reveal via `<set display>`
- no emitted `<p:attrName>display</p:attrName>` in slide XML
- emitted native visibility plan uses `style.visibility` or compiled clone
  strategy

### 9.2. Integration Tests

Add slide-level export tests asserting:

- `animate-elem-31-t.svg` produces timing XML with no raw SVG `display`
- visibility plans coexist with non-visibility animations on the same slide

### 9.3. Visual Tests

Run:

```bash
./.venv/bin/python -m tools.visual.w3c_proof_deck \
  --output reports/visual/display-visibility-spec \
  --animation-scenarios animate-elem-31-t
```

Then capture live PowerPoint playback and compare:

- top row vs bottom row for each color
- repeated cyan blink timing
- red "Test running..." text visibility

## 10. Exit Criteria

This spec is complete when all of the following are true:

- `animate-elem-31-t.svg` plays correctly enough in live PowerPoint capture to
  satisfy manual comparison
- no raw SVG `display` animation property is emitted into PowerPoint XML
- `display` / `visibility` animations no longer route through numeric handling
- the implementation remains editable for the primary fixture
- unit and integration coverage exists for the compiler logic

`animate-elem-61-t.svg` support is a follow-on requirement, not a blocker for
the first delivery slice.

## 11. References

- Local code:
  - `src/svg2ooxml/drawingml/animation/handlers/set.py`
  - `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
  - `src/svg2ooxml/drawingml/animation/constants.py`
  - `tests/svg/animate-elem-31-t.svg`
  - `tests/svg/animate-elem-61-t.svg`
  - `reports/research/pptx-animation-samples/summary.md`
- External references:
  - MDN SVG `display`: https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Attribute/display
  - MDN SVG `visibility`: https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Attribute/visibility
  - PowerPoint `Sequence.AddEffect`: https://learn.microsoft.com/en-us/office/vba/api/powerpoint.sequence.addeffect
  - PowerPoint animation properties: https://learn.microsoft.com/en-us/office/vba/api/powerpoint.msoanimproperty
  - PresentationML animation overview: https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-animation
