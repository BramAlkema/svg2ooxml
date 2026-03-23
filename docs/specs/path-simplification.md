# Path Simplification Specification

**Status:** Draft
**Date:** 2026-03-23

## 1. Goals

1. Replace the naive every-Nth-segment decimation in `apply_geometry_policy()` with mathematically sound simplification passes that preserve visual fidelity within configurable tolerance.
2. Reduce segment counts for complex paths (especially Figma-exported pre-flattened paths) to improve PowerPoint rendering performance and file size.
3. Detect standard geometric shapes from path data and emit DrawingML preset geometry (`<a:prstGeom>`) instead of custom geometry (`<a:custGeom>`).
4. Keep simplification opt-in via the existing policy system, with backward-compatible defaults.

## 2. Non-Goals

- Topological changes to compound paths (no merging or splitting of subpaths).
- Simplification of clip paths (handled separately).
- Runtime performance guarantees for pathological inputs (`max_segments` fallback to EMF/bitmap remains as safety valve).

## 3. Architecture

### 3.1. Pipeline Position

```
SVG parse → IR segments → coordinate transform
  → apply_geometry_policy()       ← simplification here
    → simplify_segments()         ← new
    → detect_preset_shape()       ← new
  → DrawingMLPathGenerator        ← receives simplified segments or preset hint
```

### 3.2. New Modules

- `src/svg2ooxml/common/geometry/simplify.py` — pure-geometric simplification, operates on `Point`, `LineSegment`, `BezierSegment` only.
- `src/svg2ooxml/common/geometry/shape_detect.py` — preset shape detection.

## 4. Simplification Passes

Passes execute in sequence on each subpath independently. Each receives and returns `list[SegmentType]`.

### 4.1. Pass 1: Degenerate Segment Removal

Remove segments with near-zero length.

- **Tolerance:** `epsilon` (default: 0.01 px ≈ 95 EMU)
- `LineSegment` where `length < epsilon` → remove
- `BezierSegment` where all four points within `epsilon` → remove
- If removal would empty a subpath, keep the last segment.

### 4.2. Pass 2: Bezier-to-Line Demotion

Convert `BezierSegment` to `LineSegment` when control points lie close to the chord.

- **Tolerance:** `bezier_flatness` (default: 0.5 px ≈ 4762 EMU)
- **Metric:** Max perpendicular distance from either control point to the start→end line.
- If both control points within tolerance → `LineSegment(start, end)`.

### 4.3. Pass 3: Collinear Line Merge

Merge consecutive `LineSegment`s with the same direction.

- **Tolerance:** `collinear_angle` (default: 0.5°)
- Two consecutive segments where `seg1.end ≈ seg2.start` and direction angle < tolerance → `LineSegment(seg1.start, seg2.end)`.
- Apply greedily (scan forward).

### 4.4. Pass 4: Ramer-Douglas-Peucker

Apply RDP to maximal runs of consecutive `LineSegment`s.

- **Tolerance:** `rdp_tolerance` (default: 1.0 px ≈ 9525 EMU)
- Extract point sequences from line runs, apply standard RDP, convert back.
- First/last points of closed subpaths are pinned.

### 4.5. Pass 5: Curve Fitting

Re-fit long line-segment sequences into fewer `BezierSegment`s (Schneider algorithm).

- **Trigger:** Run length > `curve_fit_min_points` (default: 8)
- **Tolerance:** `curve_fit_tolerance` (default: 1.5 px ≈ 14287 EMU)
- **Quality gate:** If fitting produces more segments than original, keep original.

### 4.6. Short-Circuit

If segment count ≤ `max_segments` after any pass, skip remaining passes.

## 5. Preset Shape Detection

After simplification, check if the path matches a DrawingML preset.

### 5.1. Candidates

Only single-subpath, closed paths. Quick reject if segment count ∉ {4, 8}.

### 5.2. Detectable Shapes

| Shape | Preset | Segments | Criteria |
|-------|--------|----------|----------|
| Rectangle | `rect` | 4 lines | Axis-aligned, perpendicular, closed |
| Rounded Rect | `roundRect` | 4 lines + 4 curves | Axis-aligned edges, quarter-circle corners |
| Ellipse/Circle | `ellipse` | 4 curves | Control points match κ=0.5522847498 approximation |

### 5.3. Tolerance

`shape_detect_tolerance` (default: 2.0 px). Intentionally looser than simplification — minor SVG authoring imprecisions shouldn't prevent recognition.

### 5.4. Output

```python
@dataclass(frozen=True)
class PresetShapeMatch:
    preset: str            # "rect", "roundRect", "ellipse"
    bounds: Rect
    corner_radius: float = 0.0
    confidence: float = 1.0
```

## 6. Policy Configuration

### 6.1. New Options (added to `_BASE_GEOMETRY`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `simplify_tolerance_px` | `float` | `1.0` | Base tolerance in px |
| `bezier_flatness_px` | `float` | `0.5` | Bezier-to-line demotion |
| `collinear_angle_deg` | `float` | `0.5` | Collinear merge angle |
| `rdp_tolerance_px` | `float` | `1.0` | RDP tolerance |
| `curve_fit_enabled` | `bool` | `True` | Enable curve fitting |
| `curve_fit_tolerance_px` | `float` | `1.5` | Curve fit tolerance |
| `curve_fit_min_points` | `int` | `8` | Min run length for fitting |
| `detect_preset_shapes` | `bool` | `True` | Enable shape detection |
| `shape_detect_tolerance_px` | `float` | `2.0` | Shape recognition tolerance |

### 6.2. Preset Overrides

| Preset | Simplify | Curve fit | Shape detect | Notes |
|--------|----------|-----------|-------------|-------|
| `high` | Off | N/A | On | No lossy simplification |
| `balanced` | On | On | On | Default |
| `low`/`speed` | On (2× tolerance) | On | On | Aggressive |
| `compatibility` | On | Off | On | No curve fitting |

### 6.3. EMU Relationship

1 px = 9525 EMU at 96 DPI. A 1.0 px tolerance ≈ 0.26 mm — below visible threshold at presentation viewing distance.

## 7. Safety Invariants

1. **Subpath preservation** — all passes split into subpaths first, process independently, reassemble in order.
2. **Closed subpath handling** — first/last points pinned in RDP and curve fitting.
3. **Fill rule safety** — no segment reversal, no subpath reordering, no winding changes.
4. **Compound path integrity** — subpath count in = subpath count out.

## 8. Metadata

Added to the `metadata` dict returned by `apply_geometry_policy()`:

| Key | Type | Description |
|-----|------|-------------|
| `simplification_passes` | `list[str]` | Passes that modified segments |
| `segments_before_simplify` | `int` | Count before |
| `segments_after_simplify` | `int` | Count after |
| `beziers_demoted` | `int` | Beziers → lines |
| `lines_merged` | `int` | Collinear merges |
| `rdp_points_removed` | `int` | RDP removals |
| `curves_fitted` | `int` | Beziers from fitting |
| `preset_shape` | `str \| None` | Matched preset |

## 9. Implementation Phases

### Phase 1: Infrastructure
- `simplify.py` with passes 1–3 (degenerate removal, bezier demotion, collinear merge).
- Wire into `apply_geometry_policy()`, replacing decimation.

### Phase 2: RDP
- Pass 4 in `simplify.py`.
- `rdp_tolerance_px` policy option.

### Phase 3: Curve Fitting
- Pass 5 (Schneider) in `simplify.py`.
- `curve_fit_*` policy options.

### Phase 4: Preset Shape Detection
- `shape_detect.py` with rect/roundRect/ellipse detectors.
- Rendering integration in `shapes_runtime.py`.

### Phase 5: Tuning
- Tune defaults against Kelvin Lawrence corpus and Figma fixtures.
- Visual regression validation.

## 10. Exit Criteria

- No regression in visual test suite with `balanced` policy.
- ≥15% average segment reduction on paths exceeding 50 segments (Kelvin Lawrence corpus).
- Rect and ellipse preset detection works on standard SVG→path conversions.
