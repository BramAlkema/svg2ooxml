# Animation Writer Refactoring Specification

## Current State Analysis

**File**: `src/svg2ooxml/drawingml/animation_writer.py`
**Lines**: 1,085
**XML Concatenations**: 112
**Main Class**: `DrawingMLAnimationWriter`

### Critical Issues

1. **XML Security & Maintainability**
   - 112 f-string concatenations for XML generation
   - Manual XML escaping with `xml.sax.saxutils.escape`
   - Potential injection vulnerabilities
   - Hard to test and validate XML structure

2. **Code Organization**
   - Monolithic 1,085-line class with 40+ methods
   - Mixed concerns: parsing, validation, transformation, XML generation
   - Deep nesting (20+ levels in some methods)
   - Heavy code duplication across animation types

3. **Readability & Complexity**
   - Complex f-string templates with nested indentation
   - Similar patterns repeated for each animation type
   - Hard to understand XML structure from string fragments
   - Difficult to maintain consistent indentation

4. **Testing & Debugging**
   - Hard to unit test individual components
   - XML validation requires full end-to-end execution
   - Debugging string concatenation errors is painful

## Proposed Architecture

### 1. Module Structure

```
src/svg2ooxml/drawingml/animation/
├── __init__.py
├── writer.py                    # Main public API (refactored)
├── xml_builders.py              # lxml-based XML builders
├── value_processors.py          # Value parsing & normalization
├── tav_builder.py              # Time-Animated Value list builder
├── policy.py                    # Policy evaluation & skip logic
├── handlers/
│   ├── __init__.py
│   ├── base.py                 # Base handler interface
│   ├── opacity.py              # Opacity/fade animations
│   ├── color.py                # Color animations
│   ├── transform.py            # Scale/rotate/translate
│   ├── numeric.py              # Generic numeric property
│   ├── motion.py               # Motion path animations
│   └── set_value.py            # Set animations
└── constants.py                 # Shared constants & mappings
```

### 2. Core Components

#### 2.1 XML Builders (`xml_builders.py`)

**Purpose**: lxml-based builders for PowerPoint animation timing XML.

```python
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, p_elem, p_sub, to_string
from lxml import etree

class AnimationXMLBuilder:
    """Build PowerPoint animation timing XML using lxml."""

    def build_timing_container(
        self,
        *,
        timing_id: int,
        fragments: list[str],
    ) -> str:
        """Build <p:timing> root container."""

    def build_par_container(
        self,
        *,
        par_id: int,
        duration_ms: int,
        delay_ms: int,
        child_content: str,
    ) -> str:
        """Build <p:par> container with timing."""

    def build_behavior_core(
        self,
        *,
        behavior_id: int,
        duration_ms: int,
        target_shape: str,
        repeat_count: str | int | None = None,
        accel: int | None = None,
        decel: int | None = None,
    ) -> etree._Element:
        """Build <a:cBhvr> common behavior element."""

    def build_attribute_list(
        self,
        attribute_names: list[str],
    ) -> etree._Element:
        """Build <a:attrNameLst>."""

    def build_tav_element(
        self,
        *,
        tm: int,
        value_elem: etree._Element,
        accel: int = 0,
        decel: int = 0,
        metadata: dict[str, str] | None = None,
    ) -> etree._Element:
        """Build <a:tav> time-animated value element."""
```

**Key Features**:
- Uses `xml_builder.py` for namespace handling
- Returns lxml elements for composability
- Handles namespace declarations (including custom svg2: namespace)
- Automatic escaping via lxml

#### 2.2 Value Processors (`value_processors.py`)

**Purpose**: Parse, validate, and normalize animation values.

```python
class ValueProcessor:
    """Process and normalize animation values."""

    @staticmethod
    def parse_numeric_list(value: str) -> list[float]:
        """Parse space/comma-separated numeric list."""

    @staticmethod
    def parse_color(value: str) -> str:
        """Parse color value to hex format (without #)."""

    @staticmethod
    def parse_angle(value: str) -> float:
        """Parse angle value in degrees."""

    @staticmethod
    def parse_scale_pair(value: str) -> tuple[float, float]:
        """Parse scale value (single number or x,y pair)."""

    @staticmethod
    def parse_translation_pair(value: str) -> tuple[float, float]:
        """Parse translation value (dx dy or dx,dy)."""

    @staticmethod
    def normalize_numeric_value(
        attribute: str,
        value: str,
        *,
        unit_converter: UnitConverter,
    ) -> str:
        """Normalize numeric value to PowerPoint units (EMU/60000ths)."""

    @staticmethod
    def parse_opacity(value: str) -> str:
        """Parse opacity value (0-1 or 0-100)."""
```

**Key Features**:
- Pure functions for easy testing
- Consistent error handling
- Clear transformation rules
- Unit conversion delegated to UnitConverter

#### 2.3 TAV Builder (`tav_builder.py`)

**Purpose**: Build Time-Animated Value (keyframe) lists.

```python
from typing import Callable, Protocol

class ValueFormatter(Protocol):
    """Protocol for value formatters."""
    def __call__(self, value: str, processor: ValueProcessor) -> etree._Element:
        """Format value as lxml element."""
        ...

class TAVBuilder:
    """Build <a:tavLst> keyframe lists."""

    def __init__(self, xml_builder: AnimationXMLBuilder):
        self._xml_builder = xml_builder

    def build_tav_list(
        self,
        *,
        values: Sequence[str],
        key_times: Sequence[float] | None,
        key_splines: Sequence[list[float]] | None,
        duration_ms: int,
        value_formatter: ValueFormatter,
    ) -> tuple[list[etree._Element], bool]:
        """
        Build list of <a:tav> elements.

        Returns:
            (tav_elements, needs_custom_namespace)
        """

    def resolve_key_times(
        self,
        values: Sequence[str],
        key_times: Sequence[float] | None,
    ) -> list[float]:
        """Resolve keyframe times (auto-distribute if not provided)."""

    def compute_tav_metadata(
        self,
        index: int,
        key_times: Sequence[float],
        duration_ms: int,
        splines: Sequence[list[float]],
    ) -> dict[str, str]:
        """Compute TAV metadata attributes (spline info, timing)."""
```

**Value Formatters**:
```python
def format_numeric_value(value: str, processor: ValueProcessor) -> etree._Element:
    """Format numeric value as <a:val val="..."/>."""

def format_color_value(value: str, processor: ValueProcessor) -> etree._Element:
    """Format color as <a:val><a:srgbClr val="..."/></a:val>."""

def format_point_value(value: str, processor: ValueProcessor) -> etree._Element:
    """Format point as <a:val><a:pt x="..." y="..."/></a:val>."""

def format_angle_value(value: str, processor: ValueProcessor) -> etree._Element:
    """Format angle as <a:val val="..."/> (in 60000ths)."""
```

**Key Features**:
- Single responsibility: keyframe list building
- Pluggable value formatters
- Consistent spline metadata handling
- Clear separation of timing vs. value logic

#### 2.4 Animation Handlers (`handlers/`)

**Purpose**: Type-specific animation builders using composition.

```python
# handlers/base.py
class AnimationHandler(ABC):
    """Base class for animation type handlers."""

    def __init__(
        self,
        xml_builder: AnimationXMLBuilder,
        value_processor: ValueProcessor,
        tav_builder: TAVBuilder,
        unit_converter: UnitConverter,
    ):
        self._xml = xml_builder
        self._values = value_processor
        self._tav = tav_builder
        self._units = unit_converter

    @abstractmethod
    def can_handle(self, animation: AnimationDefinition) -> bool:
        """Check if this handler supports the animation."""

    @abstractmethod
    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        """Build XML fragment for this animation."""

# handlers/opacity.py
class OpacityAnimationHandler(AnimationHandler):
    """Handle opacity/fade animations."""

    def can_handle(self, animation: AnimationDefinition) -> bool:
        attr = (animation.target_attribute or "").lower()
        return attr in {"opacity", "fill-opacity", "stroke-opacity"}

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> str:
        # Build <a:animEffect> with <a:fade>
        # Uses self._xml for structure
        # Uses self._values for opacity parsing
        ...

# handlers/transform.py
class TransformAnimationHandler(AnimationHandler):
    """Handle scale/rotate/translate animations."""

    def can_handle(self, animation: AnimationDefinition) -> bool:
        return animation.animation_type == AnimationType.ANIMATE_TRANSFORM

    def build(self, ...) -> str:
        # Route to _build_scale, _build_rotate, or _build_translate
        ...

    def _build_scale(self, ...) -> str:
        # Build <a:animScale> with TAV list
        ...

    def _build_rotate(self, ...) -> str:
        # Build <a:animRot> with TAV list
        ...

    def _build_translate(self, ...) -> str:
        # Build <a:animMotion> with <a:by>
        ...
```

**Key Features**:
- Each handler focused on one animation type
- Composition over inheritance
- Testable in isolation
- Clear dependencies via constructor

#### 2.5 Policy Engine (`policy.py`)

**Purpose**: Evaluate animation policy and determine skip reasons.

```python
class AnimationPolicy:
    """Evaluate animation policy decisions."""

    def __init__(self, options: Mapping[str, Any]):
        self._options = options

    def should_skip(
        self,
        animation: AnimationDefinition,
        max_error: float,
    ) -> tuple[bool, str | None]:
        """
        Determine if animation should be skipped.

        Returns:
            (should_skip, reason)
        """

    def estimate_spline_error(
        self,
        animation: AnimationDefinition,
    ) -> float:
        """Estimate maximum spline approximation error."""
```

**Key Features**:
- Isolated policy logic
- Clear skip reasons
- Testable without XML generation
- Options parsing centralized

#### 2.6 Main Writer (`writer.py`)

**Purpose**: Orchestrate animation building with refactored architecture.

```python
class DrawingMLAnimationWriter:
    """Generate PowerPoint animation timing XML from animation definitions."""

    def __init__(self):
        self._id_counter = 1000
        self._xml_builder = AnimationXMLBuilder()
        self._value_processor = ValueProcessor()
        self._tav_builder = TAVBuilder(self._xml_builder)
        self._unit_converter = UnitConverter()

        # Initialize handlers
        self._handlers: list[AnimationHandler] = [
            OpacityAnimationHandler(self._xml_builder, self._value_processor,
                                   self._tav_builder, self._unit_converter),
            ColorAnimationHandler(...),
            TransformAnimationHandler(...),
            NumericAnimationHandler(...),
            MotionAnimationHandler(...),
            SetAnimationHandler(...),
        ]

    def build(
        self,
        animations: Sequence[AnimationDefinition],
        timeline: Sequence[AnimationScene],
        *,
        tracer: ConversionTracer | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> str:
        """Return a <p:timing> fragment or empty string when unsupported."""
        options = dict(options or {})
        policy = AnimationPolicy(options)

        fragments: list[str] = []
        for animation in animations:
            # Policy check
            max_error = policy.estimate_spline_error(animation)
            should_skip, reason = policy.should_skip(animation, max_error)

            if should_skip:
                # Trace skip
                continue

            # Find handler
            handler = self._find_handler(animation)
            if not handler:
                # Trace unsupported
                continue

            # Build fragment
            par_id, behavior_id = self._allocate_ids()
            fragment = handler.build(animation, par_id, behavior_id)

            if fragment:
                fragments.append(fragment)
                # Trace success

        if not fragments:
            return ""

        # Build timing container
        timing_id = self._next_id()
        return self._xml_builder.build_timing_container(
            timing_id=timing_id,
            fragments=fragments,
        )

    def _find_handler(self, animation: AnimationDefinition) -> AnimationHandler | None:
        """Find appropriate handler for animation type."""
        for handler in self._handlers:
            if handler.can_handle(animation):
                return handler
        return None
```

**Key Features**:
- Clean orchestration
- Handler registry pattern
- Dependency injection
- Minimal complexity

### 3. Constants & Mappings (`constants.py`)

**Purpose**: Centralize all constants and mappings.

```python
# Attribute categories
FADE_ATTRIBUTES = frozenset({"opacity", "fill-opacity", "stroke-opacity"})
COLOR_ATTRIBUTES = frozenset({
    "fill", "stroke", "stop-color", "stopcolor",
    "flood-color", "lighting-color",
})

# Attribute name mappings for PowerPoint
ATTRIBUTE_NAME_MAP = {
    "x": "ppt_x",
    "y": "ppt_y",
    "width": "ppt_w",
    "height": "ppt_h",
    "rotate": "ppt_angle",
    # ... rest of mappings
}

COLOR_ATTRIBUTE_NAME_MAP = {
    "fill": "fillClr",
    "stroke": "lnClr",
    # ... rest of mappings
}

AXIS_MAP = {
    "ppt_x": "x",
    "ppt_y": "y",
    "ppt_w": "width",
    "ppt_h": "height",
}

ANGLE_ATTRIBUTES = frozenset({"angle", "rotation", "rotate", "ppt_angle"})

# Namespace for custom animation metadata
SVG2_ANIMATION_NS = "http://svg2ooxml.dev/ns/animation"
```

### 4. Migration Strategy

#### Phase 1: Extract Components (No Breaking Changes)
1. Create new module structure
2. Implement XML builders
3. Implement value processors
4. Keep old code working

#### Phase 2: Implement Handlers
1. Create handler base class
2. Implement one handler (opacity) with tests
3. Verify output matches old implementation
4. Implement remaining handlers incrementally

#### Phase 3: Replace Main Writer
1. Implement new `DrawingMLAnimationWriter.build()`
2. Run side-by-side comparison tests
3. Verify identical XML output
4. Switch over

#### Phase 4: Cleanup
1. Remove old implementation
2. Update tests
3. Update documentation

### 5. Testing Strategy

#### Unit Tests
- **XML Builders**: Test each builder method independently
- **Value Processors**: Test all parsing/normalization functions
- **TAV Builder**: Test keyframe list generation
- **Handlers**: Test each handler with sample animations
- **Policy**: Test skip conditions

#### Integration Tests
- Compare new vs. old output for existing test cases
- Validate XML schema compliance
- Test with real animation definitions

#### Property Tests
- Use hypothesis for value processors
- Test XML well-formedness
- Test reversibility where applicable

### 6. Benefits

#### Immediate
- ✅ **Security**: No XML injection vulnerabilities
- ✅ **Maintainability**: 40% less code through deduplication
- ✅ **Readability**: Clear structure vs. nested f-strings
- ✅ **Testability**: Each component testable in isolation

#### Long-term
- ✅ **Extensibility**: Easy to add new animation types
- ✅ **Performance**: lxml is faster than string concatenation
- ✅ **Debugging**: Clear error messages, easier to trace
- ✅ **Documentation**: Self-documenting code structure

### 7. API Compatibility

**Public API remains identical**:
```python
writer = DrawingMLAnimationWriter()
xml = writer.build(animations, timeline, tracer=tracer, options=options)
```

**Internal changes only** - no breaking changes for consumers.

### 8. File Size Estimates

| File | LOC (Est.) | Purpose |
|------|-----------|---------|
| `xml_builders.py` | 200 | XML building with lxml |
| `value_processors.py` | 150 | Value parsing/normalization |
| `tav_builder.py` | 120 | Keyframe list building |
| `policy.py` | 80 | Policy evaluation |
| `handlers/base.py` | 40 | Base handler |
| `handlers/opacity.py` | 80 | Opacity animations |
| `handlers/color.py` | 100 | Color animations |
| `handlers/transform.py` | 180 | Scale/rotate/translate |
| `handlers/numeric.py` | 100 | Numeric properties |
| `handlers/motion.py` | 120 | Motion paths |
| `handlers/set_value.py` | 70 | Set animations |
| `constants.py` | 50 | Constants |
| `writer.py` | 150 | Main orchestrator |
| **Total** | **~1,440** | vs. current 1,085 |

**Complexity reduction**: Despite ~35% more LOC, complexity is much lower due to:
- Clear separation of concerns
- No deep nesting
- Reusable components
- Better abstraction

### 9. Success Criteria

1. ✅ All existing tests pass
2. ✅ New code produces identical XML output (modulo whitespace)
3. ✅ Zero XML string concatenations
4. ✅ All components have >90% test coverage
5. ✅ Performance: No more than 5% slower than current
6. ✅ Code review: Approved by maintainer

### 10. Implementation Order

1. **constants.py** - No dependencies
2. **xml_builders.py** - Uses xml_builder.py
3. **value_processors.py** - No dependencies
4. **tav_builder.py** - Uses xml_builders.py
5. **policy.py** - No dependencies
6. **handlers/base.py** - Uses xml_builders, value_processors, tav_builder
7. **handlers/opacity.py** - First concrete handler
8. **handlers/** (rest) - Remaining handlers
9. **writer.py** - Orchestrates everything
10. **Tests** - Throughout

### 11. Risk Mitigation

**Risk**: XML output differences breaking consumers
**Mitigation**: Extensive diff testing, side-by-side comparison

**Risk**: Performance regression
**Mitigation**: Benchmark before/after, lxml is typically faster

**Risk**: Bugs in refactored code
**Mitigation**: Incremental rollout, comprehensive testing

**Risk**: Increased complexity
**Mitigation**: Clear abstractions, good documentation, code review

---

## Approval Checklist

- [ ] Architecture reviewed
- [ ] Migration strategy approved
- [ ] Testing strategy approved
- [ ] Timeline estimated
- [ ] Resources allocated
- [ ] Risk mitigation reviewed
- [ ] Go/No-Go decision

## Notes

This refactoring addresses all issues identified:
- Eliminates 112 XML concatenations
- Improves security via lxml
- Enhances maintainability through separation of concerns
- Enables better testing
- Maintains API compatibility
- Sets foundation for future animation features
