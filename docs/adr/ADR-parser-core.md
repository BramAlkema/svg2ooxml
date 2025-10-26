# ADR: Parser Core Port (svg2pptx → svg2ooxml)

- **Status:** In Progress
- **Date:** 2025-XX-XX
- **Owners:** svg2ooxml migration team
- **Depends on:** None (first ADR in parser track)
- **Blocks:** Geometry/IR ADR, Policy/Mapping ADR, Filter/Color ADRs

## Context

The legacy `svg2pptx` project implements a monolithic parser in
`core/parse/parser.py` (~110k LOC) backed by helper modules under
`core/parse_split/` and `core/utils/enhanced_xml_builder.py`. Responsibilities include:

- Preparing and validating SVG XML using `SplitXMLParser` and the enhanced XML builder.
- Normalizing markup (`SafeSVGNormalizer`), collecting statistics, and tracking DOM state.
- Building style contexts (`StyleContextBuilder`), resolving units, and establishing coordinate spaces.
- Collecting clip/mask/symbol/paint definitions and passing them to IR converters.
- Dispatching to `SplitIRConverter` and hyperlink processors, while interfacing with services (filter, gradient, pattern, image) provided by a global `ConversionServices` container.
- Feeding downstream geometry (path segments, transforms) via `TransformParser` and `PathSegmentConverter`.
- Emitting a rich `ParseResult` that includes DOM, normalization metadata, statistics, and references for later mapping steps.

This single file tightly couples IO, normalization, style resolution, reference collection, and IR conversion. It also pulls in services via mutation, making it hard to swap dependencies or test components in isolation.

## Decision

Break the parser into smaller modules that align with the new placeholders while preserving fidelity:

- `parser/dom_loader.py` — handle XML parsing, parser configuration, and root validation (wrap svg2pptx `SplitXMLParser`/enhanced builder).
- `parser/normalization.py` — host SafeSVG normalization routines and related statistics.
- `parser/style_context.py` — port the style context builder, viewport resolution, and unit conversions.
- `parser/reference_collector.py` — encapsulate clip/mask/symbol/paint definition collection.
- `parser/statistics.py` — compute element/namespace counts and external reference detection.
- `parser/xml/enhanced_builder.py` — replicate enhanced XML builder utilities used during parsing.
- `parser/svg_parser.py` — orchestrate the new helpers, returning the enriched `ParseResult` while keeping high-level behavior identical.

Dependencies on other subsystems should be injected explicitly:

- Service hooks (filter, gradient, pattern) resolved via `services.setup.configure_services` to avoid setting attributes inside the parser.
- Unit conversion and transforms should rely on the new `parser/units/` and `parser/geometry/` modules rather than pulling directly from legacy packages.

## Consequences

- **Pros**
  - Smaller, testable modules that map closely to the legacy responsibilities.
  - Clear injection points for services make the parser composable and avoid global state.
  - Downstream ADRs (geometry, policy, mapping) can reference well-defined parser outputs.
- **Cons**
  - Initial overhead to slice up responsibilities before porting behavior.
  - Requires coordination with services/DI work so imports remain clean.

## Migration Plan

1. Port xml parsing helpers into `parser/dom_loader.py` and `parser/xml/enhanced_builder.py`.
2. Move normalization and statistics code to `parser/normalization.py` and `parser/statistics.py`.
3. Port the style context builder and unit integration into `parser/style_context.py`.
4. Extract clip/mask/etc. collection to `parser/reference_collector.py`.
5. Update `parser/svg_parser.py` to delegate to the new modules, mirroring legacy behavior.
6. Write unit tests that compare key outputs to svg2pptx fixtures to ensure fidelity.

## Status Notes

- Open TODO: add `TODO(ADR-parser-core)` breadcrumbs in any remaining parser placeholders (track in issue PARSER-17).
- SplitIRConverter follow-up: `src/svg2ooxml/map/ir_converter.py` now carries a `TODO(ADR-parser-core)` comment noting the remaining hyperlink/filter/EMF behaviours that still need porting alongside ADR-policy-map.
- Service injection is now mediated through `svg2ooxml.services.setup.configure_services`; pending ADR(s) should reference this rather than mutating global state.

## Current Assessment (2025-XX-XX)

Refer to `docs/assessments/parser_core_comparison.md` for a detailed feature
matrix. Key gaps before parity with svg2pptx:

- CSS style resolver now lives under `svg2ooxml/css/resolver.py` with tinycss2 support, though shorthand coverage and regression fixtures are still pending.
- Normalization now restores encoding fixes, comment filtering, and container pruning, but legacy logging heuristics still need reviewing.
- Clip/mask collection now records geometry segments via the new `ClipPathExtractor`; IR conversion still needs to consume these definitions.
- Marker support: parser collects marker definitions into `MarkerService`, IR conversion expands start/mid/end markers (including viewBox/preserveAspectRatio) and surfaces clip metadata; DrawingML writer now emits `<a:clipPath>` for hidden-overflow markers. Remaining parity checks include hooking policy-driven raster fallbacks and validating visual baselines.
- Filter scaffolding: `FilterService` now mirrors the svg2pptx DI shape (registry + policy-aware binding) so collected `<filter>` elements flow through ConversionServices. Actual primitive execution/DrawingML emission still pending.
- Gradient/pattern processors are integrated during style extraction, attaching paint analysis and policy hints (complexity, fallback suggestions) so mappers can make raster/EMF decisions similar to svg2pptx.
- Services are instantiated per parse via `ConversionServices`, but real providers and hyperlink processing remain TODO until ADR-policy-map lands; IR conversion also remains outstanding.

These items should be addressed before declaring the parser port complete.

### Element Coverage Checklist (svg2pptx → svg2ooxml)

| Element / Feature | svg2pptx | svg2ooxml | Status / Follow-up |
| --- | --- | --- | --- |
| `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `path` | ✅ native support (rounded corners, all path commands) | ✅ basic shapes, smooth curves; rounded `rect` corners flattened | Native rect/circle/ellipse primitives restored in IR |
| `g` (group) | ✅ | ✅ | parity |
| `use` | ✅ (deep resolution) | ⚠️ expanded via traversal with width/height/viewBox scaling | Audit nested reuse & service metadata for parity |
| `defs`, `symbol` | ✅ referenced via `<use>` | ⚠️ partial (clip/mask only) | follow `<use>` work item |
| `clipPath`, `mask` | ✅ geometry + references | ✅ geometry recorded, TODO for native primitives | ensure downstream services consume definitions |
| `pattern`, `linearGradient`, `radialGradient` | ✅ processed into paint refs | ⚠️ gradients/patterns resolved via services; DrawingML mapping now emits gradient fills | Extend coverage for advanced features (spreadMethod, pattern content) |
| `image` | ✅ | ✅ | parity contingent on image service port |
| `text`, `tspan`, `textPath` | ✅ full text stack | ⚠️ simple `<text>` only, no spans/paths | large TODO |
| `marker` | ✅ | ⚠️ basic arrowheads via marker metadata; full geometry mapping pending | extend marker processor for custom shapes |
| `filter` & primitives | ✅ | ⛔ references captured, no execution | filter pipeline TODO |

## Parity Lift Plan (svg2pptx imports)

| Gap / Goal | svg2pptx source to lift | svg2ooxml destination | Notes & Dependencies |
| --- | --- | --- | --- |
| Restore normalization logging & encoding fixes | `core/parse/parser.py` normalization helpers (`_fix_encoding_issues`, `_log_normalization_changes`, `_strip_illegal_nodes`), `core/parse/safe_svg_normalization.py`, `core/xml/safe_iter.py` | Extend `parser/normalization.py`, `parser/content_cleaner.py`, reuse `parser/xml/safe_iter.py` | Adds change logs, encoding heuristics, and structured metrics referenced in assessments; unblock parity checks in `compute_statistics`. |
| Expand CSS resolver coverage | `core/css/resolver.py`, `core/css/animation_extractor.py`, shared shorthands in `core/css/__init__.py` | Merge into `css/resolver.py`, add `css/animation_extractor.py`, expose hooks via `parser/style_context.py` | Brings shorthand parsing, font fallback rules, and animation overrides required by svg2pptx fixtures; depends on unit conversion updates below. |
| Align unit & viewport math | `core/units/core.py`, `core/transforms/parser.py`, `core/transforms/coordinate_space.py` | Fill out `parser/units/lengths.py`, `parser/geometry`, `map/converter/coordinate_space.py` | Needed for EM/% handling, transform matrices, and coordinate stacks that current clip + IR stubs rely on. |
| Re-enable `<use>` and symbol expansion | `core/parse/parser.py::_convert_use_to_ir`, `_collect_symbol_definitions`, `core/parse_split/models.py`, `core/parse_split/element_traversal.py` | Update `parser/reference_collector.py`, replace `parser/split/element_traversal.py` stub, teach `map/converter/traversal.py` to call the ported logic | Unlocks traversal-level `<use>` resolution and symbol reuse so defs mirror legacy behaviour; depends on unit/transform parity. |
| Consume clip/mask geometry in IR | `core/parse_split/ir_converter.py` clip hooks, `core/parse/path_segments.py` matrix helpers | Extend `map/converter/core.py`, `parser/core/path_segments.py`, wire geometry cache through `map/converter/coordinate_space.py` | Required so collected clip/mask definitions feed mapping just like svg2pptx; ensures rounded primitives remain native when Geometry ADR lands. |
| Restore hyperlink + services wiring | `core/parse_split/hyperlink_processor.py`, `core/services/conversion_services.py` policy hooks | Flesh out `map/converter/hyperlinks.py`, `services/conversion.py`, inject services via `parser/svg_parser.py` | Keeps parser stateless while providing hyperlinks, gradients, filters, and marker processors when available; coordinates with ADR-policy-map. |
| Port gradient & pattern processors | `core/parse/parser.py` gradient collectors, `core/services/gradient_service.py`, `core/services/pattern_service.py` | Populate `parser/reference_collector.py`, `services/gradient_service.py`, `services/pattern_service.py`, seed `paint/` processors | Bridges reference collection with actual OOXML paint generation; prerequisite for gradient/pattern parity in mapper ADR. |
| Bring text stack (tspan, textPath, inheritance) | `core/parse/parser.py::_convert_text_to_ir`, `core/text/*`, supporting CSS bits in `core/css/resolver.py` | Expand `map/converter/core.py`, resurrect `text/` models and layout helpers, extend style resolver to expose text inheritance API | Required for full text coverage; depends on font + CSS tasks and will reuse services for font metrics once ported. |
| Reintroduce markers & filter execution | `core/map/marker_processor.py`, `core/map/marker_mapper.py`, `core/filters/*`, `core/services/filter_service.py` | Land under `map/marker_processor.py`, `map/marker_mapper.py`, `filters/`, hook via `services/conversion.py` | Finishes element coverage checklist (markers, filters); blocked on gradient/pattern + services wiring. |
| Regression fixtures & comparisons | Golden SVG/PPTX pairs under `../svg2pptx/testing/fixtures` and `tests/test_svg_element_coverage.py` | Mirror into `tests/integration/parser`, add diff harness in `tests/visual` | Validates parity across the lifted modules; run as part of CI gate once mapper/services ADRs complete. |
