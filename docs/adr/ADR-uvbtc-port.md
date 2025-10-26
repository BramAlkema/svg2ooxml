# ADR: Units, ViewBox, and Transform Foundation

- **Status:** In Progress
- **Date:** 2025-XX-XX
- **Owners:** svg2ooxml migration team
- **Depends on:** ADR-parser-core
- **Blocks:** ADR-geometry-ir, ADR-policy-map

## Context

svg2pptx centralises viewport handling, unit conversion, and transform math in a shared "UVBTC" layer: `core/units`, `core/viewbox`, and `core/transforms`. svg2ooxml currently has only stubs in these areas, which blocks the coordinate-system, path system, and policy-driven mapping ADRs.

Key gaps:
- `units/` lacks the fluent `UnitConverter` API with contexts, percent resolution, and EMU constants.
- `viewbox/` has no `ViewportEngine` to resolve viewBox/meet-or-slice rules.
- `transforms/` is missing decomposition/helpers required by geometry and mapping.
- Color parsing helpers (core/color) remain tied to legacy infrastructure.

Without UVBTC parity, geometry modules must re-implement ad-hoc conversions, increasing divergence and risk of numerical drift.

## Decision

Port the UVBTC foundation into svg2ooxml with clear packages and tests. Core slices are now implemented:

- `src/svg2ooxml/units/` provides the production `UnitConverter`, scalar helpers, and EMU utilities (see `tests/unit/units/test_units_conversion.py`).
- `src/svg2ooxml/viewbox/core.py` mirrors svg2pptx `ViewportEngine`, `compute_viewbox`, and preserveAspectRatio parsing (`tests/unit/viewbox/test_viewport_engine.py` cover the entry points).
- `src/svg2ooxml/transforms/` exposes immutable matrices, parser helpers, coordinate-space stacks, and decomposition utilities, with regression tests under `tests/unit/transforms/`.
- `src/svg2ooxml/color/` contains the color parsing/blending helpers consumed by gradient/pattern processors.

Remaining scope items focus on polish, optional accelerators, and documentation.

- `src/svg2ooxml/units/`
  - `conversion.py` → full `UnitConverter`, fluent API, contexts, constants.
  - `scalars.py`, `parsers.py` as needed to mirror svg2pptx helpers.
- `src/svg2ooxml/viewbox/`
  - `viewport_engine.py` (formerly `core/viewbox/core.py`) with meet-or-slice logic.
  - Strategies/enums for alignments.
- `src/svg2ooxml/transforms/`
  - Decomposition, matrix utilities, fractional EMU helpers reused across geometry.
- `src/svg2ooxml/color/`
  - Color parsing/blending utilities referenced by gradients/patterns.

These modules will expose a clean DI surface: `UnitConverter`, `ViewportEngine`, and transform helpers should accept dependency injection (no singleton state). Tests will assert parity against svg2pptx fixtures and ensure we handle edge cases (percentages, DPI, meet/slice).

## Consequences

- **Pros**
  - Geometry/path systems can rely on proven UVBTC math, reducing double-work.
  - Policies and mappers can consume shared services, enabling consistent DPI handling.
  - Improves numerical consistency, simplifying downstream regression testing.
- **Cons**
  - Porting UVBTC is sizable; we must isolate third-party dependencies (NumPy).
  - Introduces more shared infrastructure that must be maintained/typed.

## Migration Plan

1. ✔️ Port `core/units` into `src/svg2ooxml/units/`, including tests for EMU conversion, percentages, context chaining.
2. ✔️ Bring over `core/viewbox` (ViewportEngine, strategies) with coverage for meet-or-slice, aspect align.
3. ✔️ Port transform helpers (`core/transforms`) required by geometry decomposition; wire into existing matrix helpers.
4. ✔️ Introduce color parsing utilities (`core/color/parsers.py`) consumed by gradients/patterns.
5. 🔄 Update downstream ADRs (`ADR-geometry-ir`, `ADR-policy-map`) to reference the shared UVBTC modules and trim redundant TODOs.

### Implementation Slices

- **Units**: split the svg2pptx unit converter into `constants.py`, `context.py`, `parser.py`, and `converter.py` so scalar conversion lands first; gate the NumPy/numba fast paths behind optional feature flags. Mirror the regression suite from svg2pptx before swapping `parser/units/lengths.py`.
- **Transforms**: move `core.Matrix` and the transform parser into `svg2ooxml/transforms/matrix.py` and `parser.py`, then layer `coordinate_space`/`engine` as separate modules consumed by geometry. Keep decomposition helpers isolated so they can be unit-tested without pulling in geometry.
- **ViewBox**: extract viewBox parsing + preserveAspectRatio handling into `viewbox/model.py` and `parser.py`, with a scalar `engine.py` that wraps the new UnitConverter before we reintroduce svg2pptx’s vectorised batch code.
- **Adoption order**: land Units → Transforms → ViewBox, updating the parser and geometry modules incrementally after each slice so clip/mask orchestration can rely on the new services without a monolithic PR.

## Status Notes

- Optional acceleration: NumPy-backed helpers live in `ir/numpy_compat.py`. Decide whether UVBTC should expose additional vectorised paths or rely on the existing shims (`TODO(ADR-uvbtc-port)` markers remain where a fast path could land).
- Documentation: `docs/guides/geometry.md` (pending) should summarise the UVBTC API so downstream teams adopt `UnitConverter`, `ViewportEngine`, and `Matrix` consistently.
- Dependency alignment: policy/mapper ADRs now consume shared fallback constants and matrix helpers; any new ADR should refer to these modules rather than re-implement conversions.
