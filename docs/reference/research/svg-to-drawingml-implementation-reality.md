# SVG -> DrawingML Implementation Reality (Code-Verified)

Date: 2026-02-23

This document records what is actually implemented in code today, independent of roadmap wording in `docs/reference/research/svg-to-drawingml-feature-map.md`.

## Scope

- Pipeline: `Figma -> SVG -> OOXML (PPTX) -> Google Slides import`
- Evidence source: code paths + targeted tests in this repo
- Status labels used here:
  - `Implemented`: working code path exists and is exercised by tests
  - `Partial`: implemented for subsets, with known fallback/limitations
  - `Open`: still missing or effectively non-emitted

## Important Note About Map Counts

The often-cited section counts (for example `Painting & Stroke: 2 done / 10 open`) are from `Done` vs `Planned/Investigate` only. They do **not** count `Direct` rows.

Code check confirms those counts are internally consistent for the map view style:

- `1. Painting & Stroke`: `2 done / 10 open`
- `2. Gradients`: `2 done / 8 open`
- `3. Transforms`: `0 done / 4 open`
- `4. Clipping`: `1 done / 5 open`
- `5. Masking`: `2 done / 5 open`
- `6. Patterns`: `2 done / 7 open`
- `7. Text`: `7 done / 21 open`
- `8. Filters`: `4 done / 9 open`
- `9. Markers`: `9 done / 4 open`
- `10. Document Structure`: `5 done / 6 open`
- `14. Images`: `2 done / 1 open`

## Reality Snapshot By Area

### Painting & Stroke

- `Implemented`: solid fills/strokes, caps/joins, miter, dash arrays, alpha handling (`src/svg2ooxml/drawingml/paint_runtime.py`).
- `Partial`: gradient/pattern strokes vary by viewer behavior and fallback path.
- `Open`: `stroke-dashoffset` is parsed into IR but not emitted in DrawingML dash writer:
  - Parsed: `src/svg2ooxml/core/styling/style_extractor.py:275`
  - Not applied: `src/svg2ooxml/drawingml/paint_runtime.py:97`

### Gradients

- `Implemented`: linear/radial conversion, spread method expansion, gradient units and transform handling in adapters (`src/svg2ooxml/core/styling/style_extractor.py:370`, `src/svg2ooxml/drawingml/bridges/resvg_gradient_adapter.py:487`).
- `Partial`: radial + non-uniform/skew transforms trigger raster-oriented fallback intent (`src/svg2ooxml/drawingml/bridges/resvg_gradient_adapter.py:420`).
- `Partial`: focal point is carried in IR but DrawingML radial writer uses circle + `fillToRect`; extreme off-center cases remain lossy (`src/svg2ooxml/drawingml/paint_runtime.py:309`).

### Transforms

- `Implemented`: transform parsing, CTM stack, coordinate application (`src/svg2ooxml/core/traversal/transform_parser.py:11`, `src/svg2ooxml/core/traversal/coordinate_space.py:40`).
- `Partial`: type-specific fast paths reject skew/rotation in some shapes and fall back to generic geometry:
  - Rect requires axis-aligned transform (`src/svg2ooxml/core/ir/shape_converters_resvg.py:113`)
  - Ellipse rejects rotated matrix terms (`src/svg2ooxml/core/ir/shape_converters_resvg.py:226`)

### Clipping

- `Implemented`: structured fallback ladder (`native -> mimic -> emf -> raster`) (`src/svg2ooxml/services/clip_service.py:64`).
- `Partial`: complex nested semantics and renderer-specific clip-rule behavior remain edge-case sensitive.

### Masking

- `Implemented`: mask classification/fallback orchestration and uniform-alpha shortcut.
- `Open` (major): active mask effect XML is not emitted for native/mimic/emf/raster attempts (assets may be registered, but no standard mask effect is attached):
  - Native returns empty XML: `src/svg2ooxml/drawingml/mask_writer.py:171`
  - Mimic returns empty XML: `src/svg2ooxml/drawingml/mask_writer.py:196`
  - EMF returns empty XML: `src/svg2ooxml/drawingml/mask_writer.py:269`
  - Raster returns empty XML: `src/svg2ooxml/drawingml/mask_writer.py:328`
- `Partial`: simple gradient-mask baking exists for specific solid-fill scenarios (`src/svg2ooxml/core/masks/baker.py:15`).

### Patterns

- `Implemented`: preset patterns and tile image emission via `blipFill` when tile relationship is available (`src/svg2ooxml/drawingml/paint_runtime.py:343`).
- `Partial`: transform/unit fidelity for all SVG pattern variants is not complete end-to-end.

### Text

- `Implemented`: native basic text, RTL handling, decoration/spacing support, EMF fallback for complex layouts.
- `Implemented` (and map-stale): `textPath` can route to WordArt preset warp when classification confidence passes threshold:
  - Detection path: `src/svg2ooxml/core/resvg/text/text_coordinator.py:174`
  - Emission path: `src/svg2ooxml/core/resvg/text/drawingml_generator.py:216`
- `Partial`: complex typography and per-glyph advanced layout still falls to EMF.

### Filters

- `Implemented`: real primitives and fallback routing exist (not just comments) for blur/shadow/component transfer/color matrix/convolve, with policy-driven fallback selection (`src/svg2ooxml/filters/primitives/*.py`).
- `Partial`: many primitives still rely on EMF/bitmap fallback rather than true native DrawingML equivalents.

### Markers

- `Implemented`: marker-start/end/mid, scaling, orientation.
- `Implemented` (and map-stale): `orient="auto-start-reverse"` logic exists (`src/svg2ooxml/core/traversal/markers.py:195`).
- `Partial`: overflow/filter/complex paint combinations still depend on broader fallback behavior.

### Document Structure & Navigation

- `Implemented`: viewBox/PAR/group/use/symbol handling in core traversal.
- `Implemented` (and map-stale): `<switch>` evaluation for language/features (`src/svg2ooxml/core/parser/switch_evaluator.py:18`, `src/svg2ooxml/core/traversal/hooks.py:172`).
- `Implemented` (with constraints): hyperlink action URIs only for valid ACTION jumps; bookmark/custom-show intentionally not emitted as invalid `ppaction` URIs (`src/svg2ooxml/drawingml/navigation.py:183`).
- `Open`: group-level navigation is explicitly unsupported (`src/svg2ooxml/drawingml/writer.py:559`).
- `Partial`: `foreignObject` supports nested SVG/image/xhtml simplifications and placeholders, but not full browser-faithful HTML rendering (`src/svg2ooxml/core/ir/shape_converters.py:605`).

### Images

- `Implemented`: raster image embedding, data URI handling, aspect-ratio handling.
- `Partial`: recursive nested SVG image conversion and fallback behavior depend on source complexity.

## Map Rows That Are Stale (Should Be Updated)

- `7. Text`: `<textPath> on simple curve` is listed `Planned` but code path exists (WordArt classification + emit).
- `9. Markers`: `orient="auto-start-reverse"` is listed `Planned` but implemented.
- `10. Document Structure`: `<switch>` (`systemLanguage`, `requiredFeatures`) listed `Planned` but implemented.
- `10. Document Structure`: hyperlinks are implemented for valid action classes, not fully open.

## Most Material Remaining Fidelity Gaps

- Mask effect emission remains the largest practical gap for high-fidelity vector output.
- Radial gradients with anisotropic/skew transforms still require fallback for correctness.
- Advanced text layout (per-glyph positioning/warping beyond simple WordArt matches) is mostly fallback territory.
- Pattern transforms/units are not universally first-class across all SVG combinations.
- Some feature-map statuses are roadmap-accurate historically but no longer runtime-accurate.

## Verification Commands (Executed)

- `pytest -q tests/unit/drawingml/bridges/test_gradient_units_spread.py tests/unit/drawingml/bridges/test_gradient_transform_classification.py tests/unit/core/traversal/test_switch.py tests/unit/drawingml/test_navigation_ppaction.py tests/unit/core/resvg/text/test_text_coordinator.py tests/unit/core/resvg/text/test_drawingml_generator.py tests/unit/map/test_ir_converter.py::test_pattern_fill_records_policy_metadata tests/unit/map/test_ir_converter.py::test_marker_viewbox_scaling_applied tests/unit/drawingml/test_mask_writer.py tests/unit/core/test_mask_processor_core.py tests/integration/test_text_emf_fallback.py tests/integration/test_filter_vector_promotion.py`
- Result: `201 passed`
