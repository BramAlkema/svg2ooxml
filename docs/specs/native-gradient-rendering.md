# Native Gradient Rendering Specification

**Status:** Draft
**Date:** 2026-03-24
**Context:** The gallardo.svg (281 gradients, 209 gradient-filled shapes) exposed that all gradient fills are rasterized to bitmap images instead of using native DrawingML gradient fills. This is the #1 visual fidelity gap.

## 1. Problem

In `_resvg_segments_to_path()` (`shape_converters.py:401-405`):

```python
if style.fill and not isinstance(style.fill, SolidPaint):
    if allow_bitmap_fallback:
        render_mode = FALLBACK_BITMAP
```

Any non-solid fill (including `LinearGradientPaint`, `RadialGradientPaint`) triggers bitmap rasterization. The gradient data is correctly resolved — the IR has full stop lists, coordinates, and transforms — but it never reaches the DrawingML writer.

**Impact:** 209 shapes in gallardo.svg become 144 bitmap images instead of native vector shapes with gradient fills. Results in larger file sizes, blurry rendering at different scales, and "render_mode=bitmap" debug text leaking into output.

## 2. Current Pipeline

```
SVG gradient defs → resvg tree (PaintServerNode)
  → ResvgBridge._register_paints() → gradient_service._descriptors (281 entries)
  → style_extractor._resolve_paint() → LinearGradientPaint / RadialGradientPaint
  → shape_converters: fill is not SolidPaint → FALLBACK_BITMAP
  → rasterizer → Image IR node → <p:pic> with embedded PNG
```

What should happen:

```
  → shape_converters: fill is LinearGradientPaint → FALLBACK_NATIVE
  → DrawingML writer → <a:gradFill> with <a:gsLst>
```

## 3. SVG vs DrawingML Gradient Models

### SVG Linear Gradient
```xml
<linearGradient id="g1" x1="0" y1="0" x2="100" y2="0"
                gradientUnits="userSpaceOnUse"
                gradientTransform="rotate(45)">
  <stop offset="0" stop-color="#FF0000"/>
  <stop offset="1" stop-color="#0000FF"/>
</linearGradient>
```
- Coordinates: absolute (`userSpaceOnUse`) or relative to bbox (`objectBoundingBox`)
- Direction: defined by `(x1,y1)→(x2,y2)` line
- Transform: arbitrary `gradientTransform` matrix

### DrawingML Linear Gradient
```xml
<a:gradFill rotWithShape="1">
  <a:gsLst>
    <a:gs pos="0"><a:srgbClr val="FF0000"/></a:gs>
    <a:gs pos="100000"><a:srgbClr val="0000FF"/></a:gs>
  </a:gsLst>
  <a:lin ang="0" scaled="1"/>
</a:gradFill>
```
- Stop positions: 0–100000 (percentage × 1000)
- Direction: angle in 60000ths of a degree (0 = left→right, 5400000 = top→bottom)
- No arbitrary transform — only angle + flip

### SVG Radial Gradient
```xml
<radialGradient id="g2" cx="50" cy="50" r="50" fx="30" fy="30"
                gradientUnits="objectBoundingBox">
  <stop offset="0" stop-color="white"/>
  <stop offset="1" stop-color="black"/>
</radialGradient>
```
- Center: `(cx, cy)`, radius: `r`
- Focal point: `(fx, fy)` — offset from center

### DrawingML Radial/Path Gradient
```xml
<a:gradFill>
  <a:gsLst>
    <a:gs pos="0"><a:srgbClr val="FFFFFF"/></a:gs>
    <a:gs pos="100000"><a:srgbClr val="000000"/></a:gs>
  </a:gsLst>
  <a:path path="circle">
    <a:fillToRect l="50000" t="50000" r="50000" b="50000"/>
  </a:path>
</a:gradFill>
```
- Center: defined by `fillToRect` percentages (0–100000)
- No focal point offset — `fillToRect` controls shape/position
- Stops are reversed vs SVG convention (inner → outer)

## 4. Conversion Strategy

### 4.1. Linear Gradient

1. **Extract angle** from `(x1,y1)→(x2,y2)` and `gradientTransform`:
   - Apply gradientTransform to the direction vector
   - Compute angle: `atan2(dy, dx)` → convert to DrawingML units (× 60000)

2. **Convert stops**: offset 0.0–1.0 → position 0–100000

3. **Handle `userSpaceOnUse`**: If gradient coordinates are in user space, compute the effective angle relative to the shape's bounding box.

4. **Fallback to bitmap**: If gradientTransform includes non-uniform scaling or skew that can't be represented as an angle, rasterize.

### 4.2. Radial Gradient

1. **Map center** to `fillToRect` percentages relative to shape bbox
2. **Convert stops**: reverse order (SVG outer→inner vs DrawingML inner→outer)
3. **Handle focal point**: DrawingML doesn't support offset focal points — approximate with `fillToRect` asymmetry
4. **Fallback to bitmap**: If focal point offset is large or gradientTransform is complex

### 4.3. Compatibility Classification

Not all SVG gradients can be natively represented in DrawingML. Classify each:

| Feature | Native | Fallback |
|---------|--------|----------|
| Simple angle linear | Native | — |
| Uniform-scale linear | Native (adjust angle) | — |
| Skewed/complex transform linear | — | Bitmap |
| Centered radial | Native | — |
| Off-center focal point | Approximate | Bitmap if > 20% offset |
| `spreadMethod="reflect"` | — | Bitmap |
| `spreadMethod="repeat"` | — | Bitmap |
| Gradient with opacity stops | Native (alpha channel) | — |

## 5. Implementation

### 5.1. Phase 1: Let gradients through to the writer

Remove the blanket bitmap fallback for non-solid fills:

```python
# shape_converters.py:401-405
# Before:
if style.fill and not isinstance(style.fill, SolidPaint):
    render_mode = FALLBACK_BITMAP

# After:
if style.fill and not isinstance(style.fill, (SolidPaint, LinearGradientPaint, RadialGradientPaint)):
    render_mode = FALLBACK_BITMAP
```

### 5.2. Phase 2: Emit `<a:gradFill>` in paint_runtime.py

Add gradient-to-DrawingML conversion in `paint_to_fill()`:

```python
def _linear_gradient_to_fill(paint: LinearGradientPaint, bounds: Rect) -> str:
    """Convert LinearGradientPaint to <a:gradFill> XML."""

def _radial_gradient_to_fill(paint: RadialGradientPaint, bounds: Rect) -> str:
    """Convert RadialGradientPaint to <a:gradFill> XML."""
```

### 5.3. Phase 3: Coordinate transform

Convert SVG gradient coordinates to DrawingML:
- `userSpaceOnUse`: transform through shape bounds to get relative positions
- `objectBoundingBox`: direct mapping to DrawingML percentages
- Angle extraction: flatten gradientTransform + direction vector into a single angle

### 5.4. Phase 4: Fallback classification

Add `_can_render_native_gradient(paint)` that returns `True` for simple gradients and `False` for complex ones that must be rasterized.

## 6. Files to Modify

| File | Change |
|------|--------|
| `src/svg2ooxml/core/ir/shape_converters.py` | Remove blanket bitmap fallback for gradient fills |
| `src/svg2ooxml/drawingml/paint_runtime.py` | Add `_linear_gradient_to_fill()`, `_radial_gradient_to_fill()` |
| `src/svg2ooxml/drawingml/shapes_runtime.py` | Pass shape bounds to paint renderer for coordinate mapping |
| `src/svg2ooxml/ir/paint.py` | Ensure gradient IR types carry all needed fields |

## 7. Exit Criteria

- gallardo.svg: 0 bitmap fallbacks for gradient-filled shapes
- Simple linear gradients render natively in PowerPoint
- Complex gradients (skew, repeat, focal offset) still fall back to bitmap
- No visual regression on W3C gradient test suite
- File size reduction for gradient-heavy SVGs (gallardo: ~92KB → target ~40KB)
