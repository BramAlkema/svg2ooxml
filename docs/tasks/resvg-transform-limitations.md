# Resvg Transform Implementation - Known Limitations & Follow-ups

This document tracks limitations in the current transform implementation for Task 2.4 (Wire Resvg Adapters into DrawingML Writers).

## Status: ✅ Basic transform support implemented, ⚠️  with known limitations

## Critical Limitations

### 1. Radial Gradient Non-Uniform Transforms (MEDIUM PRIORITY)

**Problem**: The current radial gradient transform implementation samples a single point at `(cx + r, cy)` to compute the transformed radius. This works correctly for:
- ✅ Translation
- ✅ Uniform scale
- ✅ Rotation (radius unchanged)

But **fails** for:
- ❌ Non-uniform scale (e.g., scale(2, 3) turns circle into ellipse)
- ❌ Skew (shears circle into ellipse)

**Code Location**: `src/svg2ooxml/drawingml/bridges/resvg_gradient_adapter.py:149-159`

```python
# Current implementation (INCORRECT for non-uniform transforms):
if gradient.transform is not None:
    edge_point = _apply_matrix_to_point(gradient.cx + gradient.r, gradient.cy, gradient.transform)
    dx = edge_point[0] - center[0]
    dy = edge_point[1] - center[1]
    radius = math.sqrt(dx * dx + dy * dy)  # Single radius value!
```

**Why This Fails**: When a transform contains non-uniform scale or skew, the original circle becomes an ellipse. DrawingML radial gradients still expect a **single radius** (circle), so we render the wrong footprint.

**Example Failure Case**:
```python
# Original: circle at (50, 50) with radius 20
# Transform: scale(2, 1) - 2x horizontal, 1x vertical
# Result: ellipse with rx=40, ry=20
# Our code: renders as circle with radius=sqrt(40^2 + 0^2) = 40
# Actual shape: should be ellipse, but DrawingML can't represent it!
```

**Detection Strategy**:
```python
def _is_non_uniform_transform(matrix) -> bool:
    """Check if transform has non-uniform scale or skew."""
    # For a transform to preserve circles, it must be:
    # - Translation only (a=d=1, b=c=0), OR
    # - Uniform scale + rotation (a=d*cos(θ), b=-c=d*sin(θ), |a|=|d|, |b|=|c|)

    # Simple check: if x-scale != y-scale, it's non-uniform
    x_scale = math.sqrt(matrix.a * matrix.a + matrix.b * matrix.b)
    y_scale = math.sqrt(matrix.c * matrix.c + matrix.d * matrix.d)
    return abs(x_scale - y_scale) > 1e-6  # Non-uniform if scales differ
```

**Proposed Solutions**:

**RECOMMENDED SOLUTION: Robust SVD-based Detection + Two-Tier Policy**

This approach uses singular value decomposition to properly classify transforms and applies intelligent fallback strategies:

### Mathematical Foundation: Singular Value Classification

Use SVD-like analysis to extract scale factors and detect shear/non-uniformity:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class TransformClass:
    """Classification of a 2D affine transform's linear part."""
    non_uniform: bool      # True if x-scale != y-scale
    has_shear: bool        # True if transform has shear/skew
    det_sign: int          # -1 (reflection), 0 (degenerate), +1 (normal)
    s1: float              # Larger singular value (max stretch)
    s2: float              # Smaller singular value (min stretch)
    ratio: float           # s1/s2 (anisotropy ratio)

def classify_linear(a, b, c, d, eps=1e-6) -> TransformClass:
    """Classify 2D linear transform using singular value analysis.

    Given matrix [[a, c], [b, d]], compute:
    - Singular values s1, s2 (principal stretch factors)
    - Anisotropy ratio (how much it deviates from uniform scale)
    - Shear detection (does it skew?)
    - Determinant sign (reflection detection)

    Math: For 2×2 matrix J = [[a, c], [b, d]], singular values are:
    λ± = √((A+C ± √((A+C)² - 4det²)) / 2)
    where A = a²+b², B = ac+bd, C = c²+d²
    """
    # Compute eigenvalues of J^T J (squared singular values)
    A = a*a + b*b
    B = a*c + b*d
    C = c*c + d*d
    trace = A + C
    detJ = a*d - b*c
    disc_sq = max(trace*trace - 4.0*(detJ*detJ), 0.0)
    sqrt_disc = disc_sq**0.5

    # Eigenvalues of J^T J
    lam_plus = 0.5*(trace + sqrt_disc)
    lam_minus = 0.5*(trace - sqrt_disc)

    # Singular values (square roots of eigenvalues)
    s1 = lam_plus**0.5 if lam_plus > 0 else 0.0
    s2 = lam_minus**0.5 if lam_minus > 0 else 0.0

    # Anisotropy ratio (avoid division by zero)
    ratio = max(s1, s2) / max(min(s1, s2), eps)

    # Shear detection: B (off-diagonal correlation) should be ~0 for pure scale+rotation
    has_shear = abs(B) > eps * (A + C + 1.0)

    # Determinant sign (reflection detection)
    det_sign = -1 if detJ < -eps else (1 if detJ > eps else 0)

    # Non-uniform if singular values differ significantly
    non_uniform = abs(s1 - s2) > eps * max(s1, s2, 1.0)

    return TransformClass(non_uniform, has_shear, det_sign, s1, s2, ratio)
```

### Two-Tier Fallback Policy

```python
def decide_radial_policy(a, b, c, d, mild_ratio=1.02):
    """Decide how to handle a radial gradient transform.

    Returns:
        tuple[str, TransformClass]: ("policy_name", classification)

    Policies:
        - "vector_ok": Uniform scale/rotation, render as circle
        - "vector_warn_mild_anisotropy": Slightly non-uniform (ratio ≤ 1.02),
          render as circle but emit warning in telemetry
        - "rasterize_nonuniform": Significant non-uniformity or shear,
          fall back to rasterized gradient texture
    """
    cls = classify_linear(a, b, c, d)

    # Tier 0: Uniform scale + rotation → perfect circle
    if not cls.non_uniform:
        return "vector_ok", cls

    # Tier 1: Mild anisotropy, no shear → acceptable approximation
    if cls.ratio <= mild_ratio and not cls.has_shear:
        return "vector_warn_mild_anisotropy", cls

    # Tier 2: Significant non-uniformity or shear → rasterize
    return "rasterize_nonuniform", cls
```

### Implementation Plan

**Phase 1: Detection & Telemetry** (HIGH PRIORITY)
1. Add `classify_linear()` and `decide_radial_policy()` to adapter
2. Extend IR paint objects with new fields:
   ```python
   @dataclass
   class RadialGradientPaint:
       # ... existing fields ...
       gradient_transform: Matrix | None = None      # Original gradient transform
       original_transform: Matrix | None = None      # Shape transform (for telemetry)
       had_transform_flag: bool = False              # Was any transform applied?
       transform_class: TransformClass | None = None # SVD classification
       policy_decision: str | None = None            # "vector_ok" / "vector_warn_mild_anisotropy" / "rasterize_nonuniform"
   ```
3. Update adapter to populate these fields
4. Update telemetry to log transform_class and policy_decision

**Phase 2: Vector Warning Path** (MEDIUM PRIORITY)
1. For "vector_warn_mild_anisotropy" policy:
   - Render as circle using current logic
   - Add telemetry warning with ratio and singular values
   - Log in trace output for debugging

**Phase 3: Rasterization Fallback** (MEDIUM PRIORITY)
1. For "rasterize_nonuniform" policy:
   - Generate gradient texture as bitmap
   - Size calculation: `px = ceil(max(s1, s2) * oversample)` with clamps (64–4096)
   - Embed as pattern in DrawingML
   - Log raster_size in telemetry

**Phase 4: Units & Spread** (LOW PRIORITY)
1. Add `gradient_units` and `spread_method` to IR
2. Verify resvg normalizes objectBoundingBox before adapter
3. Update paint_runtime to handle spread methods (may need rasterization)

---

**Alternative Options (NOT RECOMMENDED)**:

**Option A: Keep matrix, let paint_runtime detect**
- Store original transform in IR alongside baked coordinates
- Add `transformed_from_circle: bool` flag to RadialGradientPaint
- paint_runtime can detect non-uniform case and fall back to bitmap/pattern
- **Con**: Moves complexity to paint_runtime, duplicates transform logic

**Option B: Simple detect and fall back in adapter**
- In `radial_gradient_to_paint()`, detect non-uniform transforms
- Return a fallback paint type (bitmap, pattern, or solid color average)
- **Con**: Loses gradient information entirely, no nuance for mild anisotropy

**Option C: Use ellipse approximation** (FUTURE)
- DrawingML doesn't natively support elliptical gradients
- Could approximate with a pattern or multiple overlapping gradients
- **Con**: Complex, low-priority, may not look correct

**Action Items (Phased Implementation)**:

**Phase 1: Detection & Telemetry** (✅ COMPLETE - 2025-01-04)
- [x] Implement `classify_linear()` helper in gradient adapter
- [x] Implement `decide_radial_policy()` helper
- [x] Extend `RadialGradientPaint` dataclass with new fields:
  - `gradient_transform: Matrix | None`
  - `original_transform: Matrix | None`
  - `had_transform_flag: bool`
  - `transform_class: TransformClass | None`
  - `policy_decision: str | None`
- [x] Update `radial_gradient_to_paint()` to classify transform and populate fields
- [x] Add tests for transform classification (21 tests, all passing)
- Commit: ad929cb

**Phase 2: Vector Warning Path** (✅ COMPLETE - 2025-01-04)
- [x] For "vector_warn_mild_anisotropy" gradients:
  - Keep current circle rendering ✅
  - Add telemetry warning with ratio/singular values ✅
  - Add trace logging for debugging ✅
- [x] Extend telemetry serialization to include transform_class ✅
- [x] Add debug logging for mild anisotropy (ratio ≤ 1.02) ✅
- [x] Add info logging for severe non-uniformity/shear ✅
- [x] Add comprehensive telemetry tests (8 tests, all passing) ✅
- [x] Document acceptable anisotropy threshold (1.02) ✅

**Phase 3: Rasterization Fallback** (✅ COMPLETE - 2025-01-04)
- [x] Implement `_calculate_raster_size()` helper with clamping (64–4096 px) ✅
- [x] Implement solid color fallback for "rasterize_nonuniform" policy ✅
  - Compute average color from gradient stops ✅
  - Return SolidPaint instead of malformed RadialGradientPaint ✅
  - Log raster_size in telemetry (for future full bitmap implementation) ✅
- [x] Add comprehensive Phase 3 tests (21 tests, all passing) ✅
  - Test size calculation with various inputs and clamping ✅
  - Test solid color fallback for severe non-uniform/skew ✅
  - Test logging includes raster size and solid color mention ✅
- [x] Update Phase 1 & 2 tests to expect SolidPaint for severe cases ✅
- Notes:
  - Pragmatic approach: Solid color fallback is simpler and acceptable for initial implementation
  - Full bitmap gradient rasterization can be added later if needed (TODO in code)
  - Size calculation is in place for when full rasterization is implemented

**Phase 4: Units & Spread** (LOW PRIORITY)
- [ ] Add `gradient_units` and `spread_method` fields to IR
- [ ] Test resvg normalization of objectBoundingBox
- [ ] Document spread method limitations
- [ ] Consider rasterization for reflect/repeat spread

---

### 2. Gradient Units & Spread (LOW PRIORITY)

**Problem**: Current adapter strips two important gradient properties:

**a) Gradient Units (objectBoundingBox vs userSpaceOnUse)**
- SVG gradients can use `gradientUnits="objectBoundingBox"` (values in 0-1 range, relative to shape bbox)
- Or `gradientUnits="userSpaceOnUse"` (absolute coordinates in user space)
- **Current behavior**: Adapter assumes all coordinates are already in correct space
- **Risk**: If resvg passes objectBoundingBox coords without scaling, we'll render tiny gradients!

**b) Spread Method (pad/reflect/repeat)**
- SVG supports `spreadMethod="pad|reflect|repeat"` for gradients
- **Current behavior**: IR doesn't have a spread field, so paint_runtime always uses "pad"
- **Risk**: Reflected/repeated gradients will render incorrectly

**Code Location**: `src/svg2ooxml/drawingml/bridges/resvg_gradient_adapter.py:48-54, 115-120`

**Current Warnings**:
```python
# From linear_gradient_to_paint docstring:
# - **Units**: objectBoundingBox vs userSpaceOnUse NOT recorded. If gradient uses
#   objectBoundingBox units (values in 0-1 range), caller MUST scale coordinates before
#   passing to paint_runtime, which assumes user-space pixels.
# - **Spread method**: Not preserved in IR (pad/reflect/repeat). IR doesn't have this field,
#   so paint_runtime will always use pad behavior. This is a DrawingML limitation.
```

**Action Items**:
- [ ] Verify resvg normalizes objectBoundingBox to userSpace before adapter
- [ ] If not, add `gradient_units` field to IR paint objects
- [ ] Add `spread_method` field to IR paint objects
- [ ] Update paint_runtime to handle spread methods (may need bitmap fallback)
- [ ] Document DrawingML limitations for reflect/repeat

---

### 3. Transform=None Side Effects (LOW PRIORITY)

**Problem**: After applying transforms, we set `transform=None` on returned paint/segments. This breaks:

**a) Telemetry/Tracing**
- `TraversalHooksMixin._serialize_paint()` calls `_serialize_matrix(paint.transform)`
- With `transform=None`, telemetry shows `"transform": null`
- **Lost information**: Can't tell if gradient/shape originally HAD a transform (now baked)

**Code Location**:
- `src/svg2ooxml/core/traversal/hooks.py:528, 541, 548, 558` - telemetry serialization
- `src/svg2ooxml/core/styling/style_extractor.py:549, 564` - paint cloning

**Current Behavior**:
```python
# Adapter code:
return LinearGradientPaint(
    stops=ir_stops,
    start=start,  # Already transformed
    end=end,      # Already transformed
    transform=None,  # ⚠️  Original matrix discarded!
    gradient_id=grad_id,
)

# Telemetry code:
def _serialize_paint(self, paint):
    return {
        "type": "linearGradient",
        "transform": self._serialize_matrix(paint.transform),  # Returns None
        # ...
    }
```

**Why This Matters**:
- Telemetry can't distinguish "no transform" from "transform was baked"
- Can't track "percentage of gradients with transforms" metric
- Can't detect "which transforms are being used" for optimization

**Proposed Solutions**:

**Option A: Add `had_transform` flag** (RECOMMENDED)
```python
@dataclass
class LinearGradientPaint:
    stops: list[GradientStop]
    start: tuple[float, float]
    end: tuple[float, float]
    transform: Any | None = None  # Kept for backward compat
    original_transform: Any | None = None  # NEW: Original matrix before baking
    gradient_id: str | None = None
```

**Option B: Keep original matrix alongside baked coords**
- Set `transform=original_matrix` even after baking
- Add `coordinates_are_transformed: bool = True` flag
- paint_runtime checks flag and skips re-applying transform
- Pro: Telemetry gets full transform info
- Con: Confusing API ("transform is present but already applied?")

**Action Items**:
- [ ] Add `original_transform` field to IR paint objects
- [ ] Update adapters to populate both `transform=None` and `original_transform=matrix`
- [ ] Update telemetry to serialize `original_transform` if present
- [ ] Add test coverage for telemetry with transformed gradients

---

## Follow-up Tasks (Checklist Updates)

These should be added to `docs/tasks/resvg-task-2.4-checklist.md`:

### High Priority
- [ ] **Detect non-uniform radial gradient transforms**
  - Implement `_is_non_uniform_transform()` helper
  - Add telemetry flag when detected
  - Document fallback strategy (bitmap or solid color)

### Medium Priority
- [ ] **Preserve original transform for telemetry**
  - Add `original_transform` field to IR paint classes
  - Update adapters to populate it
  - Update telemetry serialization

### Low Priority
- [ ] **Verify gradient units handling**
  - Test if resvg normalizes objectBoundingBox before adapter
  - Add IR field if needed
  - Document caller responsibilities

- [ ] **Document spread method limitations**
  - Confirm DrawingML only supports "pad"
  - Add IR field for future bitmap fallback
  - Document as known limitation

---

## Testing Recommendations

### Comprehensive Test Suite for Transform Classification

**File**: `tests/unit/drawingml/bridges/test_gradient_transform_classification.py`

```python
"""Tests for radial gradient transform classification and policy decisions."""

import pytest
from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import (
    classify_linear,
    decide_radial_policy,
    TransformClass,
)
from svg2ooxml.core.resvg.geometry.matrix import Matrix

class TestTransformClassification:
    """Test SVD-based transform classification."""

    def test_identity_transform(self):
        """Test identity matrix classification."""
        cls = classify_linear(1.0, 0.0, 0.0, 1.0)
        assert not cls.non_uniform
        assert not cls.has_shear
        assert cls.det_sign == 1
        assert cls.s1 == pytest.approx(1.0)
        assert cls.s2 == pytest.approx(1.0)
        assert cls.ratio == pytest.approx(1.0)

    def test_uniform_scale(self):
        """Test uniform scale (2x in both directions)."""
        cls = classify_linear(2.0, 0.0, 0.0, 2.0)
        assert not cls.non_uniform
        assert not cls.has_shear
        assert cls.det_sign == 1
        assert cls.s1 == pytest.approx(2.0)
        assert cls.s2 == pytest.approx(2.0)
        assert cls.ratio == pytest.approx(1.0)

    def test_non_uniform_scale_2x1(self):
        """Test non-uniform scale (2x horizontal, 1x vertical)."""
        cls = classify_linear(2.0, 0.0, 0.0, 1.0)
        assert cls.non_uniform
        assert not cls.has_shear
        assert cls.det_sign == 1
        assert cls.s1 == pytest.approx(2.0)  # Larger singular value
        assert cls.s2 == pytest.approx(1.0)  # Smaller singular value
        assert cls.ratio == pytest.approx(2.0)

    def test_mild_anisotropy(self):
        """Test mild anisotropy (ratio ≈ 1.015, should warn but not rasterize)."""
        # Scale(1.015, 1.0)
        cls = classify_linear(1.015, 0.0, 0.0, 1.0)
        assert cls.non_uniform
        assert not cls.has_shear
        assert cls.ratio == pytest.approx(1.015, abs=0.001)

    def test_skewx_transform(self):
        """Test skewX transform (shear)."""
        # SkewX(30°): tan(30°) ≈ 0.577
        cls = classify_linear(1.0, 0.0, 0.577, 1.0)
        assert cls.has_shear
        assert cls.det_sign == 1

    def test_rotation_90_degrees(self):
        """Test 90-degree rotation (should be uniform, no shear)."""
        # Rotation by 90°: [[0, -1], [1, 0]]
        cls = classify_linear(0.0, 1.0, -1.0, 0.0)
        assert not cls.non_uniform
        assert not cls.has_shear
        assert cls.det_sign == 1
        assert cls.s1 == pytest.approx(1.0)
        assert cls.s2 == pytest.approx(1.0)

    def test_rotation_with_uniform_scale(self):
        """Test rotation + uniform scale (should be uniform, no shear)."""
        # Scale(2) * Rotation(45°)
        import math
        c = 2 * math.cos(math.radians(45))
        s = 2 * math.sin(math.radians(45))
        cls = classify_linear(c, s, -s, c)
        assert not cls.non_uniform
        assert not cls.has_shear
        assert cls.s1 == pytest.approx(2.0)
        assert cls.s2 == pytest.approx(2.0)

    def test_reflection_negative_determinant(self):
        """Test reflection (negative determinant)."""
        # Flip in X: [[-1, 0], [0, 1]]
        cls = classify_linear(-1.0, 0.0, 0.0, 1.0)
        assert cls.det_sign == -1

    def test_degenerate_zero_determinant(self):
        """Test degenerate transform (zero determinant)."""
        # Projection onto x-axis: [[1, 0], [0, 0]]
        cls = classify_linear(1.0, 0.0, 0.0, 0.0)
        assert cls.det_sign == 0
        assert cls.s2 == pytest.approx(0.0)


class TestRadialGradientPolicy:
    """Test policy decisions for radial gradient transforms."""

    def test_policy_vector_ok_identity(self):
        """Test identity transform → vector_ok."""
        policy, cls = decide_radial_policy(1.0, 0.0, 0.0, 1.0)
        assert policy == "vector_ok"
        assert not cls.non_uniform

    def test_policy_vector_ok_uniform_scale(self):
        """Test uniform scale → vector_ok."""
        policy, cls = decide_radial_policy(2.0, 0.0, 0.0, 2.0)
        assert policy == "vector_ok"
        assert not cls.non_uniform

    def test_policy_vector_ok_rotation(self):
        """Test rotation → vector_ok."""
        import math
        c = math.cos(math.radians(45))
        s = math.sin(math.radians(45))
        policy, cls = decide_radial_policy(c, s, -s, c)
        assert policy == "vector_ok"

    def test_policy_warn_mild_anisotropy(self):
        """Test mild anisotropy (ratio=1.015) → vector_warn_mild_anisotropy."""
        policy, cls = decide_radial_policy(1.015, 0.0, 0.0, 1.0, mild_ratio=1.02)
        assert policy == "vector_warn_mild_anisotropy"
        assert cls.non_uniform
        assert not cls.has_shear
        assert cls.ratio <= 1.02

    def test_policy_rasterize_severe_anisotropy(self):
        """Test severe anisotropy (ratio=2.0) → rasterize_nonuniform."""
        policy, cls = decide_radial_policy(2.0, 0.0, 0.0, 1.0)
        assert policy == "rasterize_nonuniform"
        assert cls.ratio == pytest.approx(2.0)

    def test_policy_rasterize_skew(self):
        """Test skew transform → rasterize_nonuniform."""
        # SkewX(30°)
        policy, cls = decide_radial_policy(1.0, 0.0, 0.577, 1.0)
        assert policy == "rasterize_nonuniform"
        assert cls.has_shear

    def test_policy_rasterize_scale_plus_rotation(self):
        """Test non-uniform scale + rotation → rasterize_nonuniform."""
        import math
        # Scale(2, 1) * Rotation(30°)
        c = math.cos(math.radians(30))
        s = math.sin(math.radians(30))
        a = 2 * c
        b = 2 * s
        c_val = -1 * s
        d = 1 * c
        policy, cls = decide_radial_policy(a, b, c_val, d)
        assert policy == "rasterize_nonuniform"


class TestGradientTransformIntegration:
    """Integration tests for gradient adapter with transform classification."""

    def test_radial_gradient_with_non_uniform_scale(self):
        """Test radial gradient adapter with non-uniform scale."""
        from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import radial_gradient_to_paint
        from svg2ooxml.core.resvg.painting.gradients import RadialGradient, GradientStop
        from svg2ooxml.core.resvg.painting.paint import Color

        transform = Matrix(a=2.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)
        stops = [
            GradientStop(offset=0.0, color=Color(r=255, g=0, b=0, a=1.0)),
            GradientStop(offset=1.0, color=Color(r=0, g=0, b=255, a=1.0)),
        ]

        gradient = RadialGradient(
            cx=50.0, cy=50.0, r=20.0,
            fx=50.0, fy=50.0,
            stops=stops,
            transform=transform,
            spread_method="pad",
            href=None,
        )

        paint = radial_gradient_to_paint(gradient)

        # Once Phase 1 implemented:
        # assert paint.policy_decision == "rasterize_nonuniform"
        # assert paint.transform_class is not None
        # assert paint.transform_class.ratio == pytest.approx(2.0)
        # assert paint.had_transform_flag is True

    def test_radial_gradient_with_skew(self):
        """Test radial gradient adapter with skew transform."""
        # SkewX(30°): tan(30°) ≈ 0.577
        transform = Matrix(a=1.0, b=0.0, c=0.577, d=1.0, e=0.0, f=0.0)
        # ... similar to above

    def test_spread_method_reflect(self):
        """Test gradient with reflect spread method."""
        # Once Phase 4 implemented:
        # assert paint.spread_method == "reflect"

    def test_gradient_units_object_bounding_box(self):
        """Test gradient with objectBoundingBox units."""
        # Once Phase 4 implemented:
        # assert paint.gradient_units == "objectBoundingBox"

    def test_performance_guard_large_shape(self):
        """Test rasterization size clamping for large shapes."""
        # Transform with s1 = 10000 (would create huge bitmap)
        transform = Matrix(a=10000.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0)
        # Once Phase 3 implemented:
        # assert paint.raster_size <= 4096  # Clamped to max
```

### Test Coverage Goals

**Phase 1 Tests** (Classification & Telemetry):
- ✅ Identity transform
- ✅ Uniform scale (various factors)
- ✅ Non-uniform scale (2x1, 1.5x0.9, etc.)
- ✅ Mild anisotropy (ratio ≈ 1.015)
- ✅ Rotation (45°, 90°, arbitrary angles)
- ✅ Rotation + uniform scale
- ✅ Rotation + non-uniform scale
- ✅ Skew/shear transforms (skewX, skewY)
- ✅ Reflection (negative determinant)
- ✅ Degenerate (zero determinant)

**Phase 2 Tests** (Vector Warning):
- Telemetry logging for mild anisotropy
- Warning message format and content
- Trace output verification

**Phase 3 Tests** (Rasterization):
- Size calculation for various transforms
- Clamp behavior (64–4096 px)
- Performance guard (large shapes)
- Pattern embedding verification

**Phase 4 Tests** (Units & Spread):
- objectBoundingBox + gradientTransform + shape transform combo
- Spread method preservation (pad/reflect/repeat)
- Units normalization by resvg

---

## References

- **Original implementation**: `src/svg2ooxml/drawingml/bridges/resvg_gradient_adapter.py`
- **Telemetry usage**: `src/svg2ooxml/core/traversal/hooks.py:_serialize_paint()`
- **Style cloning**: `src/svg2ooxml/core/styling/style_extractor.py`
- **IR paint types**: `src/svg2ooxml/ir/paint.py`

---

## Decision Log

**2025-11-03**: Initial transform implementation completed
- ✅ Basic translation/rotation/uniform-scale working
- ⚠️  Non-uniform transforms on radial gradients produce incorrect circles
- ⚠️  Telemetry loses "had transform" information
- ⚠️  Gradient units/spread not tracked

**Next Steps**: Prioritize non-uniform radial gradient detection (medium priority), defer other issues as low-priority follow-ups.
