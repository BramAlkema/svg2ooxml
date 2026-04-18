# Centralized Conversions - Implementation Tasks

**Spec**: `docs/specs/centralized-conversions-spec.md`

**Goal**: Create unified conversion utilities for colors, units, angles, transforms, and PowerPoint-specific conversions.

**Priority**: P0 - Required before animation writer refactoring

---

## Phase 1: Module Structure & Foundation (Est. 1 hour)

### Task 1.1: Create Module Directory Structure
**Est**: 15 min
**Priority**: P0 - Blocker

- [ ] Create `src/svg2ooxml/common/conversions/` directory
- [ ] Create `src/svg2ooxml/common/conversions/__init__.py`
- [ ] Create placeholder files for all submodules
- [ ] Verify import path works

**Acceptance**:
- Directory structure exists
- Can import: `from svg2ooxml.common.conversions import ...`

**Files**:
- `src/svg2ooxml/common/conversions/__init__.py`
- `src/svg2ooxml/common/conversions/units.py`
- `src/svg2ooxml/common/conversions/colors.py`
- `src/svg2ooxml/common/conversions/angles.py`
- `src/svg2ooxml/common/conversions/opacity.py`
- `src/svg2ooxml/common/conversions/transforms.py`
- `src/svg2ooxml/common/conversions/powerpoint.py`

---

### Task 1.2: Implement `units.py` - Re-export Wrapper
**Est**: 15 min
**Priority**: P0 - Blocker
**Dependencies**: 1.1

- [ ] Create `units.py` with re-exports from `common.units`
- [ ] Re-export `UnitConverter`, `px_to_emu`, `emu_to_px`, `emu_to_unit`
- [ ] Re-export constants: `DEFAULT_DPI`, `EMU_PER_INCH`, etc.
- [ ] Add docstring explaining this is a convenience wrapper
- [ ] Write import test

**Acceptance**:
- All unit utilities accessible via `conversions.units`
- No functionality changes, pure re-export
- Test passes: `pytest tests/unit/common/conversions/test_units.py -v`

**Files**:
- `src/svg2ooxml/common/conversions/units.py`
- `tests/unit/common/conversions/test_units.py`

---

### Task 1.3: Implement `colors.py` - Color Utilities
**Est**: 30 min
**Priority**: P0 - Blocker
**Dependencies**: 1.1

- [ ] Re-export `color_to_hex` from `svg2ooxml.color.utils`
- [ ] Re-export `parse_color` from `svg2ooxml.color.parsers`
- [ ] Implement `hex_to_rgb(hex_value: str) -> tuple[int, int, int]`
- [ ] Implement `rgb_to_hex(r: int, g: int, b: int) -> str`
- [ ] Add comprehensive docstrings with examples
- [ ] Write unit tests for new functions
- [ ] Test edge cases (invalid hex, out-of-range RGB)

**Acceptance**:
- All color utilities work correctly
- Hex conversion roundtrips correctly
- Tests pass: `pytest tests/unit/common/conversions/test_colors.py -v`

**Files**:
- `src/svg2ooxml/common/conversions/colors.py`
- `tests/unit/common/conversions/test_colors.py`

---

## Phase 2: PowerPoint-Specific Conversions (Est. 2-3 hours)

### Task 2.1: Implement `angles.py` - Angle Conversions
**Est**: 45 min
**Priority**: P0 - Blocker
**Dependencies**: 1.1

- [ ] Define `PPT_ANGLE_SCALE = 60000` constant
- [ ] Implement `degrees_to_ppt(degrees: float) -> int`
- [ ] Implement `radians_to_ppt(radians: float) -> int`
- [ ] Implement `ppt_to_degrees(ppt_value: int) -> float`
- [ ] Implement `ppt_to_radians(ppt_value: int) -> float`
- [ ] Add comprehensive docstrings with examples
- [ ] Write unit tests for all functions
- [ ] Test common angles: 0°, 45°, 90°, 180°, 360°
- [ ] Test roundtrip conversions
- [ ] Test negative angles

**Acceptance**:
- All angle conversions work correctly
- Roundtrip conversion accurate within floating point tolerance
- Common angles convert correctly
- Tests pass: `pytest tests/unit/common/conversions/test_angles.py -v`

**Files**:
- `src/svg2ooxml/common/conversions/angles.py`
- `tests/unit/common/conversions/test_angles.py`

**Key Tests**:
```python
def test_degrees_to_ppt():
    assert degrees_to_ppt(0.0) == 0
    assert degrees_to_ppt(45.0) == 2700000
    assert degrees_to_ppt(90.0) == 5400000
    assert degrees_to_ppt(180.0) == 10800000
    assert degrees_to_ppt(360.0) == 21600000

def test_angle_roundtrip():
    for degrees in [0, 45, 90, 135, 180, 225, 270, 315, 360]:
        ppt = degrees_to_ppt(degrees)
        result = ppt_to_degrees(ppt)
        assert abs(result - degrees) < 0.001
```

---

### Task 2.2: Implement `opacity.py` - Opacity/Alpha Conversions
**Est**: 45 min
**Priority**: P0 - Blocker
**Dependencies**: 1.1

- [ ] Define `PPT_OPACITY_SCALE = 100000` constant
- [ ] Implement `opacity_to_ppt(opacity: float) -> int`
- [ ] Implement `ppt_to_opacity(ppt_value: int) -> float`
- [ ] Implement `alpha_to_ppt(alpha: float) -> int` (alias)
- [ ] Implement `ppt_to_alpha(ppt_value: int) -> float` (alias)
- [ ] Implement `percentage_to_ppt(percentage: float) -> int`
- [ ] Implement `ppt_to_percentage(ppt_value: int) -> float`
- [ ] Add value clamping (0.0-1.0 for opacity)
- [ ] Add comprehensive docstrings with examples
- [ ] Write unit tests for all functions
- [ ] Test edge cases: 0%, 50%, 100%
- [ ] Test clamping behavior
- [ ] Test roundtrip conversions

**Acceptance**:
- All opacity conversions work correctly
- Values properly clamped to valid ranges
- Roundtrip conversion accurate
- Tests pass: `pytest tests/unit/common/conversions/test_opacity.py -v`

**Files**:
- `src/svg2ooxml/common/conversions/opacity.py`
- `tests/unit/common/conversions/test_opacity.py`

**Key Tests**:
```python
def test_opacity_to_ppt():
    assert opacity_to_ppt(1.0) == 100000  # Fully opaque
    assert opacity_to_ppt(0.5) == 50000   # 50% opaque
    assert opacity_to_ppt(0.0) == 0       # Fully transparent

def test_opacity_clamping():
    assert opacity_to_ppt(1.5) == 100000  # Clamp to 1.0
    assert opacity_to_ppt(-0.5) == 0      # Clamp to 0.0

def test_opacity_roundtrip():
    for opacity in [0.0, 0.25, 0.5, 0.75, 1.0]:
        ppt = opacity_to_ppt(opacity)
        result = ppt_to_opacity(ppt)
        assert abs(result - opacity) < 0.00001
```

---

### Task 2.3: Implement `transforms.py` - Transform Parsing
**Est**: 1 hour
**Priority**: P0 - Blocker
**Dependencies**: 1.1

- [ ] Implement `parse_numeric_list(value: str) -> list[float]`
  - Support space-separated: "1.5 2.0 3.5"
  - Support comma-separated: "1.5, 2.0, 3.5"
  - Support mixed: "1.5,2.0 3.5"
  - Support scientific notation: "1.5e-3"
- [ ] Implement `parse_scale_pair(value: str) -> tuple[float, float]`
  - Single value: "1.5" → (1.5, 1.5)
  - Pair: "1.5 2.0" → (1.5, 2.0)
  - Empty: "" → (1.0, 1.0)
- [ ] Implement `parse_translation_pair(value: str) -> tuple[float, float]`
  - Pair: "10 20" → (10.0, 20.0)
  - Single: "10" → (10.0, 0.0)
  - Empty: "" → (0.0, 0.0)
- [ ] Implement `parse_angle(value: str) -> float`
  - Number: "45" → 45.0
  - With unit: "45deg" → 45.0
  - Empty: "" → 0.0
- [ ] Add comprehensive docstrings with examples
- [ ] Write unit tests for all functions
- [ ] Test edge cases (empty strings, malformed input)
- [ ] Test various formats

**Acceptance**:
- All parsing functions work correctly
- Handle various input formats gracefully
- Return sensible defaults for empty/invalid input
- Tests pass: `pytest tests/unit/common/conversions/test_transforms.py -v`

**Files**:
- `src/svg2ooxml/common/conversions/transforms.py`
- `tests/unit/common/conversions/test_transforms.py`

**Key Tests**:
```python
def test_parse_numeric_list():
    assert parse_numeric_list("1.5 2.0 3.5") == [1.5, 2.0, 3.5]
    assert parse_numeric_list("1.5, 2.0, 3.5") == [1.5, 2.0, 3.5]
    assert parse_numeric_list("1.5e-3") == [0.0015]
    assert parse_numeric_list("") == []

def test_parse_scale_pair():
    assert parse_scale_pair("1.5") == (1.5, 1.5)
    assert parse_scale_pair("1.5 2.0") == (1.5, 2.0)
    assert parse_scale_pair("") == (1.0, 1.0)

def test_parse_translation_pair():
    assert parse_translation_pair("10 20") == (10.0, 20.0)
    assert parse_translation_pair("10") == (10.0, 0.0)
    assert parse_translation_pair("") == (0.0, 0.0)
```

---

### Task 2.4: Implement `powerpoint.py` - Unified Converter
**Est**: 45 min
**Priority**: P1
**Dependencies**: 1.2, 1.3, 2.1, 2.2, 2.3

- [ ] Create `PPTConverter` class
- [ ] Implement `__init__(dpi: float = DEFAULT_DPI)`
- [ ] Implement unit conversion methods:
  - `px_to_emu(px: float, axis: str | None) -> int`
  - `length_to_emu(value: str | float, axis: str | None) -> int`
- [ ] Implement color conversion methods:
  - `color_to_hex(color: str | None, default: str) -> str`
- [ ] Implement angle conversion methods:
  - `degrees_to_ppt(degrees: float) -> int`
  - `radians_to_ppt(radians: float) -> int`
- [ ] Implement opacity conversion methods:
  - `opacity_to_ppt(opacity: float) -> int`
- [ ] Implement transform parsing methods:
  - `parse_scale(value: str) -> tuple[float, float]`
  - `parse_translation(value: str) -> tuple[float, float]`
  - `parse_angle(value: str) -> float`
- [ ] Add comprehensive docstrings
- [ ] Write unit tests for PPTConverter
- [ ] Test all methods work correctly

**Acceptance**:
- PPTConverter provides unified interface
- All conversion methods work
- Tests pass: `pytest tests/unit/common/conversions/test_powerpoint.py -v`

**Files**:
- `src/svg2ooxml/common/conversions/powerpoint.py`
- `tests/unit/common/conversions/test_powerpoint.py`

---

## Phase 3: Module Integration (Est. 1 hour)

### Task 3.1: Complete `__init__.py` - Public API
**Est**: 30 min
**Priority**: P0 - Blocker
**Dependencies**: 1.2, 1.3, 2.1, 2.2, 2.3, 2.4

- [ ] Import all public symbols from submodules
- [ ] Create comprehensive `__all__` list
- [ ] Add module-level docstring with usage examples
- [ ] Verify all imports work
- [ ] Test importing individual functions
- [ ] Test importing everything via wildcard

**Acceptance**:
- All public API accessible from `conversions` module
- Imports work: `from svg2ooxml.common.conversions import degrees_to_ppt`
- Tests pass: `pytest tests/unit/common/conversions/test_init.py -v`

**Files**:
- `src/svg2ooxml/common/conversions/__init__.py` (complete)
- `tests/unit/common/conversions/test_init.py`

---

### Task 3.2: Integration Tests
**Est**: 30 min
**Priority**: P1
**Dependencies**: 3.1

- [ ] Create integration test suite
- [ ] Test PPTConverter with real-world values
- [ ] Test conversion roundtrips across modules
- [ ] Test angle → EMU → back conversions
- [ ] Test opacity → PPT → back conversions
- [ ] Test color conversions with various formats
- [ ] Document expected precision/tolerances

**Acceptance**:
- All integration tests pass
- Roundtrip conversions accurate
- Tests pass: `pytest tests/integration/test_conversions.py -v`

**Files**:
- `tests/integration/test_conversions.py`

---

## Phase 4: Migration & Cleanup (Est. 2-3 hours)

### Task 4.1: Update `animation_writer.py` to Use New Conversions
**Est**: 1 hour
**Priority**: P1
**Dependencies**: 3.1

- [ ] Import new conversion utilities
- [ ] Replace `* 60000` with `degrees_to_ppt()`
- [ ] Replace `* 100000` with `opacity_to_ppt()`
- [ ] Replace `_parse_numeric_list()` with `parse_numeric_list()`
- [ ] Replace `_parse_scale_pair()` with `parse_scale_pair()`
- [ ] Replace `_parse_translation_pair()` with `parse_translation_pair()`
- [ ] Replace `_parse_angle()` with `parse_angle()`
- [ ] Replace `_to_hex_color()` with `color_to_hex()`
- [ ] Remove duplicate local implementations
- [ ] Run animation tests to verify no regressions

**Acceptance**:
- animation_writer.py uses centralized conversions
- No duplicate conversion code
- All tests still pass
- Tests pass: `pytest tests/unit/drawingml/test_animation_writer.py -v`

**Files**:
- `src/svg2ooxml/drawingml/animation_writer.py` (updated)

---

### Task 4.2: Update Other Files Using Scattered Conversions
**Est**: 1-2 hours
**Priority**: P2
**Dependencies**: 3.1

- [ ] Find all files with `* 60000` (angle conversions)
- [ ] Find all files with `* 100000` (opacity conversions)
- [ ] Find all files with custom color_to_hex implementations
- [ ] Update imports to use centralized conversions
- [ ] Remove duplicate implementations
- [ ] Run affected tests

**Files to Check**:
- `src/svg2ooxml/services/gradient_service.py`
- `src/svg2ooxml/drawingml/filter_renderer.py`
- `src/svg2ooxml/drawingml/paint_runtime.py`
- `src/svg2ooxml/filters/primitives/*.py`
- Others identified by grep

**Acceptance**:
- All files use centralized conversions
- No more magic numbers
- All tests still pass

---

### Task 4.3: Documentation & Examples
**Est**: 30 min
**Priority**: P2
**Dependencies**: 3.1

- [ ] Update architecture documentation
- [ ] Add usage examples to module docstrings
- [ ] Create migration guide (if needed)
- [ ] Update CHANGELOG
- [ ] Add "Conversions" section to docs

**Acceptance**:
- Documentation complete and accurate
- Examples work and are helpful

**Files**:
- `docs/internals/conversions.md` (new)
- `CHANGELOG.md`
- Module docstrings

---

## Phase 5: Final Validation (Est. 30 min)

### Task 5.1: Full Test Suite Validation
**Est**: 15 min
**Priority**: P0 - Blocker
**Dependencies**: 4.2

- [ ] Run full test suite: `pytest`
- [ ] Verify no regressions
- [ ] Check test coverage for new modules: >95%
- [ ] Run type checking: `mypy src/svg2ooxml/common/conversions/`

**Acceptance**:
- All tests pass
- Coverage >95% for conversions module
- No mypy errors

---

### Task 5.2: Code Review & Cleanup
**Est**: 15 min
**Priority**: P1
**Dependencies**: 5.1

- [ ] Self-review all code
- [ ] Check for TODO/FIXME comments
- [ ] Verify docstrings complete
- [ ] Verify type hints complete
- [ ] Run linters (black, pylint)
- [ ] Fix any issues

**Acceptance**:
- Code review complete
- All linters pass
- No outstanding issues

---

## Summary

**Total Estimated Time**: 6-8 hours

**Phases**:
1. **Phase 1**: Module structure & foundation (1 hour)
2. **Phase 2**: PowerPoint-specific conversions (2-3 hours)
3. **Phase 3**: Module integration (1 hour)
4. **Phase 4**: Migration & cleanup (2-3 hours)
5. **Phase 5**: Final validation (30 min)

**Critical Path**:
1.1 → 1.2, 1.3 → 2.1, 2.2, 2.3 → 2.4 → 3.1 → 3.2 → 4.1 → 4.2 → 4.3 → 5.1 → 5.2

**Parallel Opportunities**:
- Tasks 2.1, 2.2, 2.3 (angles, opacity, transforms) can be done in parallel
- Task 4.3 (documentation) can happen alongside 4.1-4.2

**Key Milestones**:
- ✅ M1: Module structure complete (after 1.3)
- ✅ M2: All conversions implemented (after 2.4)
- ✅ M3: Public API complete (after 3.1)
- ✅ M4: animation_writer.py migrated (after 4.1)
- ✅ M5: All files migrated (after 4.2)
- ✅ M6: Validation complete (after 5.2)

**Success Criteria**:
- ✅ Zero magic numbers (60000, 100000) in consuming code
- ✅ All conversion logic centralized
- ✅ >95% test coverage
- ✅ All existing tests pass
- ✅ Clean, documented public API
- ✅ Ready for animation writer refactoring

**Deliverables**:
- New module: `src/svg2ooxml/common/conversions/`
- 7 new source files
- 8+ new test files
- Updated documentation
- Migration of animation_writer.py and other consumers
