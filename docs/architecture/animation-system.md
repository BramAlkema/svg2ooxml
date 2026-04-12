# Animation System Architecture

**Status**: Production (as of Phase 5 completion)
**Module**: `svg2ooxml.drawingml.animation`
**Replaced**: `svg2ooxml.drawingml.animation_writer` (deprecated)

## Overview

The animation system converts SVG/SMIL animation definitions to PowerPoint timing XML. The architecture uses a modular handler pattern with lxml-based XML generation, replacing the previous monolithic string-concatenation approach.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  DrawingMLAnimationWriter                    │
│                     (Orchestrator)                           │
├─────────────────────────────────────────────────────────────┤
│  - Handler registry                                          │
│  - ID allocation (par_id, behavior_id)                      │
│  - Policy integration (skip decisions)                       │
│  - Tracer integration (telemetry)                           │
└──────────────┬──────────────────────────────────────────────┘
               │
               │ delegates to
               ↓
┌─────────────────────────────────────────────────────────────┐
│                    Handler Pattern                           │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────┐  ┌───────────────────┐              │
│  │ OpacityHandler    │  │ ColorHandler      │              │
│  │ (fade effects)    │  │ (fill, stroke)    │              │
│  └───────────────────┘  └───────────────────┘              │
│                                                              │
│  ┌───────────────────┐  ┌───────────────────┐              │
│  │ NumericHandler    │  │ TransformHandler  │              │
│  │ (x, y, width...)  │  │ (scale, rotate)   │              │
│  └───────────────────┘  └───────────────────┘              │
│                                                              │
│  ┌───────────────────┐  ┌───────────────────┐              │
│  │ MotionHandler     │  │ SetHandler        │              │
│  │ (motion paths)    │  │ (SET animations)  │              │
│  └───────────────────┘  └───────────────────┘              │
└──────────────┬──────────────────────────────────────────────┘
               │
               │ uses
               ↓
┌─────────────────────────────────────────────────────────────┐
│                   Infrastructure Layer                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────┐  ┌──────────────────────┐         │
│  │ AnimationXMLBuilder │  │ ValueProcessor       │         │
│  │ - build_par_container│  │ - parse_color()     │         │
│  │ - build_behavior_core│  │ - parse_opacity()   │         │
│  │ - build_tav_element │  │ - normalize_numeric()│         │
│  └─────────────────────┘  └──────────────────────┘         │
│                                                              │
│  ┌─────────────────────┐  ┌──────────────────────┐         │
│  │ TAVBuilder          │  │ AnimationPolicy      │         │
│  │ - build_tav_list()  │  │ - should_skip()      │         │
│  │ - compute_metadata()│  │ - estimate_error()   │         │
│  └─────────────────────┘  └──────────────────────┘         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. DrawingMLAnimationWriter (Orchestrator)

**Location**: `svg2ooxml.drawingml.animation.writer`

**Responsibilities**:
- Handler selection via `_find_handler()`
- ID allocation for XML elements
- Policy evaluation (skip logic)
- Timing container generation
- Tracer integration for telemetry

**Key Methods**:
```python
def build(
    animations: Sequence[AnimationDefinition],
    timeline: Sequence[AnimationScene],
    tracer: Tracer | None = None,
    options: Mapping[str, Any] | None = None,
) -> str
```

### 2. Handler Pattern

**Base Handler**: `svg2ooxml.drawingml.animation.handlers.base.AnimationHandler`

**Handler Responsibilities**:
- Determine if it can handle an animation (`can_handle()`)
- Build PowerPoint XML for that animation type (`build()`)
- Use infrastructure components for XML generation

**Handler Registry** (in priority order):
1. **MotionHandler** - Motion path animations (ANIMATE_MOTION)
2. **TransformHandler** - Transform animations (scale, rotate, translate)
3. **SetHandler** - SET animations (discrete value changes)
4. **OpacityHandler** - Fade effects (opacity, fill-opacity, stroke-opacity)
5. **ColorHandler** - Color animations (fill, stroke, stop-color)
6. **NumericHandler** - Generic numeric properties (catch-all)

**Mock-Safe Helpers** (Base Handler):
```python
@staticmethod
def _resolve_animation_type(animation) -> AnimationType | None:
    """Return normalized animation_type, treating unset mocks as None."""

@staticmethod
def _resolve_target_attribute(animation) -> str | None:
    """Return effective target attribute with backward compatibility."""

@staticmethod
def _animation_type_to_str(animation_type) -> str:
    """Convert arbitrary animation_type to uppercase string."""
```

### 3. XML Generation (lxml-based)

**AnimationXMLBuilder** (`xml_builders.py`):
- Creates lxml elements for PowerPoint timing schema
- Handles namespace declarations (including custom `svg2:` namespace)
- Returns XML strings via `etree.tostring()`

**Key Builders**:
- `build_timing_container()` - Top-level `<p:timing>` wrapper
- `build_par_container()` - Parallel timing group `<p:par>`
- `build_behavior_core()` - Common behavior `<a:cBhvr>` element
- `build_tav_element()` - Keyframe `<a:tav>` with easing metadata
- `build_attribute_list()` - Attribute name list `<a:attrNameLst>`

### 4. Value Processing

**ValueProcessor** (`value_processors.py`):

Delegates to `svg2ooxml.common.conversions` for core parsing:
- `parse_color()` → hex color strings
- `parse_opacity()` → PowerPoint units (0-100000)
- `parse_angle()` → degrees
- `parse_scale_pair()` → (x, y) tuples

Animation-specific normalization:
- `normalize_numeric_value()` - Attribute-specific unit conversion (px→EMU, deg→60000ths)

### 5. Keyframe/Easing Support

**TAVBuilder** (`tav_builder.py`):

Builds Time-Animated Value (TAV) lists for multi-keyframe animations:
- Resolves key times (explicit or evenly distributed)
- Computes acceleration/deceleration from cubic bezier splines
- Formats custom easing metadata as `svg2:` namespace attributes
- Returns `(tav_elements, needs_custom_namespace)` tuple

**Spline Conversion**:
- SVG cubic bezier `[c1x, c1y, c2x, c2y]`
- PowerPoint accel/decel integers (0-100000)
- Heuristic: `accel = c1y * 100000`, `decel = (1 - c2y) * 100000`

### 6. Policy & Filtering

**AnimationPolicy** (`policy.py`):

Determines which animations should be skipped:
- Spline error threshold (Bezier approximation quality)
- Disabled animation types
- Invalid/unsupported animations

**Configuration**:
```python
options = {
    "max_spline_error": 0.01,  # Max Bezier error tolerance
}
```

## Handler Details

### OpacityHandler

**Handles**: `opacity`, `fill-opacity`, `stroke-opacity`
**PowerPoint Element**: `<a:animEffect>` with `<a:fade>`
**Animation Type**: `ANIMATE`

**Key Logic**:
- Uses `parse_opacity()` to convert 0-1 → 0-100000
- Final opacity from last animation value
- PowerPoint uses in/out transition model

### ColorHandler

**Handles**: `fill`, `stroke`, `stop-color`, `flood-color`, `lighting-color`
**PowerPoint Element**: `<a:animClr>`
**Animation Type**: `ANIMATE` or `ANIMATE_COLOR`

**Key Logic**:
- Parses colors to hex format (`#RRGGBB`)
- Maps SVG attributes to PowerPoint: `fill` → `fill.color`, `stroke` → `stroke.color`
- Builds `<a:from>` and `<a:to>` with `<a:srgbClr>` elements
- Supports TAV keyframes for multi-color animations

### NumericHandler

**Handles**: All numeric attributes not handled by specialized handlers
**PowerPoint Element**: `<a:anim>`
**Animation Type**: `ANIMATE`

**Examples**: `x`, `y`, `width`, `height`, `stroke-width`, `r`, `cx`, `cy`

**Key Logic**:
- Converts values based on attribute type:
  - Position/size → EMU (English Metric Units)
  - Angles → 60000ths of a degree
- Maps SVG attributes: `x` → `ppt_x`, `rotate` → `ppt_angle`
- Includes `<a:attrNameLst>` for attribute targeting

### TransformHandler

**Handles**: Transform animations with explicit `transform_type`
**PowerPoint Elements**: `<a:animScale>`, `<a:animRot>`, `<a:animMotion>`
**Animation Type**: `ANIMATE_TRANSFORM`

**Transform Types**:

1. **Scale** (`<a:animScale>`):
   - Parses single value or `x,y` pairs
   - Uses `<a:pt x="..." y="..."/>` elements
   - TAV keyframes supported

2. **Rotate** (`<a:animRot>`):
   - Computes rotation delta: `(end_angle - start_angle) * 60000`
   - Uses `<a:by val="..."/>` for cumulative rotation
   - TAV keyframes with cumulative deltas

3. **Translate** (`<a:animMotion>`):
   - Not fully implemented yet
   - Would use motion path format

### MotionHandler

**Handles**: Motion path animations
**PowerPoint Element**: `<a:animMotion>` with `<a:ptLst>`
**Animation Type**: `ANIMATE_MOTION`

**Key Logic**:
- Parses SVG path data (`M`, `L`, `C` commands)
- Samples Bezier curves into line segments (20 samples/curve)
- Deduplicates consecutive points
- Converts points to EMU
- Generates `<a:pt>` list

### SetHandler

**Handles**: Discrete value changes
**PowerPoint Element**: `<a:set>`
**Animation Type**: `SET`

**Key Logic**:
- Instant value change (no interpolation)
- Handles both color and numeric values
- Uses `<a:to>` element with appropriate value type

## Constants & Configuration

**File**: `constants.py`

**Attribute Sets**:
```python
FADE_ATTRIBUTES = frozenset({"opacity", "fill-opacity", "stroke-opacity"})
COLOR_ATTRIBUTES = frozenset({"fill", "stroke", "stop-color", ...})
ANGLE_ATTRIBUTES = frozenset({"rotate", "rotation", "angle"})
```

**Attribute Name Maps**:
```python
ATTRIBUTE_NAME_MAP = {
    "x": "ppt_x",
    "y": "ppt_y",
    "width": "ppt_w",
    "height": "ppt_h",
    "rotate": "ppt_angle",
}

COLOR_ATTRIBUTE_NAME_MAP = {
    "fill": "fill.color",
    "stroke": "stroke.color",
    ...
}
```

**Custom Namespace**:
```python
SVG2_ANIMATION_NS = "http://svg2ooxml.anthropic.com/animation/1.0"
```

Used for storing original spline values as metadata on TAV elements.

## PowerPoint Timing Schema

### Basic Animation Structure

```xml
<p:timing>
  <p:tnLst>
    <p:par>
      <p:cTn id="1002" dur="indefinite" restart="always">
        <p:childTnLst>
          <!-- Individual animations here -->
          <p:par>
            <p:cTn id="1000" dur="1000" fill="hold">
              <p:stCondLst>
                <p:cond delay="0"/>
              </p:stCondLst>
              <p:childTnLst>
                <a:animEffect>...</a:animEffect>
              </p:childTnLst>
            </p:cTn>
          </p:par>
        </p:childTnLst>
      </p:cTn>
    </p:par>
  </p:tnLst>
</p:timing>
```

### Common Behavior Element

```xml
<a:cBhvr>
  <a:cTn id="1001" dur="1000" fill="hold"/>
  <a:tgtEl>
    <a:spTgt spid="shape1"/>
  </a:tgtEl>
  <!-- Optional for numeric/color/set animations -->
  <a:attrNameLst>
    <a:attrName>ppt_x</a:attrName>
  </a:attrNameLst>
</a:cBhvr>
```

### TAV (Time-Animated Value) Elements

```xml
<a:tavLst>
  <a:tav tm="0" svg2:spline="0.42 0 0.58 1">
    <a:val val="0"/>
  </a:tav>
  <a:tav tm="500000" accel="42000" decel="42000">
    <a:val val="50"/>
  </a:tav>
  <a:tav tm="1000000">
    <a:val val="100"/>
  </a:tav>
</a:tavLst>
```

**Time Units**: Microseconds (1s = 1,000,000)
**Accel/Decel**: 0-100000 scale (100000 = 100%)

## Testing Strategy

### Test Pyramid

**Unit Tests** (467 tests):
- Handler tests: Each handler tested in isolation
- XML builder tests: Verify correct element structure
- Value processor tests: Test conversions
- TAV builder tests: Keyframe generation
- Policy tests: Skip logic

**Integration Tests**:
- Comparison tests: Old vs new implementation
- End-to-end: Full animation workflow

### Test Utilities

**Mock-Safe Design**:
- Handlers check `animation_type is not None`
- Base handler provides `_resolve_animation_type()`
- Tests can use both real IR objects and Mocks

**Comparison Framework** (`test_writer_comparison.py`):
```python
def create_test_animation(...) -> AnimationDefinition:
    # Creates real IR objects for testing
    ...

# Compare outputs
old_xml = old_writer.build([animation], [])
new_xml = new_writer.build([animation], [])
assert normalize_xml(old_xml) == normalize_xml(new_xml)
```

## Migration Guide

### For Library Users

**Old Import** (deprecated):
```python
from svg2ooxml.drawingml.animation_writer import DrawingMLAnimationWriter
```

**New Import** (recommended):
```python
from svg2ooxml.drawingml.animation import DrawingMLAnimationWriter
# or
from svg2ooxml.drawingml import DrawingMLAnimationWriter
```

**API Compatibility**: The `build()` method signature remains unchanged.

### For Contributors

**Adding a New Handler**:

1. Create handler class in `handlers/`:
```python
from .base import AnimationHandler, AnimationDefinition

class MyHandler(AnimationHandler):
    def can_handle(self, animation: AnimationDefinition) -> bool:
        # Check if this handler should process this animation
        return animation.target_attribute == "my-property"

    def build(self, animation, par_id, behavior_id) -> str:
        # Build PowerPoint XML
        ...
```

2. Register in `writer.py`:
```python
self._handlers = [
    MotionAnimationHandler(...),
    # ... other handlers ...
    MyHandler(...),  # Add here (order matters!)
]
```

3. Write comprehensive tests in `tests/unit/drawingml/animation/handlers/test_my_handler.py`

## Performance Characteristics

**Before** (string concatenation):
- Simple string operations (fast for small inputs)
- No validation
- Manual escaping required

**After** (lxml):
- Structured XML generation (slight overhead)
- Automatic escaping and validation
- Better memory efficiency for large animations
- ~5% slower in microbenchmarks, negligible in practice

**Optimization Opportunities**:
- Handler lookup could use dictionary dispatch
- XML serialization could be deferred
- TAV computation could be memoized

## Future Enhancements

**Potential Improvements**:
1. Complete translate animation support
2. Audio/video synchronization
3. More sophisticated easing functions
4. Animation timeline optimization
5. Support for PowerPoint's advanced timing features

## References

- **Spec**: `docs/specs/animation-writer-refactoring-spec.md`
- **Tasks**: `docs/tasks/animation-writer-refactoring-tasks.md`
- **ADR**: `docs/adr/ADR-013-animation-and-multislide-port.md`
- **ECMA-376**: PowerPoint Open XML specification (timing schema)
- **SMIL**: Synchronized Multimedia Integration Language (SVG animations)

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2025-01-04 | Modular lxml architecture, 467 tests |
| 1.0 | - | Original string-concatenation implementation |
