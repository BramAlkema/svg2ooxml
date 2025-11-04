# Centralized Conversion Utilities Specification

## Problem Statement

Conversion logic for colors, units, angles, and transforms is currently scattered across the codebase:

### Current Duplication

1. **Unit Conversions** (px → EMU):
   - ✅ `common/units/conversion.py` - Main implementation
   - `drawingml/generator.py` - Local `px_to_emu` function
   - `animation_writer.py` - Uses `UnitConverter._unit_converter.to_emu()`
   - Various files importing different versions

2. **Color Conversions**:
   - ✅ `color/utils.py` - `color_to_hex()`
   - `animation_writer.py` - Custom `_to_hex_color()` wrapper
   - 16+ files with various implementations

3. **Angle Conversions**:
   - ❌ No centralized implementation
   - PowerPoint uses 60000ths of a degree
   - Duplicated across animation_writer, rotation code

4. **Opacity/Alpha Conversions**:
   - ❌ No centralized implementation
   - PowerPoint uses 100000ths scale (0-100000)
   - SVG uses 0-1 scale
   - Duplicated across filters, colors, animations

5. **Transform Parsing**:
   - Scale pairs: "1.5" → (1.5, 1.5) or "1.5 2.0" → (1.5, 2.0)
   - Rotation angles: various formats
   - Translation: "10 20" → (10, 20)
   - No central parser

## Proposed Solution

Create a **unified conversion module** that centralizes all conversion logic.

### Architecture

```
src/svg2ooxml/common/conversions/
├── __init__.py              # Public API exports
├── units.py                 # Re-export from common/units (no change)
├── colors.py                # Color conversions (extend existing)
├── angles.py                # Angle conversions (NEW)
├── opacity.py               # Opacity/alpha conversions (NEW)
├── powerpoint.py            # PowerPoint-specific conversions (NEW)
└── transforms.py            # Transform value parsing (NEW)
```

## Module Details

### 1. `conversions/__init__.py` - Public API

```python
"""Centralized conversion utilities for svg2ooxml."""

from .units import (
    UnitConverter,
    px_to_emu,
    emu_to_px,
    emu_to_unit,
    ConversionContext,
    DEFAULT_DPI,
    EMU_PER_INCH,
    EMU_PER_CM,
    EMU_PER_MM,
    EMU_PER_POINT,
    EMU_PER_PX_AT_DEFAULT_DPI,
)

from .colors import (
    color_to_hex,
    parse_color,
    hex_to_rgb,
    rgb_to_hex,
)

from .angles import (
    degrees_to_ppt,
    radians_to_ppt,
    ppt_to_degrees,
    ppt_to_radians,
)

from .opacity import (
    opacity_to_ppt,
    ppt_to_opacity,
    alpha_to_ppt,
    ppt_to_alpha,
)

from .powerpoint import (
    PPTConverter,
)

from .transforms import (
    parse_scale_pair,
    parse_translation_pair,
    parse_angle,
    parse_numeric_list,
)

__all__ = [
    # Units
    "UnitConverter",
    "px_to_emu",
    "emu_to_px",
    "emu_to_unit",
    "ConversionContext",
    "DEFAULT_DPI",
    "EMU_PER_INCH",
    # Colors
    "color_to_hex",
    "parse_color",
    "hex_to_rgb",
    "rgb_to_hex",
    # Angles
    "degrees_to_ppt",
    "radians_to_ppt",
    "ppt_to_degrees",
    "ppt_to_radians",
    # Opacity
    "opacity_to_ppt",
    "ppt_to_opacity",
    "alpha_to_ppt",
    "ppt_to_alpha",
    # PowerPoint
    "PPTConverter",
    # Transforms
    "parse_scale_pair",
    "parse_translation_pair",
    "parse_angle",
    "parse_numeric_list",
]
```

### 2. `conversions/units.py` - Unit Conversions

```python
"""Unit conversion utilities - re-export from common.units."""

from svg2ooxml.common.units import (
    UnitConverter,
    px_to_emu,
    emu_to_px,
    emu_to_unit,
    ConversionContext,
    DEFAULT_DPI,
    EMU_PER_INCH,
    EMU_PER_CM,
    EMU_PER_MM,
    EMU_PER_POINT,
    EMU_PER_PX_AT_DEFAULT_DPI,
)

__all__ = [
    "UnitConverter",
    "px_to_emu",
    "emu_to_px",
    "emu_to_unit",
    "ConversionContext",
    "DEFAULT_DPI",
    "EMU_PER_INCH",
    "EMU_PER_CM",
    "EMU_PER_MM",
    "EMU_PER_POINT",
    "EMU_PER_PX_AT_DEFAULT_DPI",
]
```

### 3. `conversions/colors.py` - Color Conversions

```python
"""Color conversion utilities."""

from __future__ import annotations

from svg2ooxml.color.utils import color_to_hex
from svg2ooxml.color.parsers import parse_color as _parse_color

__all__ = [
    "color_to_hex",
    "parse_color",
    "hex_to_rgb",
    "rgb_to_hex",
]


def parse_color(value: str | None):
    """Parse color string to Color object."""
    return _parse_color(value)


def hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    """
    Convert hex color to RGB tuple.

    Args:
        hex_value: Hex color like "FF0000" or "#FF0000"

    Returns:
        (r, g, b) tuple with values 0-255
    """
    hex_clean = hex_value.lstrip('#')
    if len(hex_clean) != 6:
        raise ValueError(f"Invalid hex color: {hex_value}")

    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    return (r, g, b)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """
    Convert RGB to hex color (without #).

    Args:
        r, g, b: Color components 0-255

    Returns:
        Hex string like "FF0000"
    """
    return f"{r:02X}{g:02X}{b:02X}"
```

### 4. `conversions/angles.py` - Angle Conversions (NEW)

```python
"""Angle conversion utilities for PowerPoint.

PowerPoint uses 60000ths of a degree internally.
SVG/CSS typically uses degrees or radians.
"""

from __future__ import annotations

import math

# PowerPoint angle unit: 1 degree = 60000 units
PPT_ANGLE_SCALE = 60000

__all__ = [
    "degrees_to_ppt",
    "radians_to_ppt",
    "ppt_to_degrees",
    "ppt_to_radians",
    "PPT_ANGLE_SCALE",
]


def degrees_to_ppt(degrees: float) -> int:
    """
    Convert degrees to PowerPoint angle units (60000ths).

    Args:
        degrees: Angle in degrees

    Returns:
        PowerPoint angle units (int)

    Example:
        >>> degrees_to_ppt(45.0)
        2700000
        >>> degrees_to_ppt(90.0)
        5400000
    """
    return int(round(degrees * PPT_ANGLE_SCALE))


def radians_to_ppt(radians: float) -> int:
    """
    Convert radians to PowerPoint angle units (60000ths).

    Args:
        radians: Angle in radians

    Returns:
        PowerPoint angle units (int)

    Example:
        >>> radians_to_ppt(math.pi / 4)  # 45 degrees
        2700000
    """
    degrees = math.degrees(radians)
    return degrees_to_ppt(degrees)


def ppt_to_degrees(ppt_value: int) -> float:
    """
    Convert PowerPoint angle units to degrees.

    Args:
        ppt_value: PowerPoint angle units

    Returns:
        Angle in degrees

    Example:
        >>> ppt_to_degrees(2700000)
        45.0
    """
    return ppt_value / PPT_ANGLE_SCALE


def ppt_to_radians(ppt_value: int) -> float:
    """
    Convert PowerPoint angle units to radians.

    Args:
        ppt_value: PowerPoint angle units

    Returns:
        Angle in radians
    """
    degrees = ppt_to_degrees(ppt_value)
    return math.radians(degrees)
```

### 5. `conversions/opacity.py` - Opacity/Alpha Conversions (NEW)

```python
"""Opacity and alpha channel conversion utilities.

PowerPoint uses 100000ths scale (0-100000) for opacity/alpha.
SVG/CSS typically uses 0-1 scale or 0-100 percentage.
"""

from __future__ import annotations

# PowerPoint opacity/alpha unit: 1.0 = 100000 units, 0% = 100000, 100% = 0
PPT_OPACITY_SCALE = 100000

__all__ = [
    "opacity_to_ppt",
    "ppt_to_opacity",
    "alpha_to_ppt",
    "ppt_to_alpha",
    "percentage_to_ppt",
    "ppt_to_percentage",
    "PPT_OPACITY_SCALE",
]


def opacity_to_ppt(opacity: float) -> int:
    """
    Convert opacity (0-1 scale) to PowerPoint units.

    PowerPoint opacity is inverted: 100000 = fully opaque, 0 = fully transparent.

    Args:
        opacity: Opacity value 0.0-1.0 (0 = transparent, 1 = opaque)

    Returns:
        PowerPoint opacity units (0-100000)

    Example:
        >>> opacity_to_ppt(1.0)  # Fully opaque
        100000
        >>> opacity_to_ppt(0.5)  # 50% opaque
        50000
        >>> opacity_to_ppt(0.0)  # Fully transparent
        0
    """
    clamped = max(0.0, min(1.0, opacity))
    return int(round(clamped * PPT_OPACITY_SCALE))


def ppt_to_opacity(ppt_value: int) -> float:
    """
    Convert PowerPoint opacity units to 0-1 scale.

    Args:
        ppt_value: PowerPoint opacity units (0-100000)

    Returns:
        Opacity 0.0-1.0
    """
    clamped = max(0, min(PPT_OPACITY_SCALE, ppt_value))
    return clamped / PPT_OPACITY_SCALE


def alpha_to_ppt(alpha: float) -> int:
    """
    Convert alpha channel (0-1 scale) to PowerPoint units.

    This is an alias for opacity_to_ppt() as they use the same scale.

    Args:
        alpha: Alpha value 0.0-1.0 (0 = transparent, 1 = opaque)

    Returns:
        PowerPoint alpha units (0-100000)
    """
    return opacity_to_ppt(alpha)


def ppt_to_alpha(ppt_value: int) -> float:
    """
    Convert PowerPoint alpha units to 0-1 scale.

    Args:
        ppt_value: PowerPoint alpha units (0-100000)

    Returns:
        Alpha 0.0-1.0
    """
    return ppt_to_opacity(ppt_value)


def percentage_to_ppt(percentage: float) -> int:
    """
    Convert percentage (0-100) to PowerPoint opacity units.

    Args:
        percentage: Percentage 0-100

    Returns:
        PowerPoint opacity units (0-100000)

    Example:
        >>> percentage_to_ppt(100.0)  # 100% opaque
        100000
        >>> percentage_to_ppt(50.0)   # 50% opaque
        50000
    """
    return opacity_to_ppt(percentage / 100.0)


def ppt_to_percentage(ppt_value: int) -> float:
    """
    Convert PowerPoint opacity units to percentage (0-100).

    Args:
        ppt_value: PowerPoint opacity units (0-100000)

    Returns:
        Percentage 0-100
    """
    return ppt_to_opacity(ppt_value) * 100.0
```

### 6. `conversions/powerpoint.py` - PowerPoint Converter Class (NEW)

```python
"""High-level PowerPoint conversion utilities.

Combines all conversion utilities into a single convenient class.
"""

from __future__ import annotations

from .units import UnitConverter, px_to_emu, DEFAULT_DPI
from .colors import color_to_hex
from .angles import degrees_to_ppt, radians_to_ppt
from .opacity import opacity_to_ppt
from .transforms import parse_scale_pair, parse_translation_pair, parse_angle

__all__ = ["PPTConverter"]


class PPTConverter:
    """Unified PowerPoint conversion utilities."""

    def __init__(self, *, dpi: float = DEFAULT_DPI):
        """
        Initialize converter.

        Args:
            dpi: Dots per inch for unit conversions
        """
        self.dpi = dpi
        self._unit_converter = UnitConverter(dpi=dpi)

    # Units
    def px_to_emu(self, px: float, *, axis: str | None = None) -> int:
        """Convert pixels to EMU."""
        emu = self._unit_converter.to_emu(px, axis=axis)
        return int(round(emu))

    def length_to_emu(self, value: str | float, *, axis: str | None = None) -> int:
        """Convert any length value to EMU."""
        emu = self._unit_converter.to_emu(value, axis=axis)
        return int(round(emu))

    # Colors
    def color_to_hex(self, color: str | None, *, default: str = "000000") -> str:
        """Convert color to hex format."""
        return color_to_hex(color, default=default)

    # Angles
    def degrees_to_ppt(self, degrees: float) -> int:
        """Convert degrees to PowerPoint units."""
        return degrees_to_ppt(degrees)

    def radians_to_ppt(self, radians: float) -> int:
        """Convert radians to PowerPoint units."""
        return radians_to_ppt(radians)

    # Opacity
    def opacity_to_ppt(self, opacity: float) -> int:
        """Convert opacity (0-1) to PowerPoint units."""
        return opacity_to_ppt(opacity)

    # Transform parsing
    def parse_scale(self, value: str) -> tuple[float, float]:
        """Parse scale value."""
        return parse_scale_pair(value)

    def parse_translation(self, value: str) -> tuple[float, float]:
        """Parse translation value."""
        return parse_translation_pair(value)

    def parse_angle(self, value: str) -> float:
        """Parse angle value."""
        return parse_angle(value)
```

### 7. `conversions/transforms.py` - Transform Parsing (NEW)

```python
"""Transform value parsing utilities."""

from __future__ import annotations

import re

__all__ = [
    "parse_scale_pair",
    "parse_translation_pair",
    "parse_angle",
    "parse_numeric_list",
]


def parse_numeric_list(value: str) -> list[float]:
    """
    Parse space/comma-separated numeric list.

    Args:
        value: String like "1.5 2.0" or "1.5, 2.0" or "1.5,2.0"

    Returns:
        List of float values

    Example:
        >>> parse_numeric_list("1.5 2.0 3.5")
        [1.5, 2.0, 3.5]
        >>> parse_numeric_list("1.5, 2.0, 3.5")
        [1.5, 2.0, 3.5]
    """
    if not value:
        return []

    # Match numbers including scientific notation
    pattern = r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?"
    tokens = re.findall(pattern, value)

    result: list[float] = []
    for token in tokens:
        try:
            result.append(float(token))
        except ValueError:
            continue

    return result


def parse_scale_pair(value: str) -> tuple[float, float]:
    """
    Parse scale value.

    Args:
        value: Scale value like "1.5" or "1.5 2.0"

    Returns:
        (scale_x, scale_y) tuple

    Example:
        >>> parse_scale_pair("1.5")
        (1.5, 1.5)
        >>> parse_scale_pair("1.5 2.0")
        (1.5, 2.0)
    """
    numbers = parse_numeric_list(value)
    if not numbers:
        return (1.0, 1.0)
    if len(numbers) == 1:
        return (numbers[0], numbers[0])
    return (numbers[0], numbers[1])


def parse_translation_pair(value: str) -> tuple[float, float]:
    """
    Parse translation value.

    Args:
        value: Translation like "10 20" or "10,20"

    Returns:
        (dx, dy) tuple

    Example:
        >>> parse_translation_pair("10 20")
        (10.0, 20.0)
        >>> parse_translation_pair("10")
        (10.0, 0.0)
    """
    numbers = parse_numeric_list(value)
    if len(numbers) >= 2:
        return (numbers[0], numbers[1])
    if len(numbers) == 1:
        return (numbers[0], 0.0)
    return (0.0, 0.0)


def parse_angle(value: str) -> float:
    """
    Parse angle value (in degrees).

    Args:
        value: Angle like "45" or "45deg"

    Returns:
        Angle in degrees

    Example:
        >>> parse_angle("45")
        45.0
        >>> parse_angle("45deg")
        45.0
    """
    numbers = parse_numeric_list(value)
    return numbers[0] if numbers else 0.0
```

## Migration Strategy

### Phase 1: Create New Module (No Breaking Changes)
1. Create `common/conversions/` directory
2. Implement all new modules
3. Write comprehensive tests
4. Old code continues to work

### Phase 2: Update Imports (Gradual)
1. Update `animation_writer.py` to use new conversions
2. Update other files incrementally
3. Deprecate old scattered functions

### Phase 3: Cleanup
1. Remove duplicate implementations
2. Update documentation
3. Verify all tests pass

## Benefits

### Immediate
- ✅ **Single source of truth** for all conversions
- ✅ **Consistent behavior** across codebase
- ✅ **Easier to test** - centralized test suite
- ✅ **Better documentation** - one place to look

### Long-term
- ✅ **Easier maintenance** - changes in one place
- ✅ **Reduced bugs** - no duplicate logic to keep in sync
- ✅ **Better API** - unified interface for consumers
- ✅ **Extensibility** - easy to add new conversion types

## Testing Strategy

### Unit Tests

```python
# tests/unit/common/conversions/test_angles.py
def test_degrees_to_ppt():
    assert degrees_to_ppt(0.0) == 0
    assert degrees_to_ppt(45.0) == 2700000
    assert degrees_to_ppt(90.0) == 5400000
    assert degrees_to_ppt(180.0) == 10800000
    assert degrees_to_ppt(360.0) == 21600000

def test_ppt_to_degrees():
    assert ppt_to_degrees(0) == 0.0
    assert ppt_to_degrees(2700000) == 45.0
    assert ppt_to_degrees(5400000) == 90.0

# tests/unit/common/conversions/test_opacity.py
def test_opacity_to_ppt():
    assert opacity_to_ppt(1.0) == 100000  # Fully opaque
    assert opacity_to_ppt(0.5) == 50000   # 50% opaque
    assert opacity_to_ppt(0.0) == 0       # Fully transparent

def test_opacity_clamping():
    assert opacity_to_ppt(1.5) == 100000  # Clamp to 1.0
    assert opacity_to_ppt(-0.5) == 0      # Clamp to 0.0

# tests/unit/common/conversions/test_transforms.py
def test_parse_scale_pair():
    assert parse_scale_pair("1.5") == (1.5, 1.5)
    assert parse_scale_pair("1.5 2.0") == (1.5, 2.0)
    assert parse_scale_pair("1.5,2.0") == (1.5, 2.0)
    assert parse_scale_pair("") == (1.0, 1.0)

def test_parse_translation_pair():
    assert parse_translation_pair("10 20") == (10.0, 20.0)
    assert parse_translation_pair("10") == (10.0, 0.0)
    assert parse_translation_pair("") == (0.0, 0.0)
```

### Integration Tests

```python
# tests/integration/test_conversions.py
def test_ppt_converter_roundtrip():
    converter = PPTConverter()

    # Angles
    degrees = 45.0
    ppt = converter.degrees_to_ppt(degrees)
    assert ppt_to_degrees(ppt) == degrees

    # Opacity
    opacity = 0.7
    ppt = converter.opacity_to_ppt(opacity)
    assert abs(ppt_to_opacity(ppt) - opacity) < 0.0001
```

## Usage Examples

### Before (Scattered)

```python
# animation_writer.py
rotation_delta = int(round((end_angle - start_angle) * 60000))  # Magic number!

# gradient_service.py
alpha_val = int(self._clamp(color.a) * 100000)  # Magic number!

# filter_renderer.py
alpha = int(max(0.0, min(1.0, opacity)) * 100000)  # Magic number!
```

### After (Centralized)

```python
from svg2ooxml.common.conversions import (
    PPTConverter,
    degrees_to_ppt,
    opacity_to_ppt,
)

# animation_writer.py
rotation_delta = degrees_to_ppt(end_angle - start_angle)

# gradient_service.py
alpha_val = opacity_to_ppt(color.a)

# filter_renderer.py
alpha = opacity_to_ppt(opacity)

# Or using unified converter
ppt = PPTConverter()
rotation = ppt.degrees_to_ppt(45.0)
alpha = ppt.opacity_to_ppt(0.7)
emu = ppt.px_to_emu(100.0)
```

## File Organization

```
src/svg2ooxml/common/
├── units/              # Existing - no changes
│   ├── __init__.py
│   ├── conversion.py
│   ├── scalars.py
│   └── converters.py
└── conversions/        # NEW - centralized conversions
    ├── __init__.py
    ├── units.py        # Re-exports from common.units
    ├── colors.py       # Color conversions
    ├── angles.py       # NEW - angle conversions
    ├── opacity.py      # NEW - opacity/alpha conversions
    ├── powerpoint.py   # NEW - unified converter
    └── transforms.py   # NEW - transform parsing
```

## Success Criteria

1. ✅ All conversion functions centralized
2. ✅ Zero magic numbers in consuming code
3. ✅ Comprehensive test coverage (>95%)
4. ✅ Clear documentation with examples
5. ✅ All existing tests still pass
6. ✅ No breaking API changes

## Implementation Timeline

**Est. Time**: 6-8 hours

1. **Phase 1** (2-3 hours): Create new modules with tests
2. **Phase 2** (3-4 hours): Update animation_writer and other consumers
3. **Phase 3** (1 hour): Cleanup and documentation

## Notes

This centralization should be done **BEFORE** the animation writer refactoring, as the refactored code will benefit from having clean, centralized conversion utilities from day one.
