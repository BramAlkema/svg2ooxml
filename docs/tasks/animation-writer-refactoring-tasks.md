# Animation Writer Refactoring - Implementation Tasks

**Spec**: `docs/specs/animation-writer-refactoring-spec.md`

**Goal**: Refactor `animation_writer.py` (1,085 LOC, 112 XML concatenations) into a modular, lxml-based architecture.

---

## Phase 1: Foundation & Infrastructure (Est. 6-8 hours)
**Updated**: Reduced from 8-10 hours by leveraging `common.conversions` module!

### Task 1.1: Create Module Structure
**Est**: 30 min
**Priority**: P0 - Blocker

- [ ] Create `src/svg2ooxml/drawingml/animation/` directory
- [ ] Create `__init__.py` (export public API)
- [ ] Create `handlers/` subdirectory with `__init__.py`
- [ ] Verify imports work

**Acceptance**:
- Module can be imported: `from svg2ooxml.drawingml.animation import ...`

---

### Task 1.2: Implement `constants.py`
**Est**: 1 hour
**Priority**: P0 - Blocker
**Dependencies**: 1.1

- [ ] Extract all constants from `animation_writer.py`
- [ ] Create `FADE_ATTRIBUTES`, `COLOR_ATTRIBUTES` as frozensets
- [ ] Create `ATTRIBUTE_NAME_MAP`, `COLOR_ATTRIBUTE_NAME_MAP` dicts
- [ ] Create `AXIS_MAP`, `ANGLE_ATTRIBUTES`
- [ ] Define `SVG2_ANIMATION_NS` constant
- [ ] Add docstrings for each constant group
- [ ] Write unit tests verifying constant values

**Acceptance**:
- All constants importable
- Tests pass: `pytest tests/unit/drawingml/animation/test_constants.py`

**Files**:
- `src/svg2ooxml/drawingml/animation/constants.py`
- `tests/unit/drawingml/animation/test_constants.py`

---

### Task 1.3: Implement `value_processors.py` (Adapter for common.conversions)
**Est**: 1 hour (REDUCED - uses existing conversions module!)
**Priority**: P0 - Blocker
**Dependencies**: 1.2, common.conversions module

**UPDATED**: This task now leverages the centralized conversions module we just created!

- [ ] Create `ValueProcessor` class as adapter around `common.conversions`
- [ ] Import and delegate to existing conversion functions:
  - `parse_numeric_list` → `conversions.parse_numeric_list`
  - `parse_color` → `conversions.color_to_hex`
  - `parse_angle` → `conversions.parse_angle`
  - `parse_scale_pair` → `conversions.parse_scale_pair`
  - `parse_translation_pair` → `conversions.parse_translation_pair`
- [ ] Implement animation-specific helpers:
  - `normalize_numeric_value(attribute, value, unit_converter)` - handles attribute-specific conversion to PPT units
  - `parse_opacity(value)` → uses `conversions.opacity_to_ppt` internally
  - `format_ppt_angle(degrees)` → uses `conversions.degrees_to_ppt`
- [ ] Write unit tests (mainly integration tests since core logic is tested)
- [ ] Test animation-specific normalization logic

**Acceptance**:
- ValueProcessor correctly delegates to conversions module
- Animation-specific logic works correctly
- Tests pass: `pytest tests/unit/drawingml/animation/test_value_processors.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/value_processors.py`
- `tests/unit/drawingml/animation/test_value_processors.py`

**Notes**:
- Most parsing logic already tested in conversions module (137 tests)
- Focus on animation-specific attribute normalization
- Estimated time reduced from 3 hours to 1 hour!

---

### Task 1.4: Implement `xml_builders.py`
**Est**: 3-4 hours
**Priority**: P0 - Blocker
**Dependencies**: 1.1

- [ ] Create `AnimationXMLBuilder` class
- [ ] Implement `build_timing_container(timing_id, fragments) -> str`
- [ ] Implement `build_par_container(par_id, duration_ms, delay_ms, child_content) -> str`
- [ ] Implement `build_behavior_core(behavior_id, duration_ms, target_shape, ...) -> etree._Element`
- [ ] Implement `build_attribute_list(attribute_names) -> etree._Element`
- [ ] Implement `build_tav_element(tm, value_elem, accel, decel, metadata) -> etree._Element`
- [ ] Implement `build_start_condition(delay_ms) -> etree._Element`
- [ ] Add namespace handling for `svg2:` custom namespace
- [ ] Write unit tests for each builder method
- [ ] Verify XML structure matches expected schema
- [ ] Test namespace declarations

**Acceptance**:
- All builders produce valid lxml elements
- XML output matches PowerPoint timing schema
- Tests pass: `pytest tests/unit/drawingml/animation/test_xml_builders.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/xml_builders.py`
- `tests/unit/drawingml/animation/test_xml_builders.py`

---

## Phase 2: Core Components (Est. 8-10 hours)

### Task 2.1: Implement `policy.py`
**Est**: 2 hours
**Priority**: P0 - Blocker
**Dependencies**: None

- [ ] Create `AnimationPolicy` class
- [ ] Implement `__init__(options: Mapping[str, Any])`
- [ ] Implement `should_skip(animation, max_error) -> tuple[bool, str | None]`
- [ ] Implement `estimate_spline_error(animation) -> float`
- [ ] Implement `_estimate_spline_error(spline, samples) -> float` helper
- [ ] Implement `_coerce_bool_option(value, default) -> bool`
- [ ] Implement `_coerce_float_option(value, default) -> float`
- [ ] Write unit tests for policy decisions
- [ ] Test all skip reasons
- [ ] Test spline error estimation

**Acceptance**:
- Policy correctly determines skip conditions
- Spline error estimation works
- Tests pass: `pytest tests/unit/drawingml/animation/test_policy.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/policy.py`
- `tests/unit/drawingml/animation/test_policy.py`

---

### Task 2.2: Implement `tav_builder.py` - Part 1 (Core)
**Est**: 2 hours
**Priority**: P0 - Blocker
**Dependencies**: 1.4

- [ ] Create `ValueFormatter` Protocol
- [ ] Create `TAVBuilder` class
- [ ] Implement `__init__(xml_builder: AnimationXMLBuilder)`
- [ ] Implement `resolve_key_times(values, key_times) -> list[float]`
- [ ] Implement `compute_tav_metadata(index, key_times, duration_ms, splines) -> dict`
- [ ] Implement `_segment_accel_decel(spline) -> tuple[int, int]`
- [ ] Implement `_format_spline(spline) -> str`
- [ ] Write unit tests for timing resolution
- [ ] Write unit tests for metadata computation

**Acceptance**:
- Keyframe timing correctly resolved
- Metadata computed accurately
- Tests pass: `pytest tests/unit/drawingml/animation/test_tav_builder.py::TestCore -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/tav_builder.py` (partial)
- `tests/unit/drawingml/animation/test_tav_builder.py` (partial)

---

### Task 2.3: Implement `tav_builder.py` - Part 2 (List Building)
**Est**: 2 hours
**Priority**: P0 - Blocker
**Dependencies**: 2.2

- [ ] Implement `build_tav_list(values, key_times, key_splines, duration_ms, value_formatter)`
- [ ] Return `(tav_elements, needs_custom_namespace)` tuple
- [ ] Handle spline metadata with svg2: namespace
- [ ] Add accel/decel to each TAV element
- [ ] Write unit tests for TAV list building
- [ ] Test with various keyframe counts (2, 3, 10)
- [ ] Test with and without splines

**Acceptance**:
- TAV lists built correctly
- Namespace handling works
- Tests pass: `pytest tests/unit/drawingml/animation/test_tav_builder.py::TestListBuilding -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/tav_builder.py` (complete)
- `tests/unit/drawingml/animation/test_tav_builder.py` (complete)

---

### Task 2.4: Implement Value Formatters
**Est**: 2 hours
**Priority**: P1
**Dependencies**: 2.3

- [ ] Implement `format_numeric_value(value, processor) -> etree._Element`
- [ ] Implement `format_color_value(value, processor) -> etree._Element`
- [ ] Implement `format_point_value(value, processor) -> etree._Element`
- [ ] Implement `format_angle_value(value, processor) -> etree._Element`
- [ ] Write unit tests for each formatter
- [ ] Test with edge cases

**Acceptance**:
- All formatters produce correct lxml elements
- Tests pass: `pytest tests/unit/drawingml/animation/test_value_formatters.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/value_formatters.py`
- `tests/unit/drawingml/animation/test_value_formatters.py`

---

## Phase 3: Animation Handlers (Est. 12-15 hours)

### Task 3.1: Implement Base Handler
**Est**: 1.5 hours
**Priority**: P0 - Blocker
**Dependencies**: 1.4, 1.3, 2.3

- [ ] Create `handlers/base.py`
- [ ] Implement `AnimationHandler` abstract base class
- [ ] Define `__init__(xml_builder, value_processor, tav_builder, unit_converter)`
- [ ] Define abstract `can_handle(animation) -> bool`
- [ ] Define abstract `build(animation, par_id, behavior_id) -> str`
- [ ] Add docstrings
- [ ] Write tests for base class utilities

**Acceptance**:
- Base handler can be subclassed
- Abstract methods enforced
- Tests pass: `pytest tests/unit/drawingml/animation/handlers/test_base.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/handlers/base.py`
- `tests/unit/drawingml/animation/handlers/test_base.py`

---

### Task 3.2: Implement Opacity Handler (Reference Implementation)
**Est**: 2.5 hours
**Priority**: P0 - Blocker
**Dependencies**: 3.1

- [ ] Create `handlers/opacity.py`
- [ ] Implement `OpacityAnimationHandler(AnimationHandler)`
- [ ] Implement `can_handle()` - check for fade attributes
- [ ] Implement `build()` - generate `<a:animEffect>` with `<a:fade>`
- [ ] Use `self._xml.build_par_container()`
- [ ] Use `self._xml.build_behavior_core()`
- [ ] Use `self._values.parse_opacity()`
- [ ] Write comprehensive unit tests
- [ ] **Comparison test**: Verify output matches old implementation

**Acceptance**:
- Opacity animations work correctly
- XML matches old implementation (modulo whitespace)
- Tests pass: `pytest tests/unit/drawingml/animation/handlers/test_opacity.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/handlers/opacity.py`
- `tests/unit/drawingml/animation/handlers/test_opacity.py`

---

### Task 3.3: Implement Color Handler
**Est**: 2.5 hours
**Priority**: P1
**Dependencies**: 3.1, 2.4

- [ ] Create `handlers/color.py`
- [ ] Implement `ColorAnimationHandler(AnimationHandler)`
- [ ] Implement `can_handle()` - check for color attributes
- [ ] Implement `build()` - generate `<a:animClr>`
- [ ] Build TAV list with `format_color_value` formatter
- [ ] Handle `from` and `to` color values
- [ ] Write unit tests
- [ ] Comparison test vs. old implementation

**Acceptance**:
- Color animations work correctly
- TAV lists with colors work
- Tests pass: `pytest tests/unit/drawingml/animation/handlers/test_color.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/handlers/color.py`
- `tests/unit/drawingml/animation/handlers/test_color.py`

---

### Task 3.4: Implement Numeric Handler
**Est**: 2.5 hours
**Priority**: P1
**Dependencies**: 3.1, 2.4

- [ ] Create `handlers/numeric.py`
- [ ] Implement `NumericAnimationHandler(AnimationHandler)`
- [ ] Implement `can_handle()` - catch-all for numeric attributes
- [ ] Implement `build()` - generate `<a:anim>`
- [ ] Build attribute name list
- [ ] Build TAV list with `format_numeric_value` formatter
- [ ] Handle unit conversion (px → EMU, degrees → 60000ths)
- [ ] Write unit tests
- [ ] Test various attributes (width, height, angle, etc.)
- [ ] Comparison test vs. old implementation

**Acceptance**:
- Numeric animations work correctly
- Unit conversions accurate
- Tests pass: `pytest tests/unit/drawingml/animation/handlers/test_numeric.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
- `tests/unit/drawingml/animation/handlers/test_numeric.py`

---

### Task 3.5: Implement Transform Handler - Part 1 (Scale)
**Est**: 2 hours
**Priority**: P1
**Dependencies**: 3.1, 2.4

- [ ] Create `handlers/transform.py`
- [ ] Implement `TransformAnimationHandler(AnimationHandler)`
- [ ] Implement `can_handle()` - check for ANIMATE_TRANSFORM type
- [ ] Implement `build()` - route to `_build_scale`, `_build_rotate`, or `_build_translate`
- [ ] Implement `_build_scale()` - generate `<a:animScale>`
- [ ] Build TAV list with `format_point_value` formatter for scale
- [ ] Parse scale pairs (single value or x,y)
- [ ] Write unit tests for scale animations
- [ ] Comparison test vs. old implementation

**Acceptance**:
- Scale animations work correctly
- Tests pass: `pytest tests/unit/drawingml/animation/handlers/test_transform.py::TestScale -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/handlers/transform.py` (partial)
- `tests/unit/drawingml/animation/handlers/test_transform.py` (partial)

---

### Task 3.6: Implement Transform Handler - Part 2 (Rotate)
**Est**: 1.5 hours
**Priority**: P1
**Dependencies**: 3.5

- [ ] Implement `_build_rotate()` - generate `<a:animRot>`
- [ ] Build TAV list with `format_angle_value` formatter
- [ ] Parse angle values
- [ ] Compute rotation delta in 60000ths
- [ ] Handle cumulative rotation (by attribute)
- [ ] Write unit tests for rotate animations
- [ ] Comparison test vs. old implementation

**Acceptance**:
- Rotate animations work correctly
- Tests pass: `pytest tests/unit/drawingml/animation/handlers/test_transform.py::TestRotate -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/handlers/transform.py` (partial)
- `tests/unit/drawingml/animation/handlers/test_transform.py` (partial)

---

### Task 3.7: Implement Transform Handler - Part 3 (Translate)
**Est**: 1.5 hours
**Priority**: P1
**Dependencies**: 3.6

- [ ] Implement `_build_translate()` - generate `<a:animMotion>`
- [ ] Parse translation pairs
- [ ] Compute dx, dy in EMU
- [ ] Build `<a:by>` element
- [ ] Write unit tests for translate animations
- [ ] Comparison test vs. old implementation

**Acceptance**:
- Translate animations work correctly
- Tests pass: `pytest tests/unit/drawingml/animation/handlers/test_transform.py::TestTranslate -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/handlers/transform.py` (complete)
- `tests/unit/drawingml/animation/handlers/test_transform.py` (complete)

---

### Task 3.8: Implement Motion Handler
**Est**: 2 hours
**Priority**: P1
**Dependencies**: 3.1

- [ ] Create `handlers/motion.py`
- [ ] Implement `MotionAnimationHandler(AnimationHandler)`
- [ ] Implement `can_handle()` - check for ANIMATE_MOTION type
- [ ] Implement `build()` - generate `<a:animMotion>` with `<a:ptLst>`
- [ ] Parse motion path (SVG path data)
- [ ] Sample Bezier curves into points
- [ ] Deduplicate consecutive points
- [ ] Convert points to EMU
- [ ] Write unit tests
- [ ] Test with straight lines and curves
- [ ] Comparison test vs. old implementation

**Acceptance**:
- Motion path animations work correctly
- Bezier sampling accurate
- Tests pass: `pytest tests/unit/drawingml/animation/handlers/test_motion.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/handlers/motion.py`
- `tests/unit/drawingml/animation/handlers/test_motion.py`

---

### Task 3.9: Implement Set Handler
**Est**: 1.5 hours
**Priority**: P1
**Dependencies**: 3.1

- [ ] Create `handlers/set_value.py`
- [ ] Implement `SetAnimationHandler(AnimationHandler)`
- [ ] Implement `can_handle()` - check for SET type
- [ ] Implement `build()` - generate `<a:set>`
- [ ] Handle both color and numeric set values
- [ ] Build `<a:to>` element
- [ ] Write unit tests
- [ ] Test color set and numeric set
- [ ] Comparison test vs. old implementation

**Acceptance**:
- Set animations work correctly
- Tests pass: `pytest tests/unit/drawingml/animation/handlers/test_set_value.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/handlers/set_value.py`
- `tests/unit/drawingml/animation/handlers/test_set_value.py`

---

## Phase 4: Main Writer Integration (Est. 4-6 hours)

### Task 4.1: Implement New Writer Class
**Est**: 3 hours
**Priority**: P0 - Blocker
**Dependencies**: 2.1, 3.2, 3.3, 3.4, 3.7, 3.8, 3.9

- [ ] Create new `writer.py`
- [ ] Implement `DrawingMLAnimationWriter.__init__()`
- [ ] Initialize all components (xml_builder, value_processor, tav_builder, etc.)
- [ ] Initialize handler registry
- [ ] Implement `build(animations, timeline, tracer, options) -> str`
- [ ] Implement `_find_handler(animation) -> AnimationHandler | None`
- [ ] Implement `_next_id() -> int`
- [ ] Implement `_allocate_ids() -> tuple[int, int]`
- [ ] Add tracer integration for all code paths
- [ ] Write unit tests for orchestration
- [ ] Test handler selection logic

**Acceptance**:
- Writer orchestrates all handlers correctly
- Tracer integration works
- Tests pass: `pytest tests/unit/drawingml/animation/test_writer.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation/writer.py`
- `tests/unit/drawingml/animation/test_writer.py`

---

### Task 4.2: Update Module Exports
**Est**: 30 min
**Priority**: P0 - Blocker
**Dependencies**: 4.1

- [ ] Update `src/svg2ooxml/drawingml/animation/__init__.py`
- [ ] Export `DrawingMLAnimationWriter`
- [ ] Export handler classes (if needed)
- [ ] Add `__all__` list
- [ ] Update docstring

**Acceptance**:
- Public API matches old module
- Import works: `from svg2ooxml.drawingml.animation import DrawingMLAnimationWriter`

**Files**:
- `src/svg2ooxml/drawingml/animation/__init__.py`

---

### Task 4.3: Side-by-Side Comparison Tests
**Est**: 2 hours
**Priority**: P0 - Blocker
**Dependencies**: 4.1

- [ ] Create comparison test suite
- [ ] Import both old and new `DrawingMLAnimationWriter`
- [ ] Run both on same animation definitions
- [ ] Compare XML output (normalized whitespace)
- [ ] Test all animation types
- [ ] Test edge cases
- [ ] Document any intentional differences

**Acceptance**:
- New implementation produces identical XML (modulo whitespace)
- All comparison tests pass
- Tests pass: `pytest tests/integration/animation/test_writer_comparison.py -v`

**Files**:
- `tests/integration/animation/test_writer_comparison.py`

---

## Phase 5: Migration & Cleanup (Est. 3-4 hours)

### Task 5.1: Update Import Paths
**Est**: 1 hour
**Priority**: P0 - Blocker
**Dependencies**: 4.3

- [ ] Find all imports of old `animation_writer`
- [ ] Update to `from svg2ooxml.drawingml.animation import DrawingMLAnimationWriter`
- [ ] Verify all imports work
- [ ] Run full test suite

**Acceptance**:
- All imports updated
- Tests pass: `pytest`

**Files**:
- Multiple files importing animation writer

---

### Task 5.2: Deprecate Old Implementation
**Est**: 30 min
**Priority**: P1
**Dependencies**: 5.1

- [ ] Rename `animation_writer.py` to `animation_writer_old.py`
- [ ] Add deprecation warning at top of file
- [ ] Update any remaining references
- [ ] Keep file for one release cycle

**Acceptance**:
- Old implementation marked deprecated
- No active usage of old implementation

**Files**:
- `src/svg2ooxml/drawingml/animation_writer_old.py`

---

### Task 5.3: Delete Old Implementation
**Est**: 15 min
**Priority**: P2
**Dependencies**: 5.2

- [ ] Delete `animation_writer_old.py`
- [ ] Remove any backup references
- [ ] Update CHANGELOG

**Acceptance**:
- Old file deleted
- Clean git history

**Files**:
- `src/svg2ooxml/drawingml/animation_writer_old.py` (deleted)

---

### Task 5.4: Update Documentation
**Est**: 1.5 hours
**Priority**: P1
**Dependencies**: 4.2

- [ ] Update module docstrings
- [ ] Update architecture docs
- [ ] Add migration guide (if needed)
- [ ] Update API reference
- [ ] Add examples for new architecture

**Acceptance**:
- Documentation accurate and complete
- Examples work

**Files**:
- `docs/architecture/animation-system.md`
- `README.md` (if needed)

---

### Task 5.5: Performance Benchmarks
**Est**: 1 hour
**Priority**: P2
**Dependencies**: 4.3

- [ ] Create benchmark script
- [ ] Benchmark old vs. new implementation
- [ ] Measure time for various animation counts (1, 10, 100)
- [ ] Measure memory usage
- [ ] Document results

**Acceptance**:
- New implementation ≤5% slower (likely faster)
- Benchmark results documented

**Files**:
- `benchmarks/animation_writer_benchmark.py`
- `docs/benchmarks/animation-writer-results.md`

---

## Phase 6: Final Validation (Est. 2-3 hours)

### Task 6.1: Full Integration Tests
**Est**: 1.5 hours
**Priority**: P0 - Blocker
**Dependencies**: 5.1

- [ ] Run full test suite: `pytest`
- [ ] Run integration tests specifically
- [ ] Test with real SVG files containing animations
- [ ] Verify PowerPoint can open generated files
- [ ] Test all animation types in PowerPoint

**Acceptance**:
- All tests pass
- Generated PowerPoint files work correctly
- Animations play as expected

---

### Task 6.2: Code Coverage Check
**Est**: 30 min
**Priority**: P1
**Dependencies**: 6.1

- [ ] Run coverage: `pytest --cov=src/svg2ooxml/drawingml/animation --cov-report=html`
- [ ] Verify >90% coverage for all new modules
- [ ] Add tests for uncovered lines
- [ ] Document any intentional exclusions

**Acceptance**:
- Coverage >90% for all new modules
- Coverage report clean

---

### Task 6.3: Code Review & QA
**Est**: 1 hour
**Priority**: P0 - Blocker
**Dependencies**: 6.2

- [ ] Self-review all code
- [ ] Check for TODO/FIXME comments
- [ ] Verify docstrings complete
- [ ] Verify type hints complete
- [ ] Run linters (mypy, pylint, black)
- [ ] Fix any issues

**Acceptance**:
- Code review complete
- All linters pass
- No outstanding issues

---

## Summary

**Total Estimated Time**: 35-46 hours (4.5-6 days)
**Updated**: Reduced by 2 hours due to leveraging existing `common.conversions` module!

**Critical Path**:
1. Phase 1 (Foundation) → Phase 2 (Core) → Phase 3 (Handlers) → Phase 4 (Integration) → Phase 5 (Migration) → Phase 6 (Validation)

**Parallel Opportunities**:
- Tasks 3.2-3.9 (handlers) can be partially parallelized
- Documentation (5.4) can happen alongside implementation
- Benchmarks (5.5) can happen independently after 4.3

**Key Milestones**:
- ✅ M1: Foundation complete (after Task 1.4)
- ✅ M2: Core components complete (after Task 2.4)
- ✅ M3: All handlers implemented (after Task 3.9)
- ✅ M4: Integration complete (after Task 4.3)
- ✅ M5: Migration complete (after Task 5.3)
- ✅ M6: Final validation (after Task 6.3)

**Risk Mitigation**:
- Start with reference implementation (opacity handler - Task 3.2)
- Comparison tests throughout (catch regressions early)
- Keep old implementation until full validation

**Success Criteria**:
- ✅ Zero XML string concatenations
- ✅ All tests pass
- ✅ XML output identical to old implementation
- ✅ >90% test coverage
- ✅ Performance ≤5% slower (likely faster)
- ✅ Code review approved
