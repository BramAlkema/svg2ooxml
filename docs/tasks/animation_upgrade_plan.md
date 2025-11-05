# Animation Fidelity Upgrade Plan

## Objective
Raise animation fidelity in svg2ooxml by widening SVG feature coverage, preserving SMIL semantics, and expanding regression signals so PowerPoint output tracks the original motion, timing, and easing more closely.

## Workstream Breakdown

### 1. Broaden Transform Support
- [ ] Extend `src/svg2ooxml/drawingml/animation/handlers/transform.py` to recognise translate, skew, and matrix transform types alongside scale/rotate.
- [ ] Implement `_build_translate_animation` so translate animations emit `<a:animMotion>` (or appropriate motion XML) instead of returning an empty string.
- [ ] Add unit tests in `tests/unit/drawingml/animation/handlers/test_transform.py` that cover translate/skew inputs and assert XML routing.

### 2. Improve Motion Path Accuracy
- [ ] Expand `MotionAnimationHandler._parse_motion_path` to handle arc and quadratic segments, and revisit the sampling routine to use curvature-aware subdivision instead of a fixed 20-step grid.
- [ ] Preserve loop closures by keeping the final vertex when a path returns to its origin.
- [ ] Create unit tests plus a new visual baseline showing curved and closed paths.

### 3. Respect Repeat & Fill Semantics
- [ ] Thread `animation.repeat_count` and `animation.fill_mode` through each handler into `AnimationXMLBuilder.build_behavior_core`, letting PowerPoint see `repeatCount` and `fill="remove"` when required.
- [ ] Write regression tests that cover freeze vs remove behaviour and both finite and indefinite loops.

### 4. Enable Additive & Accumulate Modes
- [ ] Map IR `additive` and `accumulate` values to the correct PPT attributes or deterministic stacking logic when native support is limited.
- [ ] Expand conflict-resolution tests to cover sum/replace interplay so blended animations remain predictable.

### 5. Surface Native Easing
- [ ] Translate `calcMode` and `keySplines` into native PPT acceleration/deceleration attributes rather than relying solely on custom `svg2:` metadata.
- [ ] Add spline-heavy unit tests validating that easing curves survive export.

### 6. Handle Indefinite Durations
- [ ] Detect `float("inf")` durations in `AnimationDefinition` and emit PPT timing nodes with `dur="indefinite"` to avoid integer overflow.
- [ ] Cover this path with parser and handler tests using indefinite `dur` values.

### 7. Refine Transform Scaling & Keyframes
- [ ] Audit scale/rotate handlers to ensure keyframe data, easing, and unit conversions remain intact across multi-keyframe animations.
- [ ] Add integration-style tests that assert expected PPT angle and scale values for known inputs.

### 8. Strengthen Visual Regression Coverage
- [ ] Build composite sample decks (motion + fade, transform + color, repeated loops, triggered sequences) and add PPTX goldens under `tests/visual/golden/`.
- [ ] Wire these scenarios into the visual regression harness so CI can flag behavioural drift.

### 9. Guard Attribute Mapping
- [ ] Add a lint/check helper under `tools/` that validates every animated attribute resolves via `ATTRIBUTE_NAME_MAP` or `COLOR_ATTRIBUTE_NAME_MAP`.
- [ ] Fail fast when unmapped attributes reach XML generation to prevent silent no-ops.

### 10. Document Upgrades
- [ ] Update `docs/` (architecture notes, porting guide) with the new handler capabilities, sampling heuristics, and testing workflows.
- [ ] Capture outstanding edge cases and follow-up items in `docs/porting.md` so future ports stay aligned.

## Validation Checklist
- Unit suite (`pytest tests/unit -m "unit and not slow"`) passes with new coverage for translate/easing/repeat scenarios.
- Visual regression suite incorporates new animation goldens and runs cleanly.
- Manual spot-check of generated PPTX confirms translate, loops, easing, and composites behave as intended.

## Risks & Mitigations
- **Sampling regressions**: Use adaptive thresholds guarded by tests to avoid oversampling; document defaults.
- **PPT capability gaps**: When PowerPoint lacks a direct analogue (e.g., accumulate), document fallbacks and surface warnings in logs.
- **Fixture drift**: Establish a short “before/after” note whenever visual baselines update to keep reviewers oriented.
