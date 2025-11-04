# Task 2.5: Route Traversal Hooks Through Resvg Adapters

## Status: 🔍 Planning

## Overview

This task wires the resvg adapters (completed in Tasks 2.1-2.4) into the actual conversion pipeline by adding conditional routing based on the `geometry_mode` policy flag.

## Current State Analysis

### Existing Conversion Flow (Legacy Mode)

**Entry Point**: `src/svg2ooxml/core/traversal/hooks.py:TraversalHooksMixin.convert_element()`
- Dispatches to shape-specific converters based on tag name (lines 97-105)

**Shape Converters**: `src/svg2ooxml/core/ir/shape_converters.py:ShapeConversionMixin`
- `_convert_rect()` - Delegates to `convert_rectangle()` helper
- `_convert_circle()` - Manual geometry extraction + coordinate space transforms
- `_convert_ellipse()` - Manual geometry extraction + coordinate space transforms
- `_convert_path()` - Path parsing + normalization
- `_convert_line()` - Line geometry extraction
- `_convert_polygon()` - Polygon parsing
- `_convert_polyline()` - Polyline parsing

**Key Pattern (Legacy)**:
```python
def _convert_circle(self, *, element: etree._Element, coord_space: CoordinateSpace):
    # 1. Parse SVG attributes (cx, cy, r)
    cx = _parse_float(element.get("cx"), default=0.0)
    cy = _parse_float(element.get("cy"), default=0.0)
    radius = _parse_float(element.get("r"))

    # 2. Extract style
    style = styles_runtime.extract_style(self, element)

    # 3. Get current transform matrix
    matrix = coord_space.current

    # 4. Check for optimization (uniform scale, no clip/mask)
    scale = _uniform_scale(matrix, DEFAULT_TOLERANCE)
    if scale is not None and not clip_ref and not mask_ref:
        # Fast path: create IR Circle directly
        center = matrix.transform_point(Point(cx, cy))
        return Circle(center=center, radius=radius * scale, ...)

    # 5. Fallback: convert to path with manual segment generation
    segments = _ellipse_segments(cx, cy, radius, radius)
    transformed_segments = coord_space.apply_segments(segments)
    return Path(segments=transformed_segments, ...)
```

### Target Flow (Resvg Mode)

When `geometry_mode="resvg"`, we want to:

1. **Check if resvg tree is available**
   - IRConverter stores `_resvg_tree` and `_resvg_element_lookup`
   - If not available, fall back to legacy

2. **Look up resvg node for current element**
   - Use `_resvg_element_lookup[element]` to get resvg node
   - If not found, fall back to legacy

3. **Route to appropriate resvg adapter**
   - PathNode → `ResvgShapeAdapter.from_path_node()`
   - RectNode → `ResvgShapeAdapter.from_rect_node()`
   - CircleNode → `ResvgShapeAdapter.from_circle_node()`
   - EllipseNode → `ResvgShapeAdapter.from_ellipse_node()`

4. **Convert resvg geometry to IR**
   - Adapter returns segments with transforms already applied
   - Extract paint (fill/stroke) using resvg paint bridge
   - Create IR Path object with segments

5. **Apply style and effects**
   - Still use legacy style extraction for now
   - Future: could extract directly from resvg node presentation

---

## Implementation Strategy

### Phase 1: Add Routing Infrastructure (HIGH PRIORITY)

**Goal**: Add conditional logic to shape converters without breaking legacy mode.

**Files to Modify**:
- `src/svg2ooxml/core/ir/shape_converters.py`

**Changes**:

1. **Add resvg availability check helper**:
```python
def _can_use_resvg(self, element: etree._Element) -> bool:
    """Check if resvg mode is available and enabled for this element.

    Returns:
        True if:
        - geometry_mode="resvg" in policy
        - _resvg_tree is not None
        - element has resvg node in lookup table
    """
    # Check policy
    geometry_options = self._policy_options("geometry")
    if not geometry_options or geometry_options.get("geometry_mode") != "resvg":
        return False

    # Check resvg tree exists
    if getattr(self, "_resvg_tree", None) is None:
        return False

    # Check element has resvg node
    resvg_lookup = getattr(self, "_resvg_element_lookup", {})
    if element not in resvg_lookup:
        return False

    return True
```

2. **Add resvg routing wrapper**:
```python
def _convert_with_resvg(
    self,
    *,
    element: etree._Element,
    coord_space: CoordinateSpace,
    legacy_converter: Callable,
) -> Any:
    """Route conversion through resvg adapter or fall back to legacy.

    Args:
        element: SVG element to convert
        coord_space: Current coordinate space (for legacy fallback)
        legacy_converter: Legacy converter function to call if resvg unavailable

    Returns:
        IR object (Circle, Ellipse, Path, etc.) or None
    """
    # Try resvg path first
    if self._can_use_resvg(element):
        try:
            return self._convert_via_resvg(element, coord_space)
        except Exception as e:
            # Log warning and fall back
            if self._logger:
                self._logger.warning(
                    f"Resvg conversion failed for {element.tag}, falling back to legacy: {e}"
                )

    # Fall back to legacy
    return legacy_converter(element=element, coord_space=coord_space)
```

3. **Update each shape converter**:
```python
def _convert_circle(self, *, element: etree._Element, coord_space: CoordinateSpace):
    """Convert SVG <circle> to IR.

    Routes through resvg adapter if geometry_mode="resvg", otherwise uses legacy.
    """
    return self._convert_with_resvg(
        element=element,
        coord_space=coord_space,
        legacy_converter=self._convert_circle_legacy,
    )

def _convert_circle_legacy(self, *, element: etree._Element, coord_space: CoordinateSpace):
    """Legacy circle converter (current implementation)."""
    # ... existing _convert_circle code ...
```

### Phase 2: Implement Resvg Conversion Path (HIGH PRIORITY)

**Goal**: Actually call resvg adapters and convert to IR.

**New Method**:
```python
def _convert_via_resvg(
    self,
    element: etree._Element,
    coord_space: CoordinateSpace,
) -> Any:
    """Convert element using resvg adapter.

    Args:
        element: SVG element (must have resvg node in lookup)
        coord_space: Current coordinate space (may be ignored if resvg handles transforms)

    Returns:
        IR Path object with resvg-extracted geometry
    """
    from svg2ooxml.drawingml.bridges.resvg_shape_adapter import ResvgShapeAdapter
    from svg2ooxml.core.resvg.usvg_tree import PathNode, RectNode, CircleNode, EllipseNode

    # Get resvg node
    resvg_node = self._resvg_element_lookup[element]

    # Check if it's a shape node (not group/text/etc.)
    if not isinstance(resvg_node, (PathNode, RectNode, CircleNode, EllipseNode)):
        # Not a shape, fall back to legacy
        return None

    # Convert via adapter (transforms already applied!)
    adapter = ResvgShapeAdapter()
    segments = adapter.from_node(resvg_node)

    if not segments:
        return None

    # Extract style (still use legacy for now)
    style = styles_runtime.extract_style(self, element)
    metadata = dict(style.metadata)
    self._attach_policy_metadata(metadata, "geometry")

    # Add resvg flag to metadata
    metadata["geometry_mode"] = "resvg"

    # Get clip/mask refs
    clip_ref = self._resolve_clip_ref(element)
    mask_ref, mask_instance = self._resolve_mask_ref(element)

    # Create IR Path
    path = Path(
        segments=segments,
        fill=style.fill,
        stroke=style.stroke,
        clip=clip_ref,
        mask=mask_ref,
        mask_instance=mask_instance,
        opacity=style.opacity,
        effects=style.effects,
        metadata=metadata,
        element_id=element.get("id"),
    )

    self._process_mask_metadata(path)
    self._trace_geometry_decision(element, "resvg", path.metadata)

    return path
```

### Phase 3: Gradient Routing (MEDIUM PRIORITY)

**Goal**: Route gradient extraction through resvg paint bridge.

**Current State**: Gradients extracted in `style_runtime.extract_style()`

**Future Enhancement**: Add conditional routing in style extraction:
```python
# In style_extractor.py or style_runtime.py
def extract_fill(self, element):
    if self._can_use_resvg(element):
        return self._extract_fill_via_resvg(element)
    return self._extract_fill_legacy(element)
```

This is **deferred** to a later task because:
- Style extraction is complex and spans multiple files
- Current approach (legacy style + resvg geometry) is functional
- Gradients already work via adapter when explicitly called

---

## Testing Strategy

### Unit Tests

**File**: `tests/unit/core/ir/test_shape_converters_resvg.py`

```python
"""Tests for resvg routing in shape converters."""

import pytest
from unittest import mock

class TestResvgRouting:
    """Test conditional routing based on geometry_mode."""

    def test_legacy_mode_uses_legacy_converter(self):
        """Test that geometry_mode='legacy' uses legacy converters."""
        # Mock policy to return legacy
        # Verify legacy converter called, resvg not called

    def test_resvg_mode_uses_resvg_adapter(self):
        """Test that geometry_mode='resvg' uses resvg adapters."""
        # Mock policy to return resvg
        # Mock resvg tree and lookup
        # Verify ResvgShapeAdapter called

    def test_resvg_unavailable_falls_back(self):
        """Test fallback when resvg tree missing."""
        # Set geometry_mode='resvg' but no _resvg_tree
        # Verify fallback to legacy

    def test_resvg_element_not_found_falls_back(self):
        """Test fallback when element not in resvg lookup."""
        # Set geometry_mode='resvg', provide tree
        # Element not in _resvg_element_lookup
        # Verify fallback to legacy

    def test_resvg_exception_falls_back(self):
        """Test fallback when resvg adapter raises exception."""
        # Mock adapter to raise exception
        # Verify warning logged and fallback to legacy

    def test_circle_via_resvg(self):
        """Test <circle> conversion via resvg."""
        # Full integration test with real resvg node
        # Verify segments match expected output

    def test_rect_via_resvg(self):
        """Test <rect> conversion via resvg."""
        # Full integration test

    def test_path_via_resvg(self):
        """Test <path> conversion via resvg."""
        # Full integration test

    def test_transforms_already_applied(self):
        """Test that resvg segments already have transforms baked in."""
        # Circle with transform="translate(50,100)"
        # Verify segments have translated coordinates
        # Verify coord_space transform NOT applied again

    def test_metadata_includes_geometry_mode(self):
        """Test that resvg-converted shapes have geometry_mode in metadata."""
        # Convert shape via resvg
        # Verify metadata["geometry_mode"] == "resvg"
```

### Integration Tests

**File**: `tests/integration/test_resvg_geometry_mode.py`

```python
"""Integration tests for geometry_mode='resvg' end-to-end."""

class TestResvgGeometryMode:
    """Test full SVG → PPTX conversion with resvg mode."""

    def test_simple_shapes_resvg_mode(self):
        """Test SVG with basic shapes converts via resvg."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
          <rect x="10" y="10" width="80" height="60" fill="blue"/>
          <circle cx="150" cy="50" r="30" fill="red"/>
          <ellipse cx="100" cy="150" rx="40" ry="20" fill="green"/>
        </svg>
        """
        exporter = SvgToPptxExporter(geometry_mode="resvg")
        pptx = exporter.svg_to_pptx(io.BytesIO(svg.encode()))

        # Verify PPTX created successfully
        assert pptx is not None

        # TODO: Extract and verify shapes from PPTX

    def test_transforms_applied_correctly(self):
        """Test shapes with transforms render correctly in resvg mode."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
          <circle cx="50" cy="50" r="20" transform="translate(100, 50)" fill="blue"/>
          <rect x="0" y="0" width="40" height="40" transform="rotate(45 20 20)" fill="red"/>
        </svg>
        """
        exporter = SvgToPptxExporter(geometry_mode="resvg")
        pptx = exporter.svg_to_pptx(io.BytesIO(svg.encode()))

        # Verify transforms applied (coordinates should be shifted/rotated)

    def test_gradients_work_in_resvg_mode(self):
        """Test gradients render correctly with resvg geometry."""
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
          <defs>
            <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" style="stop-color:rgb(255,255,0);stop-opacity:1" />
              <stop offset="100%" style="stop-color:rgb(255,0,0);stop-opacity:1" />
            </linearGradient>
          </defs>
          <rect x="10" y="10" width="180" height="180" fill="url(#grad1)"/>
        </svg>
        """
        exporter = SvgToPptxExporter(geometry_mode="resvg")
        pptx = exporter.svg_to_pptx(io.BytesIO(svg.encode()))

        # Verify gradient applied correctly

    def test_legacy_mode_still_works(self):
        """Test that geometry_mode='legacy' still produces correct output."""
        svg = """<svg>...</svg>"""
        exporter = SvgToPptxExporter(geometry_mode="legacy")
        pptx = exporter.svg_to_pptx(io.BytesIO(svg.encode()))

        # Verify no regressions in legacy mode
```

---

## Risks & Mitigations

### Risk 1: Coordinate Space Conflicts
**Problem**: Resvg adapters bake transforms into coordinates. Legacy code applies coord_space.current again → double transform!

**Mitigation**:
- When using resvg path, do NOT apply coord_space transforms
- Segments from resvg adapter are already in final coordinate space
- May need to adjust segment coordinate values if coord_space has viewBox scaling

### Risk 2: Style Extraction Mismatch
**Problem**: Resvg node has presentation attributes that may differ from lxml element

**Mitigation**:
- Continue using legacy style extraction for Phase 1-2
- Verify gradient references resolve correctly
- Future: extract style directly from resvg node presentation

### Risk 3: Clip/Mask Handling
**Problem**: Resvg may have already applied clips/masks, but legacy code tries to apply them again

**Mitigation**:
- Check if resvg node has clip/mask applied
- May need to skip legacy clip/mask refs when using resvg geometry
- Document in metadata which clips were resvg-applied vs legacy-applied

### Risk 4: Performance Regression
**Problem**: Resvg lookup + adapter call might be slower than legacy for simple shapes

**Mitigation**:
- Add telemetry to measure conversion time (resvg vs legacy)
- Consider caching resvg adapter instance
- Profile with real-world SVGs

---

## Success Criteria

- [ ] `_can_use_resvg()` helper correctly checks policy + availability
- [ ] `_convert_with_resvg()` wrapper handles fallback gracefully
- [ ] All shape converters route through wrapper (rect, circle, ellipse, path, line, polygon, polyline)
- [ ] Unit tests verify conditional routing (8+ tests)
- [ ] Integration tests verify end-to-end SVG → PPTX (4+ tests)
- [ ] Legacy mode regression tests pass (no changes to legacy output)
- [ ] Resvg mode produces valid PPTX files
- [ ] Transforms applied correctly (no double-transform bug)
- [ ] Telemetry captures geometry_mode in metadata

---

## Open Questions

1. **Should coord_space be passed to resvg path?**
   - Resvg segments already have transforms applied
   - But may need viewBox scaling from coord_space?
   - **Decision**: Ignore coord_space.current matrix, but may need to apply viewBox scaling

2. **How to handle hybrid cases?**
   - Element in resvg tree but unsupported node type (e.g., TextNode)
   - **Decision**: Fall back to legacy for unsupported types

3. **Should we expose resvg adapter errors to user?**
   - Currently log warning and fall back silently
   - **Decision**: Log at WARNING level, add to telemetry, continue silently

4. **When to implement gradient routing?**
   - Current plan: defer to Phase 3
   - **Decision**: Complete shape routing first, gradients are working via current approach

---

## Next Steps

1. **Implement Phase 1** (routing infrastructure)
   - Add helpers to `shape_converters.py`
   - Update shape converter methods to use wrapper
   - Ensure legacy mode unaffected

2. **Implement Phase 2** (_convert_via_resvg)
   - Call ResvgShapeAdapter
   - Create IR Path from segments
   - Handle clip/mask/style

3. **Write unit tests**
   - Routing logic tests
   - Fallback behavior tests
   - Mock-based tests

4. **Write integration tests**
   - End-to-end SVG → PPTX
   - Compare legacy vs resvg output
   - Verify transforms/gradients work

5. **Update documentation**
   - User guide: how to enable resvg mode
   - Developer docs: routing architecture
   - Known limitations

---

## References

- Task 2.1: ResvgShapeAdapter implementation
- Task 2.2: Gradient adapter implementation
- Task 2.4: Transform application + policy toggle
- `src/svg2ooxml/core/ir/shape_converters.py` - Current shape converters
- `src/svg2ooxml/drawingml/bridges/resvg_shape_adapter.py` - Resvg shape adapter
- `docs/tasks/resvg-transform-limitations.md` - Transform limitations
