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

### Native promotion targets (Figma baseline)

To reach parity for the “everyday” effects produced by Figma exports we will
build explicit DrawingML emitters for the primitives below. The intent is to
keep the chain editable whenever PowerPoint provides a matching construct.

1. **`feComposite` operators**
   - `over`: splice the upstream `<a:effectLst>` fragments without introducing
     a fallback. When both inputs provide effect lists, concatenate them and
     preserve result metadata (`pipeline_state`) so downstream primitives can
     reuse the merged fragment.
   - `in`, `out`, `atop`, `xor`: implement these as alpha masks on top of the
     combined effect using DrawingML alpha primitives (`<a:alphaBiLevel>`,
     `<a:alphaModFix>`, `<a:blend>`). Fall back to EMF only when the mask input
     is missing.
   - `arithmetic`: remains a fallback path (policy can promote later), but
     make sure the metadata records the coefficients for telemetry.
   - Implementation lives in `src/svg2ooxml/filters/primitives/composite.py`
     with helpers under `src/svg2ooxml/drawingml/filter_renderer.py` to merge
     multiple `<a:effectLst>` payloads and propagate source metadata.

2. **`feBlend` modes**
   - `normal`: identical to `over`; merge the two effect lists directly.
   - `multiply`, `screen`, `lighten`, `darken`: emit `<a:fillOverlay>` with the
     corresponding `blend` attribute (`mult`, `screen`, `lighten`, `darken`) and
     a `<a:srgbClr>` that reflects the second input’s colour when available.
   - Any unsupported mode continues to fall back to EMF, but metadata should
     record the requested mode and the source effect IDs.
   - Code entry point: new DrawingML builder in
     `src/svg2ooxml/filters/primitives/blend.py` with renderer support to turn
     the placeholder into real XML (`filter_renderer._build_blend`).

3. **`feFlood` / `feOffset` propagation**
   - When a flood feeds directly into composite/blend primitives, bubble its
     colour/opacity metadata forward so the final effect retains the same
     `<a:solidFill>` definition (no redundant fallback assets).
   - Offsets that remain in the vector path should surface their EMU offsets on
     the merged effect (use `<a:outerShdw>` with zero blur as today, but ensure
     composite/blend export keeps the offset instead of replacing it with a
     comment).

#### Hybrid eligibility rules

We will only emit native DrawingML when the inputs satisfy strict predicates;
otherwise resvg continues to produce EMF (or raster) fallbacks. This keeps the
output editable without sacrificing fidelity.

- **Simple fill (blend “top” input)** — solid or gradient fill, optional stroke,
  no nested effects, no image/pattern fills, and no references to prior filter
  results. If this test fails, the blend remains EMF.
- **Crisp mask (composite mask input)** — geometry-only mask with binary alpha
  (no blur/soft edges, no images). Allowed primitives include path geometry,
  optional hard threshold `feComponentTransfer`. Anything else falls back to EMF.
- **Boolean success** — path operations (intersect/subtract) must succeed and
  produce non-empty geometry; degeneracies trigger EMF.

Telemetry counters (e.g., `composite_in_vector`, `blend_emf_top_complex`) record
why a primitive stayed vector or fell back so we can tune heuristics later.

These builders require additions to the promotion table in
`src/svg2ooxml/services/filter_service.py` so resvg promotions can select the
native path whenever the upstream fragments have already been converted to
DrawingML. Tests belong under `tests/unit/services/` (per-primitive) and
`tests/integration/` (end-to-end blur+offset+blend chains).

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
