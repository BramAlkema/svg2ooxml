# ADR-013: Port Animation & Multi-Slide Support from `svg2pptx`

## Status

Accepted (2024-XX-XX) — implementation pending.

## Context

The legacy `svg2pptx` project contains a mature animation pipeline that:

- Samples SMIL/animated attributes into frame sequences.
- Emits timeline metadata for PowerPoint with fallbacks for unsupported effects.
- Splits long-running animations across multiple slides when required.
- The modules live under `../svg2pptx/core/animations/` and already encapsulate parsing, sequencing, timing, and PowerPoint emission concerns we need in `svg2ooxml`.
- Several components entwine concerns that we should slice apart during the port so that orchestration, sampling, and writer concerns can align with the new package layout.

`svg2ooxml` currently renders static snapshots of SVG content; animated SVGs are flattened to a single frame and the CLI exports exactly one slide per input. As we begin running the W3C SVG test suite (e.g. `animate-elem-*`), the lack of animation and multi-slide support prevents parity with `svg2pptx` and undermines downstream scenarios (motion studies, interactive decks).

Key differences observed:

- `svg2pptx` hosts an animation sampler driven by a timing engine plus a slide-assembly stage that wires `pptx` timeline elements.
- The new architecture already has IR hooks (effects, metadata) but no stage for temporal sampling or slide partitioning.
- CLI callers expect a single PPTX file; multi-slide output must remain deterministic and traceable in reports.

## Decision

1. **Port the animation sampler and timing engine.** Extract the reusable components from `svg2pptx` (SMIL attribute resolver, keyframe sampler, easing support) into `src/svg2ooxml/core/animation/`. Expect to slice large modules into focused units and refactor them to consume the new IR/conversion services.
2. **Extend the IR to represent animation tracks.** Introduce explicit animation descriptors (per attribute/element) that the DrawingML writer can translate into timing tags or baked frames.
3. **Add a multi-slide orchestrator.** When animations cannot be represented natively, fall back to slide sequences. The orchestrator determines split points, generates staged scenes, and hands them to `PPTXPackageBuilder.build_scenes`.
4. **Trace every decision.** Use the enhanced tracer to log when animations are sampled, when multi-slide fallbacks occur, and when features degrade to static frames.
5. **Gate functionality behind a policy flag initially.** Default to legacy (single slide) behaviour until animation parity is validated; opt-in via CLI flag / policy toggle.

## Consequences

- + We achieve parity with `svg2pptx` on animated SVGs and W3C animation tests.
- + Slide generation remains deterministic with trace logs explaining each split.
- − Additional complexity in the conversion pipeline (timing engine, slide orchestrator) increases maintenance.
- − Rendering animated content will cost more CPU; we must expose sampling controls (fps, duration caps) via policy.

## Implementation Sketch

1. **Audit `svg2pptx` animation modules.** Catalogue dependencies (policy hooks, timing utilities) and map them to the new package structure while identifying seams for slicing/refactors. The current entry points to lift are:
   - `core/animations/parser.py` and `core/animations/core.py` for SMIL parsing and orchestration.
   - `core/animations/sequence_builder.py`, `timing_builder.py`, and `timeline.py` for track construction.
   - `core/animations/powerpoint.py` and `builders.py` for translating animation tracks into PPTX timelines.
   - `core/animations/interpolation.py` and `time_utils.py` for easing and sampling helpers.
   Any shared utilities referenced outside this folder must either already exist in `svg2ooxml` or be rehomed under `src/svg2ooxml/common/`.
2. **Define IR extensions.** Draft types for animation clips/tracks (`src/svg2ooxml/ir/animation.py`) and update the tracer schema. Capture slide-splitting hints so downstream writers can choose between native timelines and baked frames.
3. **Port the sampler.** Move the sampling logic into `src/svg2ooxml/core/animation/` with adapters to the new Style/Geometry APIs. Strip `svg2pptx`-specific abstractions (e.g. direct `pptx` references), slice helpers into reusable units where necessary, and expose a policy-aware sampler interface.
4. **Slide orchestrator.** Build a module under `core/slide_assembly` that accepts sampled frames, groups them into scenes, and reuses `SvgToPptxExporter`’s multi-scene support. Ensure we can call back into `core/animation` to request additional frames when policies demand tighter sampling.
5. **Writer integration.** Update `DrawingMLWriter` to emit timing tags or duplicated slides depending on capabilities; ensure mask/media handling is aware of shared assets across slides. Shared assets should be deduplicated via `io/pptx/relationship_manager`.
6. **CLI ergonomics.** Add flags to control animation sampling rate, duration caps, and whether to allow multi-slide output. Document the feature gate in `docs/cli.md` and expose defaults through the policy config.
7. **Testing.** Import the relevant W3C animation tests as fixtures; add regression tests for multi-slide outputs and trace reports. Mirror `../svg2pptx/tests/animations/` where coverage remains valuable and retire obsolete tests.

## Module Slicing Notes

- `../svg2pptx/core/animations/core.py`: Bundles pure data models with runtime helpers (`AnimationDefinition.get_value_at_time`, `format_transform_string`, `AnimationSummary.calculate_complexity`). Split into immutable IR dataclasses, evaluation helpers that can plug into the sampler, and reporting utilities so `core/animation/` can depend on the lean models only.
- `../svg2pptx/core/animations/parser.py`: Mixes DOM traversal, timing/value parsing, and summary bookkeeping. Carve a `SmilElementParser` focused on producing IR objects, push time parsing to shared utilities, and route summary/warning emission through the tracer instead of the parser mutating state.
- `../svg2pptx/core/animations/builders.py`: Houses `AnimationBuilder`, `AnimationSequenceBuilder`, `TimingBuilder`, and `AnimationComposer` plus ad-hoc time parsing. Extract the reusable timing helpers, drop or relocate the fluent API to developer tooling, and ensure any retained builder surfaces work with the new policy + IR types.
- `../svg2pptx/core/animations/sequence_builder.py`: Duplicates sequencing logic from `builders.py` while leaning on `parse_time_value`. Decide whether to keep a single sequencing helper (likely under developer helpers) or fold the minimal functionality into the orchestrator.
- `../svg2pptx/core/animations/timing_builder.py`: Tiny wrapper around `AnimationTiming` with string parsing. Either fold into the shared timing utilities or expose it as a thin policy-aware factory so we do not proliferate builder classes in production code.
- `../svg2pptx/core/animations/timeline.py`: Combines sampling (`_generate_time_samples`), conflict resolution (`_resolve_animation_conflicts`), and scene optimization (`_optimize_timeline`). Slice these into dedicated services (Sampler, ConflictResolver, SceneOptimizer) feeding the new slide orchestrator and reuse the interpolation engine via narrow interfaces.
- `../svg2pptx/core/animations/interpolation.py`: Centralizes color/numeric/transform interpolation and sneaks in optional `ConversionServices` calls. Separate pure interpolation strategies from service lookups, and ensure transform handling surfaces clear extension points for policy overrides.
- `../svg2pptx/core/animations/powerpoint.py`: Converts IR directly into DrawingML strings and owns ID bookkeeping. Move the PPTX-specific emission into `drawingml/` writers, share ID generation with the existing package builder, and let `core/animation` return structured commands rather than XML fragments.
- `../svg2pptx/core/animations/time_utils.py`: Simple `parse_time_value` helper that overlaps with parser/builder logic. Replace all bespoke `_parse_time_value` helpers with a single function under `common/time.py` and add unit coverage before swapping callers.
- `../svg2pptx/core/animations/__init__.py`: Re-exports legacy fluent APIs and convenience factories tied to the old services layer. Only port the symbols needed by production code, and stage developer-facing helpers under `tools/` or drop them once tests no longer rely on the package layout.

### Dependency Walk Findings

- `core.py`: Pure stdlib dependencies. Dataclasses/enums (`AnimationType`, `AnimationTiming`, `AnimationDefinition`, `AnimationScene`, etc.) belong in `ir/animation.py`; execution helpers (`AnimationDefinition.get_value_at_time`, easing logic, `format_transform_string`) should become sampler/interpolation utilities under `core/animation/`. `AnimationSummary`’s scoring heuristics fits a policy/reporting module once we wire traces instead of mutating parser state.
- `parser.py`: Depends on `lxml.etree`, `re`, and the `AnimationSummary` helper. Keep the DOM traversal + attribute normalization in a new `core/animation/parser.py`, reuse `common/time.parse_duration` for timing, and redirect warning/complexity bookkeeping to the tracer/policy layer so the parser stays side-effect free.
- `builders.py`: Only imports core types yet duplicates `parse_time_value` and exposes fluent APIs (`AnimationBuilder`, `AnimationSequenceBuilder`, `TimingBuilder`, `AnimationComposer`). Production pipeline doesn’t need these; migrate any test/developer usage to `tools/animation_builders.py` (reusing shared time helpers) and drop the module from the main package.
- `sequence_builder.py`: Wraps `AnimationBuilder` and `parse_time_value` again. Once the fluent API moves out of production code, this file disappears or collapses into a single helper living alongside the dev tooling.
- `timing_builder.py`: Thin wrapper over `AnimationTiming` plus `parse_time_value`. Either inline into the new shared time helper or expose a policy-aware factory in `core/animation/timing.py`; no reason to keep a dedicated builder module.
- `timeline.py`: Pulls in `InterpolationEngine` and bundles time sampling, conflict resolution, and scene optimization. Extract `TimelineConfig` (policy surface) and move sampling/conflict logic into `core/animation/sampler.py`; push optimization heuristics behind a pluggable strategy so policy can tune thresholds without touching sampler internals.
- `interpolation.py`: Uses stdlib + `TransformType` and reaches into `..color.Color`. Relocate pure interpolation strategies to `common/interpolation/` and inject color parsing via an interface supplied by `core/animation` so we stop depending on the old services layer.
- `powerpoint.py`: Relies on `AnimationDefinition`, `AnimationScene`, `AnimationType`, `TransformType`, and `Color`; emits raw DrawingML strings and owns ID counters. Move the XML emission into `drawingml/animation_writer.py`, source ID/state from `drawingml`’s package builder, and keep only a thin adapter in `core/animation` that produces writer-friendly commands.
- `time_utils.py`: Standalone `parse_time_value` used across builders/sequence helpers. Replace the call sites with a shared helper under `common/time.py`, then delete the legacy module.
- `__init__.py`: Re-exports every legacy entry point and wires `ConversionServices`. Limit exports to the new IR/sampler surfaces; developer conveniences shift to `tools/` so the production package stays slim.

### Usage Inventory (svg2pptx)

- `AnimationBuilder` & friends: Only referenced from docs (`docs/adr/ADR-005-FLUENT-API-PATTERNS.md`, `docs/adr/ADR-006-ANIMATION-SYSTEM-ARCHITECTURE.md`), convenience exports (`core/animations/__init__.py`), and unit tests (`tests/unit/core/animations/test_builders.py`). No production modules call these helpers; move the fluent API into `tools/animation_builders.py` (or drop) and rewrite the unit tests against the new policy/IR surface.
- `AnimationSequenceBuilder`/`TimingBuilder` stand-alone modules: Imported exclusively by the fluent API, `core/animations/__init__.py`, and the unit test above. Safe to relocate or cull alongside the fluent API once replacement utilities exist.
- `AnimationComposer`: Unused outside its own definition and the `create_composer` convenience wrapper. Unless the new toolkit needs canned recipes, retire it.
- `TimelineGenerator` & `TimelineConfig`: Actively used by `core/converters/animation_converter.py` (production) to sample timelines, and appear in legacy specs/metrics. Must land in `core/animation/sampler.py` (or equivalent) so the converter port keeps working; update scripts/tests to import the new location when the port is complete.

### Porting Progress

- [2024-XX-XX] Lifted the core animation IR (enums, dataclasses, summaries) into `src/svg2ooxml/ir/animation.py` to unblock the sampler/parser port. Added unit coverage in `tests/unit/ir/test_ir_animation.py` and rebuilt package exports so downstream modules can import the new definitions.
- [2024-XX-XX] Ported the SMIL parser into `src/svg2ooxml/core/animation/parser.py`, using the shared time utility and new IR. Added regression tests in `tests/unit/core/animation/test_smil_parser.py` to cover attribute parsing, transforms, and summary reporting.
- [2024-XX-XX] Sampler plan: introduce `TimelineSamplingConfig` plus `TimelineSampler`, `ConflictResolver`, and `SceneOptimizer` in `core/animation/sampler.py`. The sampler will depend on interpolation helpers refactored into `common/interpolation.py`, accept IR animations, emit `AnimationScene` snapshots, and expose hooks so policy can tune thresholds without touching internals.
- [2024-XX-XX] Ported the timeline sampler to `src/svg2ooxml/core/animation/sampler.py` with supporting interpolation utilities in `src/svg2ooxml/common/interpolation.py`. Added unit tests in `tests/unit/core/animation/test_timeline_sampler.py` to verify sampling, additive conflict resolution, and discrete modes.
- [2024-XX-XX] Integrated parser + sampler into `SvgToPptxExporter` and `DrawingMLWriter`: animations are parsed, sampled, and emitted as native timing when we can map element IDs to shapes (opacity fades, scale, rotate, translate, plus simple motion paths via `<a:ptLst>`). We convert spline easing into accel/decel hints, avoid slide duplication, and keep metadata/tracer events ready for future multi-track support (`tests/unit/core/test_pptx_exporter_animation.py`).
- [2024-XX-XX] Hardened the DrawingML animation writer: property/colour/set animations normalise PPT units (`ppt_x`, `ppt_y`, `ppt_w`, `ppt_h`, `ln_w`), transform tracks emit per-segment `<a:tav>` with `<a:tavPr>` and `svg2:` easing metadata, and the policy engine now surfaces `allow_native_splines`, `fallback_mode`, and `max_spline_error` toggles. Added regression coverage for transform easing segments and policy overrides (`tests/unit/core/test_pptx_exporter_animation.py`, `tests/unit/policy/test_providers.py`).

### Support Snapshot (2024-XX-XX)

- **Native coverage**: `<a:anim>`, `<a:animClr>`, `<a:set>`, `<a:animScale>`, `<a:animRot>`, and `<a:animMotion>` (simple offsets or linearised paths) with automatic PPT attribute mapping for positions, sizes, rotation, and stroke widths.
- **Easing hints**: Every keyframe emits `<a:tav>` entries; when splines are present we add `<a:tavPr accel="" decel="">` and `svg2:accel/svg2:decel/svg2:spline/svg2:segDur` metadata so policy can assess fidelity.
- **Fallback triggers**: Policy disables native output when `fallback_mode != native`, when spline error exceeds `max_spline_error`, or when we cannot map SVG IDs to generated shapes. The tracer records `fragment_skipped` / `fragment_bundle_skipped` with the reason payload.
- **Outstanding gaps**: Arbitrary `<animateMotion>` paths still need point-list reduction, skew/matrix transforms require fallback, additive="sum" transforms currently collapse into single tracks, and we only persist spline metadata (no native PowerPoint extensions yet).

## Open Questions

- How granular should the default sampling be (per second vs per keyframe)? Benchmarks required.
- Do we need to support interactivity beyond timeline playback (e.g. triggers)? Out of scope for the initial port.
- How do we package optional assets (audio/video) if encountered? Likely follow the existing media pipeline.

## Next Steps

1. Reduce arbitrary motion paths (quadratic/cubic segments) into `<a:ptLst>` sequences so `<animateMotion>` is not limited to simple translations.
2. Explore richer easing preservation: store spline extensions or generate additional `<a:tav>` spans when the error budget is exceeded, then teach policy how to react.
3. Document and route unsupported transform types (skew/matrix) plus additive="sum" combinations through existing slide/raster fallbacks.
