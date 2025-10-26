# ADR: Policy, Services, and Mapping Port

- **Status:** In Progress
- **Date:** 2025-XX-XX
- **Owners:** svg2ooxml migration team
- **Depends on:** ADR-parser-core, ADR-geometry-ir
- **Blocks:** ADR-filters-paint, ADR-text-fonts, ADR-automation

## Context

svg2pptx coordinates conversion through a policy-driven mapper and a large service graph:

- `core/policy/engine.py`, `targets.py`, and numerous `*_policy.py` files determine quality vs. performance decisions (image handling, path simplification, text fallback, etc.).
- `core/services/conversion_services.py` wires filter, gradient, pattern, font, image, and viewport services, exposing them to the parser and mapper.
- `core/map/*.py` contains the Clean Slate mapping stages that turn IR scenes into DrawingML, leveraging policy decisions and service interfaces.
- Other cross-cutting modules (`core/services/font_embedding_engine.py`, `core/filters/`, `core/batch`, etc.) rely on the policy/service infrastructure.

The current implementation couples policy evaluation, service resolution, and mapping logic tightly, making it hard to decouple features or test in isolation.

## Decision

Define clear packages in svg2ooxml and port functionality with explicit boundaries:

- **Policy Layer (`src/svg2ooxml/policy/`)**
  - `policy/engine.py` – port the policy engine, relying on dependency injection rather than global mutation.
  - `policy/targets.py` – carry over target definitions with slim enums/data classes.
  - Submodules (`policy/providers/image.py`, `policy/providers/text.py`, `policy/providers/mask.py`, etc.) mirror the legacy `*_policy.py` responsibilities.

- **Services (`src/svg2ooxml/services/`)**
  - `services/conversion.py` – replace `conversion_services.py` with a structured container that uses `services/registry.py` and `services/providers/` to register implementations.
  - `services/cache.py`, `services/setup.py`, and provider modules will host cache management, DI wiring, and provider registration documented by this ADR.
  - Service modules (font, image, filter) will be ported individually, each depending on the registry rather than global attributes.

- **Mapper (`src/svg2ooxml/map/`)**
  - `map/base.py`, `path_mapper.py`, `text_mapper.py`, etc., will be ported to mirror the Clean Slate mapper. They will consume IR models and services through well-defined interfaces.
  - `map/ir_converter.py` (already stubbed) will bridge parser outputs and mapping stages.

Refactor goals:

- Slim down massive files by splitting policies/services into cohesive modules (e.g., image policies in `policy/image.py`, text policies in `policy/text.py`).
- Replace implicit service injection with explicit setup via `services/setup.configure_services` so tests can swap implementations.
- Keep mapping logic agnostic of global state—mappers should receive services/policies via constructor parameters or registry lookups.

## Consequences

- **Pros**
  - Clear separation of concerns makes policies and services reusable across batch/API/CLI entry points.
  - Mapper code becomes easier to test, as dependencies are injected rather than mutated global attributes.
  - Future feature work (e.g., new policy targets) can slot into well-defined modules.
- **Cons**
  - Requires careful coordination with parser/geometry ADRs to maintain contract consistency.
  - Initial port might involve substantial wiring work before functionality compiles.

## Migration Plan

1. Port policy engine (`engine.py`, `targets.py`, priority policies) into `src/svg2ooxml/policy/`, splitting modules by domain if necessary.
2. Implement service container in `services/conversion.py`, with registry/provider modules to register filter, font, image, and viewport services.
3. Port critical services (font embedding, image service, filter service) to the new structure, ensuring DI works via `services/setup.py`.
4. Move mapping modules (`map/base.py`, path/text/image mappers) into `src/svg2ooxml/map/`, updating imports to use the new IR and service modules.
5. Update pipeline code (future ADR) to instantiate policies/services/mappers via the new setup routines.
6. Add regression tests per mapper (e.g., path/text, clip/mask) comparing outputs with svg2pptx baselines.

## Status Notes

- Placeholder annotations (`TODO(ADR-policy-map)`) are in place across policy providers and cache scaffolding; future ports should keep the breadcrumbs intact.
- Fallback constants live in `svg2ooxml.policy.constants`; geometry/paint metadata now share the same hints as verified by `tests/unit/map/test_styles_fallbacks.py` and IR converter baselines. Image, text, geometry, mask, and filter providers now expose sensible defaults so downstream code can consume policy decisions without stubs.
- Service wiring uses `configure_services` idempotently (`tests/unit/services/test_setup.py` covers the contract).
- Filter targets now surface rendering strategy (native/vector/raster) for blur/shadow filters, feeding `FilterService` via policy configuration.
- Outstanding work: port production-grade policy logic (image/text/geometry) and flesh out mapper specialisations (track via POLICY-34).

### Bitmap Fallback Guardrails

- Geometry fallbacks now enforce bitmap size limits before rasterising IR paths. The mapper consults two policy knobs exposed on the `geometry` target:
  - `max_bitmap_area` (defaults to `1_500_000` pixels) caps the total raster area. Values `<= 0` disable the check.
  - `max_bitmap_side` (defaults to `2048` pixels) caps the longest side. Values `<= 0` disable the check.
- When either limit is exceeded, the mapper suppresses the bitmap fallback, retains the vector geometry, and annotates IR metadata with `bitmap_suppressed`, `bitmap_limit_*`, and `bitmap_target_size` so downstream diagnostics capture the decision.
- Downstream systems can tighten or loosen these thresholds by supplying overrides via `PolicyContext(selections={"geometry": {...}})`, ensuring PPTX payload sizes stay predictable for large canvases.
