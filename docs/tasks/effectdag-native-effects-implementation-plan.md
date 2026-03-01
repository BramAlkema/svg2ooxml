# EffectDag and Native Effects Implementation Plan

## Status: Planning

## Links

- ADR: `docs/adr/ADR-028-effectdag-and-native-color-transform-strategy.md`
- Research: `docs/research/drawingml-unused-opportunities.md`
- Baseline reality: `docs/research/svg-to-drawingml-implementation-reality.md`

## Objective

Implement a safe, incremental path to use more first-class DrawingML for SVG
filters by:

1. adding `effectDag` support for composite/mask graphs,
2. adding context-aware color transforms,
3. enriching blip-level effects for raster fallback assets,
4. validating compatibility with strict schema checks and Google Slides import.

## Non-Goals

- Eliminate EMF/bitmap fallback.
- Rewrite the full filter engine.
- Redesign unrelated geometry pipeline areas.

## Workstreams

### WS1: Effect Container Model and Serialization

Deliverables:
- Introduce explicit container handling in effect merge/render path:
  - `effectLst` path remains unchanged for valid list-only content.
  - `effectDag` path added for alpha/composite graph content.
- Prevent `effectLst` normalization from discarding non-list effect nodes.

Primary files:
- `src/svg2ooxml/drawingml/shapes_runtime.py`
- `src/svg2ooxml/filters/utils/dml.py`
- `src/svg2ooxml/drawingml/filter_renderer.py`

Acceptance checks:
- Unit tests for mixed effect fragments (`effectLst` + `effectDag`).
- XML ordering/schema tests for emitted containers.

### WS2: Composite/Mask Mapping on EffectDag

Deliverables:
- Route eligible `feComposite` outputs to `effectDag` representation.
- Keep current fallback behavior for unsupported operators or invalid inputs.
- Preserve policy override path to force EMF/bitmap as needed.

Primary files:
- `src/svg2ooxml/filters/primitives/composite.py`
- `src/svg2ooxml/drawingml/shape_renderer.py`

Acceptance checks:
- Fixture tests for `in`, `out`, `atop`, `xor` variants.
- No dropped-effect regressions compared to baseline.

### WS3: Context-Aware Color Transform Emission

Deliverables:
- Implement transform placement by parent context:
  - color-node transforms where valid,
  - effect graph transforms where valid,
  - blip-level transforms where valid.
- Upgrade selected `feColorMatrix` / `feComponentTransfer` subsets from fallback
  to native in those valid contexts.

Primary files:
- `src/svg2ooxml/filters/primitives/color_matrix.py`
- `src/svg2ooxml/filters/primitives/component_transfer.py`
- `src/svg2ooxml/drawingml/filter_renderer.py`

Acceptance checks:
- Unit tests for each mapped subtype and context.
- Schema validation tests proving no invalid `effectLst` children.

### WS4: Blip-Level Effect Enrichment

Deliverables:
- Apply compatible post-processing effects on fallback image `blip` payloads
  (strict allowlist only).
- Preserve deterministic fallback asset packaging metadata.

Primary files:
- `src/svg2ooxml/drawingml/filter_renderer.py`
- `assets/pptx_templates/picture_shape.xml` (if template changes are needed)

Acceptance checks:
- XML tests for valid blip effect payloads.
- Visual fixtures showing improvement over plain fallback image embedding.

### WS5: Validation and Rollout

Deliverables:
- Add targeted corpus (`tests/visual/golden/`) for composite/mask/color cases.
- Add schema-gate tests for all new emit paths.
- Produce before/after fallback-rate and visual-diff summary.
- Add policy flag and staged enablement.

Primary files:
- `tests/unit/...`, `tests/integration/...`, `tests/visual/...`
- policy provider files under `src/svg2ooxml/policy/`

Acceptance checks:
- All existing tests pass.
- New targeted suite passes.
- No increase in repair/schema error rate.

## Milestones

### M1: Container Foundation

Scope:
- WS1 baseline complete.

Exit criteria:
- `effectDag` can be emitted and preserved in rendering path.
- Existing `effectLst` behavior unchanged for current fixtures.

### M2: Composite/Mask Native Upgrade

Scope:
- WS2 complete with policy guard.

Exit criteria:
- Target composite operators pass schema and fixture checks.
- Demonstrated reduced fallback on composite/mask fixture subset.

### M3: Color Transform Upgrade

Scope:
- WS3 complete for initial subtype allowlist.

Exit criteria:
- Subset of color transforms promoted to native for valid contexts.
- No invalid `effectLst`/container placements.

### M4: Blip Enrichment and Rollout Decision

Scope:
- WS4 and WS5 complete.

Exit criteria:
- Compatibility report available (PowerPoint + Google Slides import checks).
- Decision taken on enabling for `high` then `balanced` quality profiles.

## Risks and Mitigations

1. Compatibility variance in Slides import.
- Mitigation: stage behind policy flag, maintain fixture matrix, default off
  until acceptance thresholds pass.

2. Schema regressions from container mixing.
- Mitigation: add strict XML-schema tests for every new emitted structure.

3. Hidden regressions in legacy effect paths.
- Mitigation: keep `effectLst` fast path untouched where possible and add
  regression snapshots.

## Proposed Policy Flags

- `filters.enable_effect_dag` (bool, default `False` initially)
- `filters.enable_native_color_transforms` (bool, default `False` initially)
- `filters.enable_blip_effect_enrichment` (bool, default `False` initially)

## Execution Order

1. WS1 -> M1
2. WS2 -> M2
3. WS3 -> M3
4. WS4 + WS5 -> M4

## Reporting Cadence

- End of each milestone:
  - fallback-rate delta on targeted fixtures,
  - schema validation summary,
  - visual comparison summary,
  - recommendation to advance or hold rollout stage.
