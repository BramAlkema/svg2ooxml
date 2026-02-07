# ADR-022: Centralize PowerPoint Unit Conversions

- **Status:** Proposed
- **Date:** 2026-02-07
- **Owners:** svg2ooxml team
- **Depends on:** ADR-020 (animation writer rewrite — proved pattern in animation module)

## 1. Problem Statement

PowerPoint uses non-standard units for angles (60,000ths of a degree), opacity
(0–100,000 scale), and positions (EMU). The codebase has centralized converters
at `common/conversions/` but almost nobody uses them. Instead, inline magic
number arithmetic is copy-pasted throughout:

### 1.1 Angle Conversions — `* 60000`

The inline pattern `int(... * 60000)` appears in 7 files with subtle
variations in rounding and modular reduction:

| File | Line | Expression |
|---|---|---|
| `services/gradient_service.py` | 450 | `int(((90 - angle) % 360) * 60000)` |
| `drawingml/paint_runtime.py` | 219 | `int(round(angle * 60000))` |
| `drawingml/filter_renderer.py` | 158 | `int((math.degrees(angle_rad) * 60000) % 21600000)` |
| `ir/effects.py` | 38 | `int(self.angle * 60000) % 21600000` |
| `filters/primitives/drop_shadow.py` | 78 | `int((angle % 360) * 60000)` |
| `filters/primitives/color_matrix.py` | 89 | `int((degrees % 360) * 60000)` |
| `filters/primitives/offset.py` | 57 | `int((math.degrees(angle_rad) * 60000) % 21600000)` |

The centralized `degrees_to_ppt()` in `common/conversions/angles.py` already
does `int(round(degrees * PPT_ANGLE_SCALE))`. Only the animation module uses it.

### 1.2 Opacity/Alpha Conversions — `* 100000`

The inline pattern `int(... * 100000)` with ad-hoc clamping appears in **15+
files**, 30+ instances:

| File | Lines | Count |
|---|---|---|
| `drawingml/paint_runtime.py` | 35, 85, 244–247, 286, 315, 316 | 8 |
| `services/gradient_service.py` | 227, 403, 406, 407 | 4 |
| `drawingml/shapes_runtime.py` | 544, 553 | 2 |
| `filters/primitives/drop_shadow.py` | 61, 92 | 2 |
| `filters/primitives/blend.py` | 199 | 1 |
| `filters/primitives/flood.py` | 62 | 1 |
| `filters/primitives/color_matrix.py` | 78 | 1 |
| `filters/primitives/morphology.py` | 83 | 1 |
| `filters/primitives/gaussian_blur.py` | 178 | 1 |
| `drawingml/mask_writer.py` | 428 | 1 |
| `drawingml/filter_renderer.py` | 129 | 1 |
| `core/pipeline/mappers/path_mapper.py` | 182, 199 | 2 |
| `ir/effects.py` | 41, 76, 77 | 3 |
| `color/advanced/core.py` | 654 | 1 |
| `core/resvg/text/drawingml_generator.py` | 315, 327 | 2 |

The centralized `opacity_to_ppt()` in `common/conversions/opacity.py` already
does `int(round(max(0.0, min(1.0, opacity)) * PPT_OPACITY_SCALE))` with
proper clamping. Only the animation module uses it.

### 1.3 Why This Matters

- **Inconsistent rounding** — some sites use `int(round(...))`, others use
  `int(...)` (truncating), others clamp before or after multiplication.
- **Inconsistent clamping** — some sites clamp to 0.0–1.0 before multiplying,
  others don't. A few clamp to 0–100000 after.
- **Unnamed constants** — `60000` and `100000` carry no semantic meaning at
  point of use. Reviewers must remember what they represent.
- **Bug surface** — `gradient_service.py` line 450 applies a 90-degree SVG→PPT
  coordinate rotation *inside* the angle conversion. This domain-specific
  adjustment is tangled with the unit conversion.

## 2. Design

### 2.1 Use Existing Converters

The converters already exist and are well-tested:

```python
from svg2ooxml.common.conversions.angles import degrees_to_ppt, radians_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt, alpha_to_ppt
```

No new utilities are needed. The migration is purely about adoption.

### 2.2 Add Position/Scale Converter

For the `* 100000` usage that represents scale factors (not opacity), add a
converter to `common/conversions/`:

```python
# common/conversions/scale.py
PPT_SCALE = 100000

def scale_to_ppt(factor: float) -> int:
    """Convert a 0-1 scale factor to PPT units (0-100000)."""
    return int(round(factor * PPT_SCALE))

def percentage_position_to_ppt(fraction: float) -> int:
    """Convert a 0-1 fraction to PPT percentage position (0-100000)."""
    clamped = max(0.0, min(1.0, fraction))
    return int(round(clamped * PPT_SCALE))
```

This disambiguates opacity (clamped 0–1) from scale (may exceed 1.0) from
position percentage (clamped 0–1).

### 2.3 Separate Domain Logic from Unit Conversion

Where domain-specific adjustments exist (e.g. gradient angle rotation,
modular reduction), these should be explicit:

```python
# Before: tangled
ppt_angle = int(((90 - angle) % 360) * 60000)

# After: separated
svg_to_ppt_degrees = (90 - angle) % 360  # SVG→PPT coordinate rotation
ppt_angle = degrees_to_ppt(svg_to_ppt_degrees)
```

## 3. Migration Plan

### Phase 1: Angle conversions (7 files)

Replace all `* 60000` instances with `degrees_to_ppt()` or `radians_to_ppt()`.
Separate domain adjustments (coordinate rotation, modular reduction) from the
unit conversion call.

**Files:** gradient_service, paint_runtime, filter_renderer, ir/effects,
drop_shadow, color_matrix, offset

### Phase 2: Opacity/alpha conversions (15 files)

Replace all `* 100000` opacity instances with `opacity_to_ppt()` or
`alpha_to_ppt()`. Remove ad-hoc clamping that the converter already handles.

**Files:** paint_runtime, gradient_service, shapes_runtime, filter_renderer,
path_mapper, mask_writer, all filter primitives, color/advanced/core,
resvg/text/drawingml_generator, ir/effects

### Phase 3: Scale/position conversions

Introduce `scale_to_ppt()` and `percentage_position_to_ppt()` for the
remaining `* 100000` instances that aren't opacity (scale factors in animation
transforms, gradient tile rectangles in paint_runtime lines 244–247).

## 4. Testing Strategy

- All conversions are value-preserving — `int(round(x * 60000))` is exactly
  what `degrees_to_ppt(x)` does. Tests should not change.
- Run the full test suite after each phase.
- For sites with inconsistent rounding (truncation vs round), the migration
  to `degrees_to_ppt()` / `opacity_to_ppt()` normalizes to `int(round(...))`.
  Verify any EMU-sensitive golden masters still pass.

## 5. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Rounding changes from `int(x)` → `int(round(x))` | Audit each site; difference is at most 1 unit (invisible in PPT) |
| Clamping changes for sites missing clamp | `opacity_to_ppt()` clamps; verify no caller relies on out-of-range values |
| Gradient angle domain adjustment lost | Keep domain logic explicit alongside `degrees_to_ppt()` call |
| Import churn across many files | Mechanical; linter catches unused imports |

## 6. Decision

Adopt the existing `common/conversions/` utilities across the codebase. No new
abstraction — just consistent use of what already exists. Prioritize
`paint_runtime.py` and `gradient_service.py` (highest instance count).
