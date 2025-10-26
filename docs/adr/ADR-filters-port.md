# ADR: Filter Pipeline Port (svg2pptx → svg2ooxml)

- **Status:** In Progress
- **Date:** 2025-XX-XX
- **Owners:** svg2ooxml migration team
- **Depends on:** ADR-parser-core, ADR-geometry-ir, ADR-policy-map, ADR-uvbtc-port
- **Blocks:** ADR-visual-tests, ADR-exporter

## Context

The svg2pptx converter ships with a mature SVG filter pipeline:

- `core/filters/base.py` defines abstract filter interfaces, shared `FilterContext`,
  `FilterResult`, and utility helpers.
- `core/filters/registry.py` discovers filter implementations, matches SVG filter
  primitives to DrawingML generators, and orchestrates filter chains.
- Concrete filters live under `core/filters/{geometric,image}/` and include
  Gaussian blur, soft-edge, drop shadow, glow, saturation/tint adjustments,
  displacement maps, and composite operators.
- `FilterService` in svg2pptx converts `<filter>` definitions into DrawingML
  `<a:blipFill>` or custom effect XML and determines fallback behaviour (native vs.
  raster).
- Filter execution is coordinated with policy decisions (quality vs. performance),
  the geometry pipeline (fallbacks for complex filters), and the PPTX writer
  (embedding CustomEffects when DrawingML lacks direct analogues).

svg2ooxml currently stubs filter handling:

- `FilterService` only stores raw filter XML and returns a placeholder `CustomEffect`.
- The IR converter records filter IDs and forces bitmap fallbacks, but provides no
  real DrawingML output.
- No per-primitive processing, bounding box expansion, or policy ties exist yet.

Without parity, we cannot faithfully render blur/glow/shadow-heavy SVGs, nor can we
exercise the visual regression suite. Downstream ADRs (exporter, visual tests) depend
on a complete filter stack.

## Decision

Port the svg2pptx filter subsystem into svg2ooxml with incremental slices:

1. **Core Infrastructure**
   - Adopt `FilterContext`, `FilterResult`, error types, and abstract `Filter`
     interfaces (`filters/base.py`).
   - Embed a `FilterPipeline` dispatcher mirroring svg2pptx logic for chaining
     primitives.
   - Maintain compatibility with svg2ooxml’s DI setup (`ConversionServices`) and
     policy hooks.

2. **Registry and Discovery**
   - Port `FilterRegistry` with thread-safe registration, lookup by filter type,
     and element matching.
   - Populate registry via provider modules in `svg2ooxml.services.providers.filter_*`.
   - Ensure filters register lazily to keep startup lightweight.

3. **Primitive Implementations**
   - Phase 1: Gaussian blur, drop shadow, glow, and soft-edge (covering the
     majority of real-world filters; they map cleanly to DrawingML effects).
   - Phase 2: Remaining geometric/image filters (saturation, hue rotation, color
     matrix, displacement map, feComposite, feBlend).
   - Phase 3: Filter chain operations (filterUnits/userSpaceOnUse, primitive subregions,
     chaining multiple primitives, referencing prior results via `in` attributes).

4. **DrawingML Emission**
   - Generate actual DrawingML `<a:effectLst>` fragments or `<a:blipFill>` wrappers.
   - Provide a serialization helper that returns both effect XML and metadata
     (powerpoint compatibility, fallbacks, policy hints).
   - For unsupported primitives, emit a documented `CustomEffect` payload that can
     be consumed by the exporter for rasterization.

5. **Policy & Fallback Integration**
   - Extend `FilterService` to query policy decisions (quality levels, raster
     fallbacks). Policy modules must expose filter targets (e.g., `policy/filter.py`).
   - Update `apply_geometry_policy` / IR converter to honour filter-specific hints
     (e.g., rasterize if gaussian blur radius exceeds threshold).
   - Capture filter metadata in element `policy` blocks so downstream components
     can audit decisions.

6. **Testing & Tooling**
   - Unit tests for each filter class (parameter validation, DrawingML output).
   - Integration tests that convert SVG fixtures with known filters and compare
     emitted DrawingML to svg2pptx baselines.
   - Visual regression coverage gated behind the visual test suite once the PPTX
     writer consumes effect XML.

## Migration Plan

1. **Bootstrap Infrastructure (Week 1)**
    - Port `filters/base.py` + registry core; wire into `svg2ooxml/services/filter_service.py`.
    - Update `FilterService.resolve_effects` to call the registry pipeline instead of
      returning placeholders.
    - Add ADR-linked TODOs in filter provider modules.

2. **Priority Primitives (Weeks 2–3)**
   - Port GaussianBlur, DropShadow, OuterGlow, SoftEdge implementations with
     DrawingML emission.
   - Add unit tests mirroring svg2pptx data-driven cases.
   - Integrate with IR converter (effects lists) and update policy fallbacks.

3. **Extended Primitive Suite (Weeks 4–5)**
   - Port remaining geometric/image primitives, composite operations, and filter
     chains.
   - Handle filter coordinate spaces, primitive bounding box inflation, and
     multi-stage pipelines.

4. **Policy & Mapper Alignment (Week 6)**
   - Introduce `policy/filter.py` for quality settings (e.g., max blur radius before
     raster fallback).
  - Ensure IR metadata records filter complexity and suggests fallback modes.
   - Update DrawingML writer to inject effect fragments into slide XML.

5. **Testing & Documentation (Week 7)**
   - Expand integration fixtures (`tests/fixtures/filters/*.svg`, expected PPTX or
     DrawingML snippets).
   - Document the filter pipeline (`docs/guides/filter_pipeline.md`) including
     developer notes for adding new primitives.
   - Update ADR statuses (geometry, policy, exporter) to reference the new
     capabilities.

## Status Notes

- Bootstrap infrastructure is complete (`filters/base.py`, registry plumbing, color matrix prototype).
- Color matrix, Gaussian blur (isotropic), drop shadow, glow, displacement map, turbulence, flood, offset, morphology, component transfer, convolve matrix, merge/tile, blend/composite chaining, and lighting primitives now emit metadata and exporter hook comments while awaiting native DrawingML parity.
- FilterService records rendering strategy (`native` / `raster` / future `vector`), with configuration exposed through `configure_services(filter_strategy=...)` and policy-driven overrides (`filter` target).
- Next milestone: bring over blur/drop-shadow primitives to cover the most common effects.
- Policy modules still need a dedicated filter target; schedule alongside phase 1.
- Filter execution depends on UVBTC helpers and geometry metadata, which are already available.
- Visual regression harness remains blocked until at least the priority primitives produce DrawingML output.

## TODOs / Warnings

- Decide on raster fallback strategy for unsupported primitives (rasterize vs.
  EMF export) and document configuration.
- Ensure performance remains acceptable; consider caching parsed filters or compiled
  pipelines.
- Extend pipeline seeding to cover additional virtual inputs (BackgroundImage, FillPaint) so merge/tile/lighting operations can resolve them without warnings.
- Convert exporter hooks into concrete DrawingML or raster/vector pipelines once the renderer feature set is available.
- Validate that generated DrawingML matches PowerPoint compatibility constraints
  (some filters may need to degrade gracefully).
- Coordinate with exporter ADR so packaged PPTX embeds CustomEffects or raster
  assets when necessary.
