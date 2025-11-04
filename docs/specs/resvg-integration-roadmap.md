# Resvg Integration Roadmap Specification

**Feature**: Complete Resvg Integration for Native Vector Rendering
**Priority**: High
**Status**: Planning
**Created**: 2025-11-03

---

## 1. Overview

### 1.1 Problem Statement

Currently, svg2ooxml uses a hybrid rendering approach with legacy helpers for filters, shapes, paint, and text. This results in:
- Unnecessary EMF/raster fallbacks for primitives that could stay vector
- Complex maintenance burden with dual code paths
- Suboptimal fidelity for filters that have native DrawingML equivalents
- Limited telemetry on rendering quality decisions

### 1.2 Success Criteria

**Must Have**:
- ⏳ Native vector promotion for priority filter primitives (feComposite, feBlend)
- ⏳ Complete pyportresvg integration for fills, strokes, gradients, markers, masks, clips
- ⏳ Resvg-based text shaping with DrawingML fallback
- ⏳ Comprehensive telemetry for native vs. EMF/raster decisions
- ⏳ Visual regression testing infrastructure
- ⏳ Default to resvg rendering paths with monitoring

**Should Have**:
- Performance metrics for resvg vs. legacy paths
- Automatic quality scoring for rendering decisions
- Gradual rollout mechanism with feature flags

**Nice to Have**:
- Interactive visual diff viewer
- Automated fidelity benchmarking against reference browsers
- Community feedback collection system

### 1.3 Non-Goals

- ❌ Custom filter primitive implementations (use resvg's battle-tested code)
- ❌ Full CSS3 filter support beyond SVG 1.1/2.0
- ❌ Dynamic filter animations
- ❌ WebGL-based rendering

---

## 2. Technical Design

### 2.1 Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                     SVG Input                              │
│  <filter>, <text>, <path>, <gradient>, etc.               │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│                  Pyportresvg Parser                        │
│  - Parse SVG using resvg's renderer                        │
│  - Extract geometry, paint, filter outputs                 │
│  - Normalize to intermediate representation                │
└────────────────────────────────────────────────────────────┘
                            ↓
                 ┌──────────┴──────────┐
                 ↓                     ↓
┌────────────────────────┐  ┌──────────────────────┐
│  Filter Ladder         │  │  Geometry/Paint      │
│  - Analyze primitives  │  │  - Fills, strokes    │
│  - Promote to native   │  │  - Gradients         │
│  - EMF for complex     │  │  - Markers, clips    │
└────────────────────────┘  └──────────────────────┘
                 │                     │
                 └──────────┬──────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│            Rendering Decision Engine                       │
│  - Heuristics: "simple fill", "vector mask", etc.         │
│  - Telemetry: record decision + rationale                  │
│  - Fallback: EMF/raster when needed                        │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│             DrawingML Writers                              │
│  - <a:fillOverlay> for blend modes                         │
│  - <a:alphaMod> for composite                              │
│  - <p:txBody> for text                                     │
│  - <a:gradFill> for gradients                              │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│                    PPTX Output                             │
│  - Native vector shapes (preferred)                        │
│  - EMF fallback (when necessary)                           │
│  - Telemetry metadata embedded                             │
└────────────────────────────────────────────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 Filter Ladder (Phase 1)

#### 3.1.1 Priority Primitives

**feComposite**:
- **Native mapping**: `<a:alphaMod>`, `<a:alphaFloor>`, boolean operations
- **Heuristic**: Simple compositing modes (over, in, out, atop)
- **Fallback**: EMF for arithmetic operator

**feBlend**:
- **Native mapping**: `<a:fillOverlay blendMode="..."/>`
- **Heuristic**: "Simple fill" detection (solid/gradient + blend mode)
- **Supported modes**: normal, multiply, screen, darken, lighten
- **Fallback**: EMF for complex modes (color-dodge, color-burn, etc.)

**Turbulence/Lighting**:
- **Strategy**: Always EMF (pathologically complex)
- **Rationale**: No DrawingML equivalent, computational intensity

#### 3.1.2 Masking Path Promotion

**Implementation**:
```python
# Hook into boolean helpers
def promote_composite_mask(fe_composite_node, context):
    """Convert feComposite masking to vector boolean operations."""
    operator = fe_composite_node.get("operator", "over")

    if operator in {"in", "out", "atop"}:
        # Extract mask path from input
        mask_path = extract_mask_geometry(fe_composite_node)

        # Convert to DrawingML path with boolean
        if is_simple_path(mask_path):
            return create_drawingml_boolean(mask_path, operator)

    # Fallback to EMF
    return render_to_emf(fe_composite_node)
```

**Location**: `src/svg2ooxml/filters/primitives/composite.py`

#### 3.1.3 Blend Mode Mapping

**DrawingML Blend Modes** (PowerPoint Limitations):
| SVG feBlend | DrawingML | Supported |
|-------------|-----------|-----------|
| normal | normal | ✅ |
| multiply | mult | ✅ |
| screen | screen | ✅ |
| darken | darken | ✅ |
| lighten | lighten | ✅ |
| overlay | - | ❌ (EMF) |
| color-dodge | - | ❌ (EMF) |
| color-burn | - | ❌ (EMF) |
| hard-light | - | ❌ (EMF) |
| soft-light | - | ❌ (EMF) |
| difference | - | ❌ (EMF) |
| exclusion | - | ❌ (EMF) |

**Note**: PowerPoint's DrawingML only supports `normal`, `mult`, `screen`, `darken`, and `lighten`. All other blend modes require EMF fallback.

**Implementation**:
```python
BLEND_MODE_MAP = {
    "normal": "normal",
    "multiply": "mult",
    "screen": "screen",
    "darken": "darken",
    "lighten": "lighten",
    # Note: overlay, difference, exclusion NOT supported by PowerPoint
}

def map_blend_mode(svg_mode: str) -> str | None:
    """Map SVG blend mode to DrawingML, return None for unsupported."""
    return BLEND_MODE_MAP.get(svg_mode)
```

**Location**: `src/svg2ooxml/drawingml/fill_overlay.py`

---

### 3.2 Telemetry System

#### 3.2.1 Decision Tracking

**Data Structure**:
```python
@dataclass
class RenderDecision:
    """Record of a rendering decision."""
    element_type: str  # "filter", "shape", "text", etc.
    element_id: str | None
    strategy: str  # "native", "emf", "raster"
    rationale: str  # Why this decision was made
    complexity_score: float  # 0.0 = simple, 1.0 = complex
    timestamp: float  # Unix timestamp (seconds since epoch)
    context: dict[str, Any]  # Additional metadata
```

**Location**: `src/svg2ooxml/telemetry/render_decisions.py`

#### 3.2.2 Tracer Integration

**Existing Tracer Enhancement**:
```python
# In src/svg2ooxml/common/trace.py
class Tracer:
    def record_filter_decision(
        self,
        filter_id: str,
        strategy: str,
        rationale: str,
        complexity: float
    ):
        """Record filter rendering decision."""
        self.data.setdefault("filter_decisions", []).append({
            "filter_id": filter_id,
            "strategy": strategy,
            "rationale": rationale,
            "complexity": complexity,
            "timestamp": time.time(),
        })

    def get_strategy_summary(self) -> dict[str, int]:
        """Get count of native vs. EMF vs. raster."""
        decisions = self.data.get("filter_decisions", [])
        return {
            "native": sum(1 for d in decisions if d["strategy"] == "native"),
            "emf": sum(1 for d in decisions if d["strategy"] == "emf"),
            "raster": sum(1 for d in decisions if d["strategy"] == "raster"),
        }
```

#### 3.2.3 Reporting

**Output Format**:
```json
{
  "conversion_id": "abc123",
  "total_filters": 42,
  "strategy_breakdown": {
    "native": 35,
    "emf": 5,
    "raster": 2
  },
  "native_rate": 0.833,
  "top_fallback_reasons": [
    {"reason": "unsupported_blend_mode", "count": 3},
    {"reason": "complex_turbulence", "count": 2}
  ],
  "complexity_distribution": {
    "0.0-0.3": 30,
    "0.3-0.7": 8,
    "0.7-1.0": 4
  }
}
```

---

### 3.3 Shapes & Paint Swap (Phase 2)

#### 3.3.1 Pyportresvg Integration Points

**Current State**:
- Legacy helpers in `src/svg2ooxml/core/shapes/`
- Separate paint processing in `src/svg2ooxml/core/paint/`

**Target State**:
- Unified pyportresvg output → DrawingML
- Delete legacy adapters after migration

**Integration Flow** (pseudocode - actual API TBD):
```python
# Conceptual flow - actual pyportresvg API differs
def convert_shape_with_resvg(svg_element, context):
    """Convert shape using resvg geometry + paint."""
    # Actual implementation will use pyportresvg's render_to_ir() or similar
    # This is pseudocode to illustrate the concept

    # 1. Render via resvg to intermediate representation
    ir_data = render_shape_ir(svg_element)

    # 2. Extract geometry from IR
    drawingml_path = convert_ir_path_to_drawingml(ir_data.path)

    # 3. Extract paint from IR
    drawingml_fill = convert_ir_fill(ir_data.fill)
    drawingml_stroke = convert_ir_stroke(ir_data.stroke)

    # 4. Build DrawingML shape
    return build_drawingml_shape(
        path=drawingml_path,
        fill=drawingml_fill,
        stroke=drawingml_stroke
    )
```

**Location**: `src/svg2ooxml/core/resvg_integration/shape_converter.py`

#### 3.3.2 Paint Type Mapping

| Resvg Paint | DrawingML | Implementation |
|-------------|-----------|----------------|
| Solid color | `<a:solidFill>` | Direct RGB/alpha |
| Linear gradient | `<a:gradFill lin>` | Map stops + angle |
| Radial gradient | `<a:gradFill path>` | Map stops + focal |
| Pattern | EMF fallback | Too complex |
| None | `<a:noFill>` | Direct |

#### 3.3.3 Gradient Conversion

**Linear Gradient**:
```python
def convert_linear_gradient(ir_gradient):
    """Convert IR linear gradient to DrawingML.

    Note: IR uses 0.0-1.0 floats for offset/alpha.
    DrawingML uses 0-100000 for pos, 0-100000 for alpha.
    """
    stops = ir_gradient.stops
    angle = ir_gradient.angle

    drawingml_stops = []
    for stop in stops:
        # Clamp offset to [0.0, 1.0] and convert to DrawingML range
        pos = max(0, min(100000, int(stop.offset * 100000)))
        # Alpha: 0.0-1.0 → 0-100000
        alpha = max(0, min(100000, int(stop.alpha * 100000)))

        drawingml_stops.append(
            f'<a:gs pos="{pos}">'
            f'  <a:srgbClr val="{stop.color.to_hex()}">'
            f'    <a:alpha val="{alpha}"/>'
            f'  </a:srgbClr>'
            f'</a:gs>'
        )

    # Angle: degrees → 1/60000ths of a degree
    angle_drawingml = int(angle * 60000)

    return f'''
    <a:gradFill>
      <a:gsLst>
        {''.join(drawingml_stops)}
      </a:gsLst>
      <a:lin ang="{angle_drawingml}" scaled="0"/>
    </a:gradFill>
    '''
```

#### 3.3.4 Marker Handling

**Strategy**:
- Resvg exposes marker nodes separately (not automatically expanded)
- We must walk the marker tree and expand to geometry ourselves
- OR: Use resvg's render output which flattens markers to paths
- Convert expanded geometry to DrawingML paths
- Group as single shape with multiple sub-paths

**Note**: Exact approach depends on pyportresvg API capabilities - may need custom marker expansion logic.

**Location**: `src/svg2ooxml/core/resvg_integration/marker_converter.py`

---

### 3.4 Text Port (Phase 3)

#### 3.4.1 Resvg Text Shaping

**Flow**:
```
SVG <text>
  ↓
Resvg shapes text (font selection, layout, metrics)
  ↓
Extract glyph positions + font metadata
  ↓
Decision: Plain layout?
  ├─ Yes → DrawingML <p:txBody>
  └─ No → EMF fallback
```

**Plain Layout Detection**:
```python
def is_plain_text_layout(resvg_text):
    """Determine if text can be represented in DrawingML."""
    # Check for simple cases
    if resvg_text.has_path_text():
        return False  # textPath not supported

    if resvg_text.has_glyph_reuse():
        return False  # Complex glyph positioning

    if resvg_text.has_vertical_text():
        return False  # vertical-text not well-supported

    # Check transform complexity
    if not is_simple_transform(resvg_text.get_transform()):
        return False

    # Check for advanced shaping features
    # Resvg will apply kerning/ligatures automatically, but DrawingML
    # uses simplified text runs that may not preserve exact glyph positioning
    if resvg_text.has_kerning() or resvg_text.has_ligatures():
        # Only allow if glyphs remain in simple left-to-right sequence
        if not resvg_text.is_simple_horizontal_flow():
            return False

    return True
```

#### 3.4.2 DrawingML Text Generation

**Structure**:
```xml
<p:txBody>
  <a:bodyPr/>
  <a:lstStyle/>
  <a:p>
    <a:r>
      <a:rPr lang="en-US" sz="2400" b="0" i="0">
        <a:solidFill>
          <a:srgbClr val="000000"/>
        </a:solidFill>
        <a:latin typeface="Scheherazade" pitchFamily="34" charset="0"/>
      </a:rPr>
      <a:t>Hello World</a:t>
    </a:r>
  </a:p>
</p:txBody>
```

**Implementation**:
```python
def convert_resvg_text_to_drawingml(resvg_text):
    """Convert resvg text output to DrawingML paragraphs."""
    runs = resvg_text.get_runs()

    paragraphs = []
    for run in runs:
        rPr = create_run_properties(
            font_family=run.font.family,
            font_size=run.font.size,
            color=run.fill.color,
            bold=run.font.weight >= 700,
            italic=run.font.style == "italic",
        )

        paragraphs.append(
            f'<a:r>'
            f'  {rPr}'
            f'  <a:t>{escape_xml(run.text)}</a:t>'
            f'</a:r>'
        )

    return f'<p:txBody>{create_body_props()}<a:p>{"".join(paragraphs)}</a:p></p:txBody>'
```

#### 3.4.3 Font Fallback Integration

**Coordinate with Web Font System**:
- Use `FontService.resolve()` for font resolution
- If web font loaded, pass font_data to resvg
- Resvg uses loaded font for shaping
- DrawingML embeds font (existing pipeline)

**Location**: `src/svg2ooxml/core/resvg_integration/text_converter.py`

---

### 3.5 Integration & Visual Coverage (Phase 4)

#### 3.5.1 Visual Regression Testing

**Infrastructure**:
```python
# tests/visual/resvg_mode_tests.py
class ResvgVisualTests:
    """Visual regression tests in resvg-only mode."""

    @pytest.mark.visual
    def test_filter_blend_modes(self, visual_differ):
        """Test all supported blend modes render correctly."""
        svg = create_blend_mode_test_svg()

        # Convert with resvg mode
        pptx = convert_svg(svg, filter_strategy="resvg")

        # Compare against baseline
        diff = visual_differ.compare(pptx, "blend_modes_baseline.png")
        assert diff.score > 0.95, f"Visual diff score: {diff.score}"

    @pytest.mark.visual
    def test_gradient_fills(self, visual_differ):
        """Test gradient rendering fidelity."""
        svg = load_test_svg("gradients_complex.svg")
        pptx = convert_svg(svg, filter_strategy="resvg")

        diff = visual_differ.compare(pptx, "gradients_baseline.png")
        assert diff.score > 0.93
```

**Visual Differ Tool**:
- Use `Pillow` + `scikit-image` for pixel comparison
- Generate diff images highlighting changes
- Store baselines in `tests/visual/baselines/`

**Note**: This introduces a new optional dependency on `scikit-image`. Add to `pyproject.toml` extras:
```toml
[project.optional-dependencies]
visual-testing = ["scikit-image>=0.21.0", "Pillow>=10.0.0"]
```

#### 3.5.2 Real-World Deck Testing

**Test Corpus**:
1. **Figma Exports** (10 decks)
   - Design system components
   - Complex filters (shadows, glows)
   - Mixed content (shapes + text + images)

2. **Sketch Exports** (5 decks)
   - Illustration-heavy slides
   - Gradient meshes
   - Symbol overrides

3. **Adobe Illustrator** (5 decks)
   - Vector artwork
   - Complex clipping masks
   - Blend modes

**Metrics**:
- Native rendering rate (target: >80%)
- EMF fallback rate (target: <15%)
- Raster fallback rate (target: <5%)
- Visual fidelity score (target: >0.90)

**Location**: `tests/corpus/real_world_decks/`

---

### 3.6 Flip, Monitor, Clean Up (Phase 5)

#### 3.6.1 Default Flip

**Configuration Change**:
```python
# src/svg2ooxml/config/defaults.py
class RenderingDefaults:
    # OLD: filter_strategy = "legacy"
    filter_strategy: str = "resvg"  # NEW DEFAULT

    # OLD: geometry_mode = "legacy"
    geometry_mode: str = "resvg"  # NEW DEFAULT

    # Gradual rollout flag
    resvg_rollout_percentage: float = 1.0  # 100% by default
```

**Rollout Mechanism**:
```python
def should_use_resvg(user_id: str | None, rollout_pct: float) -> bool:
    """Gradual rollout based on user ID hash."""
    if rollout_pct >= 1.0:
        return True

    if user_id is None:
        return random.random() < rollout_pct

    # Deterministic based on user ID
    hash_val = int(hashlib.sha256(user_id.encode()).hexdigest(), 16)
    return (hash_val % 100) / 100.0 < rollout_pct
```

#### 3.6.2 Monitoring Dashboard

**Metrics to Track**:
```python
@dataclass
class ResvgMetrics:
    """Metrics for resvg rendering adoption."""
    total_conversions: int
    resvg_conversions: int
    legacy_conversions: int

    # Strategy breakdown
    native_rate: float
    emf_rate: float
    raster_rate: float

    # Performance
    avg_render_time_resvg: float
    avg_render_time_legacy: float

    # Quality
    avg_fidelity_score: float
    user_reported_issues: int
```

**Dashboard Queries**:
```sql
-- Native rendering rate over time
SELECT
    DATE(timestamp) as date,
    COUNT(*) as total,
    SUM(CASE WHEN strategy = 'native' THEN 1 ELSE 0 END) as native,
    SUM(CASE WHEN strategy = 'native' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as native_pct
FROM render_decisions
WHERE element_type = 'filter'
GROUP BY date
ORDER BY date DESC;
```

**Location**: `src/svg2ooxml/telemetry/dashboard.py`

#### 3.6.3 Legacy Code Retirement

**Deprecation Plan**:

**Phase 1** (Immediate):
- Mark legacy functions with `@deprecated` decorator
- Add warnings when legacy path is used
- Update documentation to recommend resvg

**Phase 2** (After 3 months, >90% resvg adoption):
- Move legacy code to `src/svg2ooxml/legacy/` directory
- Make legacy path opt-in only
- Remove from default imports

**Phase 3** (After 6 months, >95% resvg adoption):
- Delete legacy code entirely
- Final migration guide for remaining users
- Close legacy-related issues

**Files to Retire**:
```
src/svg2ooxml/core/shapes/legacy_path.py
src/svg2ooxml/core/paint/legacy_gradient.py
src/svg2ooxml/core/filters/legacy_primitives.py
src/svg2ooxml/core/text/legacy_shaping.py
```

---

## 4. Implementation Plan

### 4.1 Phase 1: Filter Ladder

**Tasks**:

1. **Implement feComposite → Boolean Helpers**
   - File: `src/svg2ooxml/core/traversal/filters/composite.py`
   - Hook masking paths into boolean operations
   - Extract mask geometry from filter input
   - Convert to DrawingML path with boolean
   - Unit tests: 15+ test cases

2. **Implement feBlend → fillOverlay**
   - File: `src/svg2ooxml/drawingml/fill_overlay.py`
   - Map blend modes to DrawingML
   - "Simple fill" heuristic detection
   - Handle gradient + blend combinations
   - Unit tests: 10+ test cases

3. **Add Telemetry System**
   - File: `src/svg2ooxml/telemetry/render_decisions.py`
   - RenderDecision dataclass
   - Tracer integration
   - JSON reporting
   - Unit tests: 5+ test cases

4. **Update Filter Strategy Router**
   - File: `src/svg2ooxml/core/filters/strategy.py`
   - Route feComposite/feBlend to native converters
   - Fallback logic for unsupported modes
   - Integration tests: 5+ test cases

**Deliverables**:
- ✅ Native feComposite/feBlend promotion
- ✅ Telemetry tracking
- ✅ 30+ unit tests
- ✅ Integration tests

**Success Metrics**:
- Native rendering rate for feComposite: >70%
- Native rendering rate for feBlend: >80%
- All tests pass
- No visual regressions

### 4.2 Phase 2: Shapes & Paint Swap

**Tasks**:

1. **Create Resvg Shape Converter**
   - File: `src/svg2ooxml/core/resvg_integration/shape_converter.py`
   - Unified shape conversion pipeline
   - Geometry extraction from resvg
   - Paint extraction (fill, stroke, gradient)
   - Unit tests: 20+ test cases

2. **Implement Gradient Converters**
   - File: `src/svg2ooxml/core/resvg_integration/gradient_converter.py`
   - Linear gradient → DrawingML
   - Radial gradient → DrawingML
   - Gradient stop mapping
   - Unit tests: 10+ test cases

3. **Implement Marker Converter**
   - File: `src/svg2ooxml/core/resvg_integration/marker_converter.py`
   - Expand markers to geometry
   - Group as sub-paths
   - Handle marker orientations
   - Unit tests: 8+ test cases

4. **Wire into DrawingML Writers**
   - Update `src/svg2ooxml/drawingml/writer.py`
   - Route through resvg converters
   - Maintain backward compatibility
   - Integration tests: 10+ test cases

**Deliverables**:
- ✅ Complete pyportresvg → DrawingML pipeline
- ✅ Gradient conversion
- ✅ Marker support
- ✅ 48+ unit tests

**Success Metrics**:
- All gradient types render correctly
- Markers render with correct orientation
- No performance regression (< 10% slowdown)
- Visual fidelity score > 0.90

### 4.3 Phase 3: Text Port

**Tasks**:

1. **Implement Plain Text Detection**
   - File: `src/svg2ooxml/core/resvg_integration/text_analyzer.py`
   - Detect simple vs. complex layouts
   - Transform complexity scoring
   - Glyph reuse detection
   - Unit tests: 12+ test cases

2. **Create DrawingML Text Generator**
   - File: `src/svg2ooxml/core/resvg_integration/text_converter.py`
   - Convert resvg text runs to DrawingML
   - Font properties mapping
   - Color/style handling
   - Unit tests: 15+ test cases

3. **Integrate with Font Service**
   - Wire into existing FontService
   - Pass loaded web fonts to resvg
   - Font embedding coordination
   - Integration tests: 8+ test cases

4. **EMF Fallback for Complex Text**
   - Detect unsupported layouts
   - Generate EMF for path text, vertical text
   - Add telemetry
   - Integration tests: 5+ test cases

**Deliverables**:
- ✅ Resvg text shaping integration
- ✅ DrawingML paragraph generation
- ✅ Font service coordination
- ✅ 40+ unit tests

**Success Metrics**:
- Plain text conversion rate > 70%
- Font rendering fidelity > 0.95
- No missing characters
- Correct font metrics

### 4.4 Phase 4: Integration & Visual Coverage

**Tasks**:

1. **Build Visual Differ Tool**
   - File: `tests/visual/differ.py`
   - Pixel-by-pixel comparison
   - Diff image generation
   - Scoring algorithm
   - Unit tests: 5+ test cases

2. **Create Visual Regression Suite**
   - File: `tests/visual/resvg_mode_tests.py`
   - Blend mode tests
   - Gradient tests
   - Text rendering tests
   - 10+ visual test cases

3. **Collect Real-World Test Corpus**
   - Gather 20 real decks (Figma, Sketch, AI)
   - Document expected fidelity
   - Store baselines
   - Metadata tracking

4. **Run Comprehensive Testing**
   - Execute visual regression suite
   - Test real-world corpus
   - Measure metrics (native rate, fidelity)
   - Generate reports

**Deliverables**:
- ✅ Visual regression infrastructure
- ✅ 10+ visual tests
- ✅ 20-deck test corpus
- ✅ Fidelity report

**Success Metrics**:
- Visual fidelity score > 0.90 across corpus
- Native rendering rate > 80%
- EMF fallback rate < 15%
- Raster fallback rate < 5%

### 4.5 Phase 5: Flip, Monitor, Clean Up

**Tasks**:

1. **Flip Default Strategy**
   - Update `src/svg2ooxml/config/defaults.py`
   - Set `filter_strategy="resvg"`
   - Set `geometry_mode="resvg"`
   - Add rollout percentage mechanism

2. **Deploy Monitoring**
   - File: `src/svg2ooxml/telemetry/dashboard.py`
   - Database schema for metrics
   - Dashboard queries
   - Alerting thresholds

3. **Gradual Rollout**
   - Deploy at 10% → 25% → 50% → 75% → 100%
   - Monitor metrics at each stage
   - Fix issues as they arise
   - Adjust thresholds

4. **Documentation Updates**
   - Update user guide for resvg mode
   - Migration guide from legacy
   - Troubleshooting section
   - API documentation

5. **Legacy Code Deprecation**
   - Add `@deprecated` decorators
   - Move to `legacy/` directory
   - Update imports
   - Deprecation warnings

**Deliverables**:
- ✅ Resvg as default
- ✅ Monitoring dashboard
- ✅ Updated documentation
- ✅ Legacy deprecation plan

**Success Metrics**:
- 100% rollout completed
- < 1% user-reported issues
- Documentation complete
- Legacy usage < 5%

---

## 5. Testing Strategy

### 5.1 Unit Tests

**Filter Ladder** (30+ tests):
- feComposite boolean mapping
- feBlend mode conversion
- Mask geometry extraction
- Telemetry recording
- Fallback logic

**Shapes & Paint** (48+ tests):
- Resvg geometry extraction
- Fill/stroke conversion
- Gradient mapping (linear, radial)
- Marker expansion
- Paint type handling

**Text Port** (40+ tests):
- Plain layout detection
- DrawingML generation
- Font property mapping
- Complex text detection
- EMF fallback triggers

**Visual Regression** (10+ tests):
- Blend mode rendering
- Gradient fidelity
- Text rendering
- Marker orientation
- Filter combinations

### 5.2 Integration Tests

**End-to-End Conversion** (25+ tests):
1. SVG with feComposite → PPTX with vector mask
2. SVG with feBlend → PPTX with fillOverlay
3. SVG with gradients → PPTX with native gradients
4. SVG with markers → PPTX with marker geometry
5. SVG with text → PPTX with DrawingML paragraphs
6. SVG with complex filters → PPTX with EMF fallback
7. Multi-slide deck → All strategies work
8. Real Figma export → High fidelity
9. Real Sketch export → High fidelity
10. Real AI export → High fidelity

### 5.3 Performance Tests

**Benchmarks**:
- Baseline: Current legacy rendering
- Resvg mode: Target < 10% slowdown
- Memory: Target < 20% increase
- Cache: Font/filter cache hit rates

**Test Cases**:
- 100-slide deck with filters
- 50-slide deck with complex gradients
- 20-slide deck with heavy text
- 10-slide deck with markers

### 5.4 Visual Tests

**Automated Visual Comparison**:
- Pixel-diff scoring (target > 0.90)
- Structural similarity (SSIM)
- Perceptual diff (CIEDE2000)

**Manual Review**:
- Designer review of 20 test decks
- Fidelity scoring (1-5 scale)
- Issue categorization

---

## 6. Monitoring & Telemetry

### 6.1 Key Metrics

**Rendering Decisions**:
- Native rate (target: >80%)
- EMF rate (target: <15%)
- Raster rate (target: <5%)

**Performance**:
- Avg conversion time
- P50/P95/P99 latency
- Memory usage

**Quality**:
- Visual fidelity score
- User-reported issues
- Regression count

### 6.2 Dashboards

**Real-Time Dashboard**:
- Current native/EMF/raster rates
- Conversion volume (last hour/day/week)
- Error rate
- Rollout percentage

**Historical Trends**:
- Native rate over time
- Performance degradation detection
- Quality score trends
- Issue velocity

**Alerting**:
- Native rate drops below 70%
- Error rate exceeds 1%
- P95 latency > 5 seconds
- Fidelity score < 0.85

### 6.3 Logging

**Structured Logs**:
```json
{
  "timestamp": "2025-11-03T10:30:00Z",
  "conversion_id": "abc123",
  "strategy": "resvg",
  "element_type": "filter",
  "element_id": "filter1",
  "decision": "native",
  "rationale": "simple_blend_mode",
  "complexity": 0.3,
  "render_time_ms": 45
}
```

---

## 7. Rollout Plan

### 7.1 Alpha Release

- Internal testing only
- Feature flag: `RESVG_MODE_ALPHA=1`
- Limited to development team
- Gather initial feedback

### 7.2 Beta Release

- 10% gradual rollout
- Monitor metrics closely
- Fix critical issues
- Expand to 25% if stable

### 7.3 Production Rollout

- 50% → 75% → 100%
- Monitor at each stage
- Pause if issues detected
- Full rollout after validation

### 7.4 Legacy Deprecation

- Phase 1: Add deprecation warnings
- Phase 2: Move to legacy/ directory
- Phase 3: Delete legacy code (if >95% adoption)

---

## 8. Success Metrics

### 8.1 Technical Metrics

- ✅ Native rendering rate > 80%
- ✅ Visual fidelity score > 0.90
- ✅ Performance regression < 10%
- ✅ Test coverage > 90%
- ✅ Zero critical bugs

### 8.2 User Metrics

- ✅ User-reported issues < 1%
- ✅ Positive feedback from designers
- ✅ Adoption rate > 95% after 3 months
- ✅ No rollback requests

### 8.3 Business Metrics

- Increase rendering quality
- Reduce "broken output" support tickets
- Enable premium features (advanced filters)
- Differentiate from competitors

---

## 9. Risks & Mitigations

### 9.1 Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Resvg API instability | High | Low | Pin resvg version, extensive testing |
| Performance regression | Medium | Medium | Benchmarking, optimization passes |
| Visual fidelity gaps | High | Medium | Comprehensive visual tests, EMF fallback |
| Legacy code removal too early | Medium | Low | Gradual deprecation, usage monitoring |

### 9.2 Operational Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Rollout issues | High | Low | Gradual rollout, rollback plan |
| Monitoring gaps | Medium | Medium | Comprehensive telemetry, alerting |
| User complaints | Medium | Low | Clear communication, fallback options |

---

## 10. Future Enhancements

### 10.1 Phase 2 Features (Post-Launch)

1. **Advanced Filter Support**
   - feTurbulence optimization
   - Lighting effects (diffuse, specular)
   - Displacement maps

2. **Interactive Visual Diff Viewer**
   - Web UI for comparing outputs
   - Slider for before/after
   - Annotation tools

3. **Automated Fidelity Benchmarking**
   - Compare against Chrome/Firefox rendering
   - Generate fidelity reports
   - Regression detection

4. **Community Feedback Collection**
   - In-app feedback widget
   - Issue categorization
   - Priority scoring

### 10.2 Integration Opportunities

- **Figma Plugin**: Direct resvg rendering preview
- **Sketch Plugin**: Same as above
- **CLI Tool**: Standalone resvg rendering
- **Cloud Service**: Rendering API

---

## 11. Appendices

### Appendix A: Blend Mode Reference

**Full Mapping Table**:
| SVG Mode | DrawingML | PowerPoint Support | Notes |
|----------|-----------|-------------------|-------|
| normal | normal | ✅ | Default |
| multiply | mult | ✅ | Darken |
| screen | screen | ✅ | Lighten |
| overlay | overlay | ✅ | Contrast |
| darken | darken | ✅ | Min |
| lighten | lighten | ✅ | Max |
| color-dodge | - | ❌ | EMF fallback |
| color-burn | - | ❌ | EMF fallback |
| hard-light | - | ❌ | EMF fallback |
| soft-light | - | ❌ | EMF fallback |
| difference | diff | ✅ | Invert |
| exclusion | exclus | ✅ | Similar to difference |

### Appendix B: Filter Complexity Scoring

**Scoring Algorithm**:
```python
def calculate_complexity(filter_node):
    """Calculate complexity score (0.0-1.0) for a filter."""
    score = 0.0

    # Number of primitives
    primitive_count = len(filter_node.children)
    score += min(primitive_count / 10.0, 0.3)

    # Unsupported primitives
    unsupported = ["feTurbulence", "feDiffuseLighting", "feSpecularLighting"]
    for primitive in filter_node.children:
        if primitive.tag in unsupported:
            score += 0.4

    # Complex attributes
    if filter_node.get("result"):
        score += 0.1  # Result chaining

    if filter_node.get("in", "").startswith("SourceAlpha"):
        score += 0.1  # Alpha channel manipulation

    # Boolean: >0.7 = complex, EMF fallback
    return min(score, 1.0)
```

### Appendix C: References

- [Resvg Documentation](https://github.com/RazrFalcon/resvg)
- [DrawingML Blend Modes Spec](https://docs.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/blend-modes)
- [SVG Filter Specification](https://www.w3.org/TR/SVG2/filters.html)
- [Pyportresvg API](https://pyportresvg.readthedocs.io/)

---

**End of Specification**

**Next Steps**:
1. Review and approve spec
2. Create implementation tasks in issue tracker
3. Assign development team
4. Set milestone dates
5. Begin Phase 1 implementation
