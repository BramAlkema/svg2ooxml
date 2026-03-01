# ADR-028: EffectDag and Native Color Transform Strategy for SVG Filters

- **Status:** Proposed
- **Date:** 2026-02-23
- **Owners:** svg2ooxml drawingml and filters teams
- **Depends on:** ADR-017 (resvg strategy), ADR-018 (EMF procedural fallbacks), ADR-023 (schema compliance), ADR-025 (quality roadmap)
- **Related:** `docs/research/drawingml-unused-opportunities.md`, `docs/research/svg-to-drawingml-implementation-reality.md`

## 1. Problem Statement

The current pipeline can build advanced filter/composite fragments, but practical
native coverage is limited by an `effectLst`-only merge path. In particular:

- composite/mask alpha operators are generated in filter primitives, then lost
  during shape-level effect normalization;
- several color-transform opportunities are skipped because they are evaluated
  only against `effectLst` validity, not full DrawingML context rules;
- raster fallback images are embedded without using available blip-level color
  effects that could preserve more semantics.

This creates avoidable fallback pressure and leaves native DrawingML capability
unused for high-value SVG cases.

## 2. Context

- Composite currently builds `alphaMod` / `alphaModFix` style structures:
  `src/svg2ooxml/filters/primitives/composite.py`
- Shape effect normalization keeps only `CT_EffectList` child set:
  `src/svg2ooxml/drawingml/shapes_runtime.py`
- Filter color matrix primitive explicitly avoids mappings when judged through
  `effectLst` constraints:
  `src/svg2ooxml/filters/primitives/color_matrix.py`
- Fallback rendering frequently uses `blipFill`/image paths:
  `src/svg2ooxml/drawingml/filter_renderer.py`

## 3. Decision

1. Adopt a dual native-effect architecture:
   - keep `effectLst` for simple valid `CT_EffectList` content;
   - add `effectDag` emission for compositing/mask graphs that need alpha ops
     and nested containers.
2. Introduce context-aware color-transform emission:
   - apply transforms where schema-valid (color nodes, blip context, effect dag),
     not only where valid under `effectLst`.
3. Add blip-level effect enrichment for raster fallback assets where safe.
4. Gate rollout with strict schema validation and Google Slides import checks on
   focused fixtures before enabling by default.
5. Keep EMF/bitmap fallback ladder unchanged as safety net.

## 4. Scope

### In Scope

- `effectDag` serialization path for filter composite/mask cases.
- Effect merge utilities that preserve both container families (`effectLst` and
  `effectDag`) without cross-invalid flattening.
- Color transform mappings for selected `feColorMatrix` /
  `feComponentTransfer` subsets in valid XML contexts.
- Blip-level effect application for raster fallback media where deterministic.
- Policy flags for progressive rollout and rollback.

### Out of Scope

- Full reimplementation of all SVG filter primitives as native DrawingML.
- Removal of EMF/bitmap fallback paths.
- Broad transform/geometry redesign unrelated to filter/effect emission.

## 5. Rationale

- The highest-value gaps are currently caused by container/placement mismatch,
  not by total lack of candidate DrawingML primitives.
- `effectDag` addresses exactly the class of generated-but-dropped structures in
  the present code path.
- Context-aware emission prevents false negatives from `effectLst`-only checks.
- Incremental, policy-gated rollout preserves delivery safety.

## 6. Consequences

### Positive

- Higher native fidelity for composite/mask and selected color-transform cases.
- Reduced fallback frequency for filter-heavy assets.
- Better leverage of existing DrawingML primitives and existing filter planner.

### Negative

- More complexity in effect serialization and merge logic.
- Higher compatibility-test burden across PowerPoint and Google Slides import.
- Increased risk of subtle schema/ordering regressions without strict fixtures.

## 7. Rollout

1. Implement `effectDag` path behind a policy flag (`filters.enable_effect_dag`).
2. Add fixture corpus for composite/mask and color-transform scenarios.
3. Enable for opt-in profiles first (`high`, then `balanced` after validation).
4. Publish compatibility matrix and fallback deltas before default-on decision.

## 8. Acceptance Criteria

- Composite/mask fixtures that currently lose alpha graph semantics emit valid
  OOXML with no schema violations.
- No regression in existing `effectLst` output for legacy/simple cases.
- Targeted Google Slides import checks show improved parity on new fixtures.
- Fallback ratio decreases for the selected fixture set without increasing
  corruption/repair incidents.
