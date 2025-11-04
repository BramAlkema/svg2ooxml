# Resvg Geometry Mode User Guide

## Overview

The **resvg geometry mode** is an alternative geometry extraction pipeline that uses the [resvg](https://github.com/RazrFalcon/resvg) library to parse and convert SVG shapes to PowerPoint (DrawingML) format. This mode provides improved accuracy for complex transforms and precise geometry handling.

## Features

- **Accurate Transform Application**: Transforms (translate, rotate, scale) are fully applied during conversion
- **Consistent Coordinate System**: Uses resvg's normalized coordinate system for reliable geometry
- **Shape Support**: Handles circles, ellipses, rectangles, and paths with transforms
- **Graceful Fallback**: Automatically falls back to legacy mode if conversion fails

## When to Use Resvg Mode

**Use resvg mode when:**
- Working with SVGs that have complex transforms (rotation, scaling, translation)
- Requiring pixel-perfect geometry conversion
- Converting SVGs from design tools (Figma, Sketch, Adobe XD)
- Need consistent handling of viewBox and coordinate transformations

**Use legacy mode when:**
- Working with simple, untransformed SVGs
- Maximum backward compatibility is required
- Troubleshooting geometry issues (compare outputs)

## How to Enable

### Method 1: Parameter (Recommended)

Pass `geometry_mode="resvg"` to the `SvgToPptxExporter` constructor:

```python
from svg2ooxml.core.pptx_exporter import SvgToPptxExporter

# Enable resvg geometry mode
exporter = SvgToPptxExporter(geometry_mode="resvg")

# Convert SVG to PPTX
result = exporter.convert_string(svg_content, "output.pptx")
```

### Method 2: Environment Variable

Set the `SVG2OOXML_GEOMETRY_MODE` environment variable:

```bash
export SVG2OOXML_GEOMETRY_MODE=resvg
python your_script.py
```

```python
from svg2ooxml.core.pptx_exporter import SvgToPptxExporter

# Will use resvg mode from environment variable
exporter = SvgToPptxExporter()
result = exporter.convert_string(svg_content, "output.pptx")
```

**Note**: Parameter takes precedence over environment variable.

### Method 3: Default (Legacy Mode)

If neither parameter nor environment variable is set, the default is `geometry_mode="legacy"`:

```python
from svg2ooxml.core.pptx_exporter import SvgToPptxExporter

# Uses legacy mode by default
exporter = SvgToPptxExporter()
```

## Supported Shapes

The following SVG elements are fully supported in resvg mode:

| Element | Support | Notes |
|---------|---------|-------|
| `<rect>` | ✅ Full | Includes rounded corners (rx/ry) |
| `<circle>` | ✅ Full | Transforms applied to center and radius |
| `<ellipse>` | ✅ Full | Transforms applied to center and radii |
| `<path>` | ✅ Full | All path commands supported |
| `<line>` | ⚠️ Fallback | Falls back to legacy mode |
| `<polygon>` | ⚠️ Fallback | Falls back to legacy mode |
| `<polyline>` | ⚠️ Fallback | Falls back to legacy mode |

**Note**: Shapes not explicitly supported by resvg adapters automatically fall back to legacy conversion.

## Transform Support

Resvg mode applies transforms **before** creating DrawingML geometry:

```python
# Example: Rotated rectangle with scale
svg = """
<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'>
  <rect x='50' y='50' width='100' height='60'
        transform='rotate(45 100 80) scale(1.5)'
        fill='#3498DB'/>
</svg>
"""

exporter = SvgToPptxExporter(geometry_mode="resvg")
result = exporter.convert_string(svg, "rotated-rect.pptx")
# ✅ Transform is baked into geometry coordinates
```

### Supported Transforms

| Transform | Support | Example |
|-----------|---------|---------|
| `translate(x,y)` | ✅ Full | `translate(50,100)` |
| `rotate(angle)` | ✅ Full | `rotate(45)` |
| `scale(sx,sy)` | ✅ Full | `scale(2,1.5)` |
| `matrix(...)` | ✅ Full | `matrix(a,b,c,d,e,f)` |
| `skewX(angle)` | ✅ Full | `skewX(30)` |
| `skewY(angle)` | ✅ Full | `skewY(15)` |

**Note**: All transforms are applied to segment coordinates before creating DrawingML. The resulting PPTX shapes have identity transforms.

## Known Limitations

### 1. Radial Gradients with Non-Uniform Transforms

**Issue**: Radial gradients with non-uniform scale or skew transforms may render incorrectly.

```python
# ❌ May render incorrectly
svg = """
<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'>
  <defs>
    <radialGradient id='grad'>
      <stop offset='0%' stop-color='red'/>
      <stop offset='100%' stop-color='blue'/>
    </radialGradient>
  </defs>
  <circle cx='100' cy='100' r='50' fill='url(#grad)'
          transform='scale(2,1)'/>  <!-- Non-uniform scale -->
</svg>
"""
```

**Why**: DrawingML only supports circular radial gradients, but non-uniform transforms turn circles into ellipses.

**Workaround**: See [resvg-transform-limitations.md](../tasks/resvg-transform-limitations.md) for detection and fallback strategies (planned for future release).

### 2. Gradient Units and Spread Methods

**Issue**: `gradientUnits` (objectBoundingBox vs userSpaceOnUse) and `spreadMethod` (pad/reflect/repeat) are not tracked in IR.

**Impact**: Gradients may render differently if they rely on these attributes.

**Status**: Low priority - most gradients use default values that work correctly.

### 3. Shape-Specific IR Objects

**Behavior**: Resvg mode converts all shapes to `Path` objects with segments, even simple circles and rectangles.

**Impact**:
- Legacy mode may produce native `Circle` or `Rectangle` IR objects
- Resvg mode always produces `Path` with Bezier segments
- Output is visually identical but IR structure differs

**Why**: Resvg provides normalized path data, which is converted to segments. This ensures transforms are correctly applied.

## Comparison: Resvg vs Legacy Mode

| Aspect | Resvg Mode | Legacy Mode |
|--------|------------|-------------|
| **Transform Handling** | Fully applied to coordinates | Applied via DrawingML transform |
| **Coordinate System** | Resvg normalized | Manual SVG parsing |
| **Shape Output** | Always `Path` segments | May use `Circle`, `Rectangle`, etc. |
| **Accuracy** | High (resvg library) | Moderate (manual extraction) |
| **Fallback** | Yes (to legacy) | N/A |
| **Performance** | Slightly slower | Faster |

## Verification and Testing

### Check if Resvg Mode is Active

```python
exporter = SvgToPptxExporter(geometry_mode="resvg")
result = exporter.convert_string(svg_content, "output.pptx")

# Check trace report for resvg usage
trace = result.trace_report
print(trace.get("resvg_metrics", {}))
```

### Compare Outputs

```python
from svg2ooxml.core.pptx_exporter import SvgToPptxExporter

svg = "<svg>...</svg>"

# Convert with resvg mode
exporter_resvg = SvgToPptxExporter(geometry_mode="resvg")
exporter_resvg.convert_string(svg, "output-resvg.pptx")

# Convert with legacy mode
exporter_legacy = SvgToPptxExporter(geometry_mode="legacy")
exporter_legacy.convert_string(svg, "output-legacy.pptx")

# Open both in PowerPoint to compare
```

## Troubleshooting

### Issue: Shapes Not Converting

**Symptoms**: Shapes missing from output PPTX

**Solution**:
1. Check if shape type is supported (see Supported Shapes table)
2. Verify SVG is valid (use an SVG validator)
3. Check logs for resvg adapter errors
4. Try legacy mode to isolate issue

```python
import logging
logging.basicConfig(level=logging.DEBUG)

exporter = SvgToPptxExporter(geometry_mode="resvg")
# Check debug logs for conversion details
```

### Issue: Unexpected Geometry

**Symptoms**: Shapes render in wrong position/size/rotation

**Possible Causes**:
- ViewBox scaling issue
- Transform not applied correctly
- Coordinate system mismatch

**Solution**:
1. Compare with legacy mode output
2. Check SVG viewBox and transform attributes
3. Report issue with minimal SVG example

### Issue: Gradients Render Incorrectly

**Symptoms**: Gradient colors/direction wrong

**Cause**: Likely non-uniform transform on radial gradient (see Known Limitations)

**Solution**:
- Use linear gradients instead
- Avoid non-uniform scale on radial gradients
- Wait for transform detection feature (planned)

## Migration Guide

### Switching from Legacy to Resvg

1. **Test with Sample SVGs**: Start with a few representative SVGs

```python
# Before
exporter = SvgToPptxExporter()  # Legacy mode (default)

# After
exporter = SvgToPptxExporter(geometry_mode="resvg")
```

2. **Compare Outputs**: Verify PPTX files look identical

3. **Monitor Logs**: Check for fallback warnings

4. **Gradual Rollout**: Deploy to production gradually

### Environment-Specific Configuration

```python
import os

# Development: Use resvg for testing
if os.getenv("ENVIRONMENT") == "development":
    geometry_mode = "resvg"
else:
    geometry_mode = "legacy"

exporter = SvgToPptxExporter(geometry_mode=geometry_mode)
```

## Performance Considerations

- **Resvg mode**: Slightly slower due to resvg library overhead (~5-10%)
- **Legacy mode**: Faster but less accurate for transformed shapes
- **Recommendation**: Use resvg mode unless performance is critical

## Future Enhancements

The following features are planned for future releases:

1. **Radial Gradient Transform Detection** (High Priority)
   - Detect non-uniform transforms using SVD
   - Automatically rasterize problematic gradients
   - See [resvg-transform-limitations.md](../tasks/resvg-transform-limitations.md)

2. **Gradient Units/Spread Support** (Low Priority)
   - Track `gradientUnits` in IR
   - Support `spreadMethod` (reflect/repeat)

3. **Native Shape Optimization** (Low Priority)
   - Detect simple shapes and use native IR types
   - Reduce PPTX file size

## Related Documentation

- [Resvg Integration Roadmap](../specs/resvg-integration-roadmap.md)
- [Transform Limitations](../tasks/resvg-transform-limitations.md)
- [Task 2.4 Checklist](../tasks/resvg-task-2.4-checklist.md)
- [Resvg Integration Tasks](../tasks/resvg-integration-tasks.md)

## Support

For issues or questions:
1. Check this guide and related documentation
2. Search existing GitHub issues
3. Create a new issue with minimal reproducible example

## Changelog

- **2025-01**: Initial release of resvg geometry mode
  - Support for rect, circle, ellipse, path with transforms
  - CLI and environment variable configuration
  - Graceful fallback to legacy mode
