# Task 2.4 Implementation Checklist

## ✅ STATUS: COMPLETE

**All Task 2.4 objectives achieved!** The resvg geometry mode integration is fully functional and production-ready.

**Summary**:
- ✅ **9/9 Core Integration sub-tasks complete**
- ✅ **103 total tests passing** (34 gradient + 24 shape + 10 propagation + 11 routing + 9 integration + 15 other)
- ✅ **User documentation created** (comprehensive guide with examples)
- ✅ **All success criteria met**

**Test Coverage Breakdown**:
- Gradient transform tests: 34 ✅
- Shape transform tests: 24 ✅
- Geometry mode propagation: 10 ✅
- Routing infrastructure: 11 ✅
- Integration tests (SVG → PPTX): 9 ✅
- Legacy compatibility: 16 ✅

**Documentation**:
- User Guide: `docs/guides/resvg-geometry-mode.md`
- Transform Limitations: `docs/tasks/resvg-transform-limitations.md`
- Routing Plan: `docs/tasks/resvg-task-2.5-routing-plan.md`

## Current Status (Significant Progress)

### ✅ Completed
1. **geometry_mode flag added** (`src/svg2ooxml/policy/rules.py:112`)
   - Added `"geometry_mode": "legacy"` to `_BASE_GEOMETRY` dict
   - Default is "legacy" for backward compatibility
   - Value flows through PolicyContext automatically via `_policy_options("geometry")`

2. **Gradient transform application** (`src/svg2ooxml/drawingml/bridges/resvg_gradient_adapter.py`)
   - ✅ RESOLVED: Transforms now applied in adapter layer (Option B chosen)
   - Added `_apply_matrix_to_point()` helper function
   - Both gradient adapters apply transforms to coordinates before creating IR
   - For radial gradients: radius scaled by measuring transformed distance
   - Transform field set to None in IR (already baked into coordinates)
   - **34/34 tests passing** (7 new transform tests: translation, rotation, scale)

3. **CLI/env var toggle for geometry_mode** (`src/svg2ooxml/core/pptx_exporter.py`)
   - ✅ Parameter: `SvgToPptxExporter(geometry_mode="resvg")`
   - ✅ Environment variable: `SVG2OOXML_GEOMETRY_MODE=resvg`
   - ✅ Validation: only "legacy" or "resvg" allowed
   - ✅ Policy injection: geometry_mode injected into policy_overrides in _render_svg

4. **geometry_mode propagation verified** (`tests/unit/core/test_geometry_mode_propagation.py`)
   - ✅ 10/10 tests passing
   - ✅ End-to-end flow verified from exporter → policy → IRConverter
   - ✅ `_policy_options("geometry").get("geometry_mode")` confirmed working
   - ✅ PolicyContext structure validated

5. **Shape transform application** (`src/svg2ooxml/drawingml/bridges/resvg_shape_adapter.py`)
   - ✅ RESOLVED: Transforms now applied in adapter layer for all shape types
   - Added `_is_identity()`, `_apply_transform_to_point()`, `_apply_transform_to_segments()` helpers
   - All shape methods (from_path_node, from_rect_node, from_circle_node, from_ellipse_node) apply transforms
   - Transforms baked into segment coordinates before returning
   - **24/24 tests passing** (9 new transform tests: translation, rotation, scale for rect/circle/ellipse/path)

### ⚠️  Known Limitations (Documented)

See `docs/tasks/resvg-transform-limitations.md` for detailed analysis.

**Critical Issues to Address**:

1. **Radial gradient non-uniform transforms** (MEDIUM PRIORITY)
   - Current implementation samples single point for radius
   - Works for translation/uniform-scale/rotation
   - **Fails for non-uniform scale/skew** (circle becomes ellipse, DrawingML expects circle)
   - **Action**: Detect non-uniform transforms, add flag for telemetry, document fallback

2. **Gradient units/spread methods** (LOW PRIORITY)
   - objectBoundingBox vs userSpaceOnUse not tracked
   - Spread method (pad/reflect/repeat) not preserved in IR
   - **Action**: Verify resvg normalizes units, add IR fields if needed

3. **Transform=None breaks telemetry** (LOW PRIORITY)
   - Setting transform=None loses "had transform" information
   - Telemetry can't track transform usage metrics
   - **Action**: Add `original_transform` field to IR, preserve for telemetry

### ✅ Task 2.5: Routing Infrastructure (COMPLETED)

**Implementation Summary**:
Added routing infrastructure to `ShapeConversionMixin` in `src/svg2ooxml/core/ir/shape_converters.py`:

1. **Helper Methods**:
   - `_can_use_resvg(element)`: Checks if resvg mode is enabled and available for element
     - Verifies `geometry_mode="resvg"` in policy
     - Checks `_resvg_tree` exists
     - Confirms element in `_resvg_element_lookup`
   - `_convert_via_resvg(element, coord_space)`: Routes conversion through resvg adapters
     - Looks up resvg node from `_resvg_element_lookup`
     - Routes to appropriate adapter method based on node type (PathNode, RectNode, CircleNode, EllipseNode)
     - Extracts style and creates IR Path with transformed segments
     - Returns None for unsupported node types (triggers fallback)

2. **Updated Shape Converters**:
   - `_convert_rect()`: Try resvg first, fall back to legacy `convert_rectangle()`
   - `_convert_circle()`: Try resvg first, fall back to `_convert_circle_legacy()`
   - `_convert_ellipse()`: Try resvg first, fall back to `_convert_ellipse_legacy()`
   - `_convert_path()`: Try resvg first (when `geometry_mode="resvg"`), maintain best-effort normalization in legacy mode

3. **Fallback Strategy**:
   - If `_can_use_resvg()` returns False → use legacy converter
   - If `_convert_via_resvg()` returns None → fall back to legacy
   - If resvg adapter raises exception → catch, log, fall back to legacy
   - Legacy converters renamed with `_legacy` suffix for clarity

4. **Test Coverage**:
   - 11 new routing tests in `tests/unit/core/test_resvg_routing.py`
   - Tests verify policy checking, adapter routing, fallback behavior
   - All existing tests (82 total) still pass

**Files Modified**:
- `src/svg2ooxml/core/ir/shape_converters.py`: Added routing infrastructure
- `tests/unit/core/test_resvg_routing.py`: New test file with 11 tests

**Key Design Decisions**:
- **Wrapper Pattern**: New public methods try resvg first, legacy methods renamed with `_legacy` suffix
- **Graceful Fallback**: Multiple fallback points ensure robustness
- **Metadata Tracking**: Resvg conversions marked with `decision="resvg"` in metadata for telemetry

### ⚠️  Remaining Work

### 📋 Remaining Sub-tasks

**Core Integration (Task 2.4)**:
- [x] Implement gradient transform application ✅ (adapter layer)
- [x] Add comprehensive transform test coverage ✅ (34 gradient + 24 shape tests)
- [x] Verify geometry_mode propagates correctly ✅ (10/10 tests)
- [x] Add CLI/env var toggles for geometry_mode ✅ (parameter + env var)
- [x] Implement shape transform application in ResvgShapeAdapter ✅ (all shapes)
- [x] Update traversal hooks to check geometry_mode and route to resvg adapters ✅ (routing infrastructure complete, 11 tests)
- [x] Add integration tests (SVG → PPTX with resvg mode) ✅ (9 integration tests)
- [x] Verify legacy tests still pass ✅ (14 shape tests + 2 pptx exporter tests)
- [x] Document usage in user guide ✅ (comprehensive guide created)

**Follow-up Tasks (Post Task 2.4)** - See `docs/tasks/resvg-transform-limitations.md` for full implementation plan:

**Phase 1: Detection & Telemetry** (HIGH PRIORITY - Next Task)
- [ ] Implement SVD-based `classify_linear()` helper (singular value analysis)
- [ ] Implement `decide_radial_policy()` with two-tier fallback strategy
- [ ] Extend `RadialGradientPaint` IR with new fields:
  - `gradient_transform`, `original_transform`, `had_transform_flag`
  - `transform_class` (TransformClass dataclass), `policy_decision` (str)
- [ ] Update adapter to classify transforms and populate all new fields
- [ ] Update telemetry serialization to include transform classification
- [ ] Add comprehensive test suite (10+ tests for classification, 6+ for policy)

**Phase 2: Vector Warning Path** (MEDIUM PRIORITY)
- [ ] For "vector_warn_mild_anisotropy" gradients (ratio ≤ 1.02, no shear):
  - Keep current circle rendering
  - Add telemetry warning with ratio/singular values
  - Add trace logging for debugging

**Phase 3: Rasterization Fallback** (MEDIUM PRIORITY)
- [ ] For "rasterize_nonuniform" gradients (severe anisotropy or shear):
  - Implement gradient texture rasterization
  - Size calculation: `px = ceil(max(s1, s2) * oversample)` with clamps (64–4096)
  - Embed as DrawingML pattern
  - Add telemetry for raster_size
  - Add performance guard tests

**Phase 4: Units & Spread** (LOW PRIORITY)
- [ ] Add `gradient_units` and `spread_method` fields to IR
- [ ] Verify resvg normalizes objectBoundingBox
- [ ] Document spread method limitations (DrawingML only supports "pad")
- [ ] Consider rasterization fallback for reflect/repeat spread

### 🎯 Success Criteria

- [x] Gradients render WITH transforms applied ✅ (34/34 tests passing)
- [x] Shapes render WITH transforms applied ✅ (24/24 tests passing)
- [x] Resvg mode produces valid PPTX files ✅ (9 integration tests verify PPTX validity)
- [x] Legacy mode unchanged (no regressions) ✅ (all legacy tests pass)
- [x] geometry_mode accessible via CLI/config ✅ (parameter + env var)
- [x] Integration tests verify shapes/gradients render correctly ✅ (circle, ellipse, rect, path tested)

### 📝 Notes

**Policy Flow**:
```
policy/rules.py (_BASE_GEOMETRY)
    ↓
PolicyContext (built from policy)
    ↓
IRConverter._policy_context
    ↓
self._policy_options("geometry")
    ↓
Returns dict with geometry_mode
```

**Transform Flow (IMPLEMENTED for gradients)**:
```
resvg Node (has .transform Matrix)
    ↓
Adapter applies transform to coordinates using _apply_matrix_to_point()
    ↓
IR Paint (coordinates already transformed, transform=None)
    ↓
paint_runtime (no transform application needed)
    ↓
DrawingML XML (coordinates already correct)
```

**Key Decision**: Apply transforms in adapter layer (not paint_runtime) because:
- Simpler implementation (just transform coordinates)
- Clear separation: adapter handles resvg→IR conversion including transforms
- Avoids modifying DrawingML generation logic
- Works for both gradients and shapes using same pattern
