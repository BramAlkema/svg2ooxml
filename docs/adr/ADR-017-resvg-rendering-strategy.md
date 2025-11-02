# ADR-017: Resvg Rendering Strategy and Migration Plan

- **Status:** Accepted (in progress)
- **Date:** 2025-03-04
- **Owners:** Renderer/Exporter Group
- **Depends on:** ADR-012 (pyportresvg render refactor), ADR-filter-port, ADR-policy-map
- **Replaces:** N/A (clarifies roadmap for ADR-filter-port)

## Context

Historically, svg2pptx rendered filters and complex effects through a legacy
pipeline: attempt native DrawingML mappings, emit EMF fallbacks, and finally
rasterise the entire shape if necessary. svg2ooxml now embeds pyportresvg, which
can execute the full SVG filter/mask/clip feature set directly. We added
`render/filters.py`, mask/clip rasterisation, and service wiring (`FilterService`,
`ConversionServices`) so consumers can request resvg output.

Today’s behaviour:

- `FilterService.resolve_effects` tries native registry → (new) resvg planner →
  legacy raster path. Resvg results are currently packaged as bounded PNGs, with
  metadata describing the executed primitives.
- `ConversionTracer` records `resvg_attempt`/`resvg_success`, as well as legacy
  decisions (`filter_effect`, fallback modes). Visual baselines can be refreshed
  with `SVG2OOXML_VISUAL_FILTER_STRATEGY=resvg`.
- Legacy exporters still rely on EMF/bitmap fallbacks for unsupported primitives,
  and policy modules only partially govern the new strategy.

We need a plan to migrate off the legacy fallback while preserving fidelity and
allowing per-primitive policy overrides.

## Decision

Adopt a resvg-first rendering strategy with clear promotion/fallback rules:

1. **Native DrawingML first** – retain the existing registry so primitives with
   proven DrawingML emission remain editable.
2. **Resvg promotion second** – execute the resvg planner/executor for any
   primitive stack that cannot be expressed natively. Initial implementation
   packages resvg output as PNG; future work will emit EMF/vector equivalents
   when fidelity allows.
3. **Legacy raster as last resort** – only use the original raster adapters when
   both native and resvg promotion fail or policy explicitly forces legacy mode.

Implementation requirements:

- Track strategy decisions via `ConversionTracer` and metadata (`plan_primitives`,
  `renderer`, fallback assets).
- Surface exporter controls (`SvgToPptxExporter(filter_strategy=...)`) and policy
  overrides so callers can opt into resvg, legacy, or diagnostic modes.
- Continue recording tracer events for observability.

## Consequences

- We keep the legacy pipeline as a fallback until resvg parity is proven for all
  primitives; policies can force legacy behaviour in the interim.
- Consumers can choose resvg (or `resvg-only`) to compare output without
  disabling the legacy lane.
- Visual baselines and integration tests can run either strategy via the new
  environment flag and integration suite.

## Work Plan

> Detailed execution items live in [`docs/resvg_migration_plan.md`](../resvg_migration_plan.md).

Phase 1 – *Parity & Telemetry (complete)*
- [x] Port resvg filter/mask/clip execution (`render/filters.py`, `render/pipeline.py`).
- [x] Wire `FilterService` to try native → resvg → legacy; expose strategy toggles.
- [x] Add `tests/integration/core/test_pipeline.py` and update visual baselines.
- [x] Document resvg strategy (`docs/resvg.md`).

Phase 2 – *Promotion & Policy (complete)*
- [x] Promote simple resvg primitives (flood, blends, composites, morphology/tile,
      offset, merge, component-transfer, convolve) to EMF/vector instead of PNG
      where fidelity allows.
- [x] Extend policy rules (`filter` target) so per-primitive overrides
      (e.g., disable lighting or force raster beyond thresholds) integrate with
      the new strategy.
- [x] Ensure tracer reports include the source of each decision (strategy vs policy)
      via structured `resvg_promoted_emf` / `resvg_promotion_policy_blocked` events.

Phase 3 – *Coverage & Validation*
- [x] Complete resvg handlers for remaining primitives, including spot/distant
      lighting edge cases and turbulence stitching.
- [ ] Expand integration/visual suites with complex filters; compare resvg vs
      legacy output to quantify wins (lighting scene visual diff landed; broader
      coverage pending).
- [ ] Gather telemetry from staging runs (using the new `resvg_metrics` counters)
      to confirm resvg handles the majority of effects without regressions.

Phase 4 – *Default to resvg*
- [ ] Flip exporter default to `resvg` once parity is proven; keep legacy only as
      an opt-in fallback.
- [ ] Update documentation and release notes; retire legacy-only helpers once all
      consumers have migrated.

## Alternatives Considered

- **Immediate legacy removal** – rejected; current coverage isn’t complete, and
  downstream consumers still rely on EMF placeholders.
- **Pure raster fallback** – rejected; we would lose editable DrawingML output
  for primitives with native mappings.
- **Resvg-only release** – reserved for testing; still useful for comparing output
  but not suitable as the default yet.

## References

- ADR-012 (pyportresvg render refactor) – base rendering infrastructure.
- ADR-filter-port – filter planner migration roadmap.
- docs/resvg.md – user guide for resvg strategy controls.
- tests/integration/core/test_pipeline.py – end-to-end resvg vs. legacy tests.
