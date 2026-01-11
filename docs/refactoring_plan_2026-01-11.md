# Refactoring Plan
Date: 2026-01-11

## Scope
This plan captures refactoring recommendations and an execution roadmap for the
svg2ooxml codebase. The focus is on reducing coupling, improving modularity,
and making the conversion pipeline easier to reason about and test.

## Current Pipeline (today)
- Parse: `core.parser.svg_parser.SVGParser`
- IR conversion: `ir.entrypoints.convert_parser_output` -> `core.ir.converter.IRConverter`
- DrawingML rendering: `drawingml.writer.DrawingMLWriter`
- Packaging: `io.pptx_writer.PPTXPackageBuilder`

## Goals
- Clarify the primary parse -> IR -> DrawingML -> PPTX pipeline.
- Reduce dynamic import indirection and stringly-typed wiring.
- Split large modules into focused collaborators.
- Keep changes bisectable and testable.

## Proposed PR Slices
Each slice is intended to be reviewable and independently releasable.

### PR1: Service registry unification (small, low risk)
- Purpose: eliminate duplicate provider registries and reduce import side effects.
- Scope:
  - Merge provider registry logic in:
    - src/svg2ooxml/services/registry/__init__.py
    - src/svg2ooxml/services/providers/registry.py
  - Update service wiring in src/svg2ooxml/services/setup.py to use the unified API.
  - Add a small typed shim for service keys to reduce stringly-typed access in
    src/svg2ooxml/services/conversion.py.
- Expected impact: simpler service wiring, fewer hidden imports, clearer DI surface.
- Tests: tests/unit/services/test_setup.py, tests/unit/services/test_filter_service.py

### PR2: ConversionContext builder (small/medium, low risk)
- Purpose: ensure consistent wiring between CLI/API/tests without duplication.
- Scope:
  - Introduce a ConversionContext (services + policy + unit converter + style resolver).
  - Refactor entrypoints and parser wiring:
    - src/svg2ooxml/ir/entrypoints.py
    - src/svg2ooxml/core/parser/svg_parser.py
    - src/svg2ooxml/core/parser/preprocess/services.py
- Expected impact: fewer ad-hoc service/policy decisions and easier testing setup.
- Tests: tests/unit/core/test_pipeline.py, tests/unit/core/parser/*

### PR3: Filter subsystem split (medium, moderate risk)
- Purpose: separate planning, registry, and output concerns for filters.
- Scope:
  - Split FilterService responsibilities into focused modules:
    - FilterRegistry (registration + lookup)
    - FilterPlanner (resvg planning)
    - FilterRenderer (raster/vector output)
  - Keep FilterService as a thin facade.
  - Relevant files:
    - src/svg2ooxml/services/filter_service.py
    - src/svg2ooxml/filters/registry.py
    - src/svg2ooxml/filters/resvg_bridge.py
- Expected impact: easier maintenance and clearer strategy selection.
- Tests: tests/unit/services/test_filter_*, tests/integration/test_filter_*

### PR4: IRConverter decomposition (large, higher risk)
- Purpose: reduce IR conversion complexity and make state flow explicit.
- Scope:
  - Split src/svg2ooxml/core/ir/converter.py into smaller components:
    - core/ir/context.py (state + tracer)
    - core/ir/resource_tracker.py (clip/mask/marker/symbol usage)
    - core/ir/resvg_bridge.py (lookup + normalization helpers)
    - core/ir/text_pipeline.py and core/ir/shape_pipeline.py
  - Replace mixins with composition.
- Expected impact: smaller test targets and clearer boundaries between traversal, styling, and text/shape handling.
- Tests: tests/unit/core/ir/*, tests/unit/core/resvg/*

### PR5: DrawingML writer split (medium, moderate risk)
- Purpose: reduce the size of DrawingMLWriter and isolate domain-specific rendering.
- Scope:
  - Extract focused renderers from src/svg2ooxml/drawingml/writer.py:
    - DrawingMLTextRenderer
    - DrawingMLShapeRenderer
    - MaskPipeline
    - AnimationPipeline
  - Keep DrawingMLWriter as coordinator and template holder.
- Expected impact: easier additions to text/shape support and reduced regression risk.
- Tests: tests/unit/drawingml/*, tests/unit/map/*

### PR6: PPTX packaging split (medium, moderate risk)
- Purpose: isolate file IO and relationship bookkeeping from slide assembly.
- Scope:
  - Separate slide assembly from packaging in src/svg2ooxml/io/pptx_writer.py:
    - SlideAssembler
    - PackageWriter
    - PackagingContext stays focused on IDs and filenames
- Expected impact: easier unit testing for each stage and clearer reuse for multi-slide workflows.
- Tests: tests/unit/io/test_pptx_writer.py, tests/unit/io/test_pptx_required_parts.py

### PR7: Public API and shim cleanup (medium, higher coordination)
- Purpose: limit public API surface and reduce import-time indirection.
- Scope:
  - Deprecate or remove shim re-exports:
    - src/svg2ooxml/map/converter/__init__.py
    - src/svg2ooxml/parser/__init__.py
    - src/svg2ooxml/geometry/__init__.py
  - Introduce a curated public API surface (e.g. src/svg2ooxml/public.py).
- Expected impact: faster imports, clearer boundaries for new modules.
- Tests: smoke + import tests

## Recommended Order
1. PR1: Registry unification
2. PR2: ConversionContext builder
3. PR3: Filter subsystem split
4. PR4: IRConverter decomposition
5. PR5: DrawingML writer split
6. PR6: PPTX packaging split
7. PR7: Public API/shim cleanup

## Success Criteria
- Clear single pipeline entrypoints for CLI/API.
- Reduced cross-layer imports (core should not depend on drawingml).
- Fewer runtime import redirects for public APIs.
- All tests pass with no new skips.
