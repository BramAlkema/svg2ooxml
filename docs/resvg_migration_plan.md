# Resvg Migration Plan

This plan operationalises [ADR-017](adr/ADR-017-resvg-rendering-strategy.md) so
the team can move svg2ooxml’s filter rendering pipeline to a resvg-first
strategy while keeping production consumers stable.

## Objectives

- Make resvg the primary fallback after native DrawingML emission and relegate
  the legacy raster/EMF adapters to “last resort” status.
- Maintain editability for primitives that already support DrawingML.
- Provide clear policy and exporter controls so callers can force legacy or
  diagnostic modes during the migration.
- Capture telemetry that proves parity and highlights remaining gaps.

## Milestones

| Phase | Goal | Target window | Exit criteria |
| ----- | ---- | ------------- | ------------- |
| P1 – Parity & Telemetry | Ship resvg fallback and capture metadata. | Complete | `FilterService` executes native → resvg → legacy, tracer marks `resvg_attempt`/`resvg_success`, docs updated. |
| P2 – Promotion & Policy | Promote simple resvg stacks to vector/EMF where possible and wire policies. | Complete | Policy engine now enforces per-primitive promotion limits, tracer records policy blocks, and promotion metadata covers all supported vector stacks. |
| P3 – Coverage & Validation | Prove resvg handles real workloads. | Upcoming | Integration + visual suites cover complex filters; telemetry dashboards show resvg handling ≥85 % of staged documents without regression reports. |
| P4 – Default to resvg | Flip exporter default and retire unused legacy helpers. | Pending parity proof | Exporter defaults to `filter_strategy="resvg"`; legacy pathway disabled unless explicitly requested; release notes published. |

## Work Breakdown

### Phase 2 – Promotion & Policy

1. **Descriptor-driven promotion** *(complete)*
   - [x] Analyse planner metadata to identify promotable stacks and keep extras in `plan_primitives`.
   - [x] Promote flood/composite, blend, color matrix, morphology/tile, offset, merge, component-transfer, and convolve-matrix chains to EMF/vector fallbacks.
   - [x] Expand unit coverage (`tests/unit/services/test_filter_service.py`) for multi-primitive promotion paths.

2. **Policy scenarios** *(complete)*
   - [x] Extend `FilterPolicyProvider` with promotion limits (offset distance, merge inputs, component functions/tables, convolve kernels/orders) alongside `allow_promotion`.
   - [x] Enforce overrides inside `FilterService` so policy, exporter, or runtime knobs can veto promotions.
   - [x] Document the knobs in `docs/resvg.md` for downstream teams.

3. **Telemetry enrichment** *(complete)*
   - [x] Emit `resvg_promotion_policy_blocked` and `resvg_promoted_emf` stage events with structured metadata (rule, limits, primitive chain).
   - [x] Attach serialised resvg descriptors and planner summaries to promotion metadata for downstream telemetry.

### Phase 3 – Coverage & Validation

1. **Primitive coverage**
- [x] Implement remaining resvg handlers (lighting edge cases, turbulence
     stitching) in `src/svg2ooxml/render/filters.py`.
- [x] Expand unit coverage (`tests/unit/services/test_filter_service.py`) to
     capture lighting metadata and policy interactions (`resvg_plan_characterised`
     events).
- [x] Add synthetic SVG fixtures in `tests/assets` for broader coverage.
- [x] Prototype lighting promotions (diffuse/specular) via promotion factories
     and trace `resvg_lighting_promoted` events for telemetry.
- [x] Add integration coverage (`tests/integration/test_filter_vector_promotion.py`)
     to compare resvg vs legacy metrics for lighting filters.

2. **Visual baselines**
   - Refresh `tests/visual/golden/` with matched resvg/legacy outputs.
   - Introduce comparison jobs in CI (nightly) that run
     `SVG2OOXML_VISUAL_FILTER_STRATEGY=resvg` vs `legacy` and report pixel
     diffs.
   - [x] Add a lighting regression comparison (`tests/visual/test_filter_lighting_scene.py`)
     to measure resvg vs legacy rendering deltas without requiring golden assets.

3. **Staging telemetry**
- [x] Emit `resvg_plan_characterised` / `resvg_promotion_policy_blocked` tracer
    events so downstream telemetry captures plan composition and policy fallbacks.
- [x] Feed `resvg_metrics` counters into conversion summaries for dashboards.
- [ ] Instrument API workers to emit counters for resvg vs legacy pathway.
- [ ] Build a simple dashboard (e.g. Looker/BigQuery or temporary CSV) tracking
     adoption and fallbacks.
    - See `docs/telemetry/resvg_metrics.md` for wiring notes and sample queries.

### Phase 4 – Defaulting

1. **Flip defaults**
   - Change `SvgToPptxExporter` default `filter_strategy` to `"resvg"`.
   - Update CLI/tools defaults and documentation.

2. **Deprecate legacy helpers**
   - Remove unused raster/EMF fallback utilities once resvg coverage is proven.
   - Archive documentation for legacy modes, keeping a troubleshooting note.

3. **Release communication**
   - Draft release notes and update `docs/porting.md`.
   - Inform downstream consumers (Slides, internal exporters) with the rollout
     timeline and opt-out instructions.

## Status Dashboard (manual)

| Item | Status | Notes |
| ---- | ------ | ----- |
| Resvg-first pipeline landed | ✅ | `FilterService` now returns resvg results before legacy fallbacks. |
| Policy override spec | ✅ | Promotion limits for offset/merge/component-transfer/convolve landed; lighting budgets moved to Phase 3. |
| EMF promotion prototype | ✅ | Single-primitive and stack promotions now cover flood/composite, blend, color matrix, morphology/tile, component-transfer, offset, merge, and convolve matrix. |
| Visual regression suite | ⏳ | Needs CI integration. |
| Exporter default flip | ⏳ | Blocked on parity metrics. |

Update this table as milestones progress.

## Current Focus

- Monitor the extended policy override schema (`allow_promotion`, `max_arithmetic_coeff`, offset/merge/component/convolve limits) and keep the unit coverage in sync with new knobs.
- Extend EMF/vector promotion to lighting primitives using the enriched plan metadata and lighting helpers.
- Finalise staging telemetry (counters/dashboards) so resvg vs legacy adoption remains observable.

## Immediate Next Steps (Q1)

1. Validate extended policy overrides and land supporting unit tests. *(done)*
2. Prototype EMF promotion for lighting primitives using the enriched lighting metadata and plan summaries.
3. Scope lighting parity: lighting descriptors now capture surface scale, constants, light parameters, and planner metadata; next step is EMF/vector promotion for `feDiffuseLighting`/`feSpecularLighting` plus policy knobs.
4. Expand tracer payloads and ship dashboards for staging telemetry.
5. Begin collecting parity metrics on key customer documents.
