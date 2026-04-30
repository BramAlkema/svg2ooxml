# Animation Fidelity Specification

**Status:** Draft
**Date:** 2026-03-25
**Context:** SVG SMIL animations generate `<p:timing>` XML that PowerPoint accepts without validation errors, but animations don't play correctly. The timing XML structure, attribute names, and TAV normalization are correct. The issues are in preset mapping, multi-animation coordination, and edge-case handling.

## 1. Current State

The animation pipeline works end-to-end:
- SMIL parsing captures all attributes correctly
- IR `AnimationDefinition` has full metadata
- Handler selection routes to correct handler type
- XML generation produces structurally valid timing blocks
- Shape ID binding maps SVG IDs to PPTX shape IDs
- `ppt_h`, `ppt_w`, `ppt_x`, `ppt_y` attribute names are correct
- TAV `tm` values are correctly normalized to 0–100000 range

## 2. Known Issues

### 2.1. Preset/Behavior Mismatch

**NumericAnimationHandler** uses `presetID=32` (Grow/Shrink) for all numeric property animations. Grow/Shrink expects simultaneous width+height scaling. Animating only `ppt_h` with this preset may cause PowerPoint to:
- Show the animation in the pane but with unexpected behavior
- Apply width changes it shouldn't
- Treat single-axis animation as incomplete

**Fix:** Use property-specific presets:
- `ppt_h` only → custom (`presetID=0`) or Height emphasis
- `ppt_w` only → custom or Width emphasis
- `ppt_h` + `ppt_w` together → Grow/Shrink (`presetID=32`)
- `ppt_x`/`ppt_y` → custom path or Position emphasis

### 2.2. Opacity Handler Limited to Fade Entrance

**OpacityAnimationHandler** hardcodes `presetClass="entr"` (entrance) with fade filter. Issues:
- Already-visible elements don't respond to entrance animations
- Multi-keyframe opacity (`values="0;0.5;1"`) not supported — falls through to NumericAnimationHandler
- `fill-opacity` and `stroke-opacity` treated identically to `opacity`

**Fix:**
- Use `presetClass="emph"` for opacity changes on existing elements
- Support multi-keyframe opacity via `<p:anim>` with `style.opacity` attribute
- Only use entrance fade when the element starts invisible (opacity=0 at begin)

### 2.3. calcMode="discrete" Implemented

SVG `calcMode="discrete"` means instant jumps between values. Numeric, color,
transform, motion, opacity, and set paths now emit `<p:set>` segments or
discrete TAV/path entries rather than relying on PowerPoint interpolation.

**Current approach:** Prefer timed `<p:set>` segments for attributes where
PowerPoint silently ignores `calcmode="discrete"`; use discrete TAV/path entries
only for paths that PowerPoint preserves.

### 2.4. additive="sum" and accumulate="sum"

SVG `additive="sum"` means the animation value is added to the base value. `accumulate="sum"` means each repeat iteration accumulates the previous result.

PowerPoint doesn't have direct equivalents. Current behavior: these attributes are parsed but not applied.

**Fix:** Pre-compute the effective values with additive/accumulate applied, then emit as absolute values in the TAV list.

### 2.5. fill="freeze" vs fill="remove"

SVG `fill="freeze"` means the animation's final value persists. `fill="remove"` means it reverts. PowerPoint uses `fill="hold"` for freeze.

**Current:** The `fill` attribute is set on the `<p:cTn>` but may not be consistently applied across handler types.

### 2.6. repeatCount Mapping

SVG `repeatCount="2"` means play twice. PowerPoint uses `repeatCount="2000"` (thousandths) or `repeatCount="indefinite"`.

**Current:** May not be correctly converting the repeat count format.

### 2.7. Multi-Animation Coordination

The W3C test `animate-elem-02-t.svg` has multiple `<animate>` elements targeting the same attribute on the same element with different `additive`/`accumulate` settings. PowerPoint requires careful sequencing of parallel animations.

**Current:** Each animation is emitted independently without coordination.

## 3. Investigation Plan

### Phase 1: Create reference animations
- Manually create PPTX files with working animations in PowerPoint
- Extract the timing XML as reference
- Compare structure-by-structure with our generated XML
- Document the exact expected format for each animation type

### Phase 2: Fix preset mapping
- Create a preset lookup table mapping SVG attribute + animation type to correct PowerPoint presetID/presetClass
- Handle property-specific presets (height-only, width-only, position, opacity)

### Phase 3: Fix opacity handler
- Support multi-keyframe opacity via `<p:anim>` with `style.opacity`
- Use correct presetClass based on element visibility state

### Phase 4: Handle calcMode, additive, accumulate
- Pre-compute effective values for additive="sum"
- Keep discrete calcMode covered by handler-level regression tests
- Verify fill="freeze" maps to fill="hold"

### Phase 5: Validate against W3C animation suite
- Test all 42 `<animate>` test files
- Test all 14 `<animateTransform>` test files
- Test all 14 `<animateMotion>` test files
- Test all 32 `<set>` test files
- Document which tests pass and which still fail

## 4. Files to Modify

| File | Change |
|------|--------|
| `src/svg2ooxml/drawingml/animation/handlers/numeric.py` | Property-specific preset selection |
| `src/svg2ooxml/drawingml/animation/handlers/opacity.py` | Multi-keyframe support, emph vs entr |
| `src/svg2ooxml/drawingml/animation/tav_builder.py` | discrete TAV support, additive/accumulate pre-computation |
| `src/svg2ooxml/drawingml/animation/xml_builders.py` | additive/accumulate pre-computation |
| `src/svg2ooxml/drawingml/animation/constants.py` | Preset lookup table |

## 5. Flipbook Fallback (added 2026-04-17)

Animations that PPT cannot play natively now have a universal fallback:
the **flipbook renderer** pre-renders N keyframes as stacked shapes and
sequences `<p:set>` visibility toggles. Oracle API:
`AnimationOracle.instantiate_flipbook()`.

Covers: skew, path morph, stroke-width, stroke-opacity, fill-opacity,
complex filter params, and any failed transform decomposition.

Key structural requirement: `<p:bldP>` entries must carry `grpId`
matching the animation `<p:cTn>` group. Mismatched `grpId` causes silent
failure.

Empirical findings from 2026-04-16/17 testing:
- `calcMode="discrete"` on `fillcolor`: silently dropped. Only works on
  `style.visibility`. Use `<p:set>` segments for discrete color jumps.
- `cBhvr additive="sum"` on `<p:animMotion>`: broken (jumps to corner).
  **Never emit.** Concurrent motion paths stack additively by default.
- Sequenced `animScale` + `animRot`: scale applies in rotated frame.
  Cannot produce skew via native primitives on 2D shapes.
- Flipbook with `<p:set>` visibility: **works.** Visually verified with
  8-frame color-cycling test.

## 6. Exit Criteria

- Simple `<animate attributeName="height">` plays correctly in PowerPoint
- Simple `<animate attributeName="opacity">` plays correctly
- `calcMode="discrete"` produces instant jumps via `<p:set>` segments
- `fill="freeze"` holds the final value
- `repeatCount="2"` repeats twice
- Dead-path animations (skew, stroke-width, etc.) render via flipbook fallback
- At least 50% of W3C animation test files play correctly
