# ADR: Text, Font, and WordArt Strategy

- **Status:** In Progress
- **Date:** 2025-XX-XX
- **Owners:** svg2ooxml migration team
- **Depends on:** ADR-policy-map, ADR-geometry-ir, ADR-filters-port
- **Blocks:** ADR-text-layout, ADR-exporter-packaging

## Context

svg2pptx ships a rich text pipeline:

* `core/policy/text_policy.py` evaluates per-frame complexity, glyph availability, and warp compatibility, producing `TextDecision` values (native, EMF fallback, WordArt, outline) with rationale and metadata.
* Font discovery/subsetting is handled by `FontService`, `FontEmbeddingEngine`, and caches under `core/services`, using fontTools to locate fonts, validate embedding rights, and subset requested glyph sets.
* Deterministic curve positioning + WordArt classification (see `core/algorithms/deterministic_curve_positioning.py`, `curve_text_positioning.py`, `text_warp_classifier.py`) recognises patterns (arc, wave, inflate/deflate, triangle) to emit native PowerPoint WordArt presets.
* Text mappers honour policy decisions, attaching font metadata, kerning/leading, theme overrides, and packaging fonts or EMF/vector fallbacks as needed.

svg2ooxml currently exposes only basic runs (`ir/text.Run`), no font services, and a placeholder `TextPolicyProvider`. Text is emitted as simple `<a:r>`, text-on-path degrades to planar geometry, and features such as embedded fonts, theme major/minor fonts, word spacing, kerning, language tagging, and outlining are not present.

## Goals

1. **Font discovery & embedding**
   * Detect embedded SVG fonts, `@font-face` references, and referenced families; locate system fonts via a DI-provided font service.
   * Determine embedding rights, subset characters, and package font data into PPTX relationships when allowed.
   * Record major/minor font usage and map runs to theme slots when possible.

2. **Policy-driven text decisions**
   * Replace placeholder policy providers with a `TextPolicy` similar to svg2pptx, covering font availability, outline fallback, WordArt detection thresholds, complexity scoring, and conservative modes.
   * Introduce policy knobs for kerning, leading, colour/outline inheritance, language-based fallback families, and glyph conversion thresholds.

3. **WordArt vs. warp strategy**
   * When deterministic curve positioning matches a supported WordArt preset with sufficient confidence, emit native WordArt; otherwise fall back to glyph warping or outline/EMF.
   * Preserve text metadata (language, kerning, leading, colours, outlines) regardless of decision; annotate IR metadata with policy decisions for downstream diagnostics.

4. **Writer integration**
   * Extend DrawingML writer to output WordArt fragments, run-level kerning/leading, language codes, font metrics, and theme mapping. For glyph outlines, ensure custom geometry or EMF fallbacks carry the correct metadata.

5. **Packaging & export**
   * Bundle embedded fonts via the export pipeline, generate relationship parts, and update manifest entries surfaced through the DrawingML asset registry.

## Decision

Implement a multi-slice roadmap that ports the svg2pptx text pipeline into svg2ooxml while keeping modules modular:

1. **Text Policy & Targets**
   * Introduce `policy/providers/text.py` replacement with a real `TextPolicy` object model.
   * Extend `PolicyTarget` registry to include `mask` (already done) and update text provider to return structured decisions (embedding behaviour, warp allowance, glyph fallback).

2. **Font Services**
   * Port or reimplement `FontService` and `FontEmbeddingEngine` under `src/svg2ooxml/services/fonts/`, adding provider registration and DI wiring (`services/providers/font_provider.py`).
   * Provide feature flags (enable embedding, subset level, preserve hinting) controlled by policy.
   * Create data classes for font metadata, caching, and packaging similar to `FontEmbeddingStats` / `EmbeddedFont`.

3. **IR Enhancements**
   * Extend `ir/text.py` with `EnhancedRun`-style metadata: language tags, kerning, letter/word spacing, baseline shifts, text transforms, fill/outline.
   * Add `TextPathFrame` or equivalent to represent text-on-path with metrics (currently `text_path` modules are stubs).

4. **Mapper Modules**
   * Split text conversion into `map/converter/text.py`, mirroring the rectangle refactor, handling: run splitting, policy evaluation, WordArt detection, glyph outline generation, and fallback to EMF.
   * Integrate deterministic curve positioning algorithms so text-on-path flows can classify WordArt presets.
   * Hook mask/language metadata into text metadata for downstream writer decisions.

5. **DrawingML Writer**
   * Add WordArt support (render appropriate `<a:bodyPr>` warp presets, highlight anchors, etc.).
   * Emit `<a:latin>`, `<a:ea>`, `<a:cs>` for major/minor fonts and set language via `lang`.
   * Honour kerning (`kern`), leading (`lnSpc`), outline fills, and theme accent overrides.

6. **Export Packaging**
   * Update writer/exporter to write embedded fonts (font parts, relationships).
   * Ensure EMF/vector fallbacks for glyph outlines are packaged with metadata (size, relationships).

## Status Notes

* 2025-03-XX — DrawingML writer now returns `DrawingMLRenderResult` snapshots with an asset registry, and the PPTX exporter consumes those assets for media/font packaging (see ADR-drawingml-writer-export implementation).

## Implementation Slices

- **Slice 0 – Policy decider + diagnostics**: Port svg2pptx’s `core/policy/text_policy.py` into `src/svg2ooxml/policy/text_policy.py`, adding the runtime `TextPolicy.decide`, `TextDecision`, and `DecisionReason` plumbing so `TextPolicyProvider` emits actionable metadata. Backfill coverage in `tests/unit/policy/test_text_policy.py`, exercising conservative mode, run-count ceilings, and missing-font strategies.
- **Slice 1 – Font discovery services**: Move `core/services/font_service.py`, `font_system.py`, and `font_fetcher.py` into `src/svg2ooxml/services/fonts/`, wiring them through the existing registry in `services/providers`. Register macOS/Windows/Linux directories plus CLI/env overrides (`--font-dir`, `SVG2OOXML_FONT_DIRS`) and add unit tests for fallback ordering (`tests/unit/services/font/test_directory_provider.py`, `tests/unit/services/font/test_font_service.py`).
- **Slice 2 – Embedding engine + caches**: Replace the stub in `services/fonts/embedding.py` with the svg2pptx `FontEmbeddingEngine`, `font_embedding_cache.py`, and `font_embedding_rules.py`, integrating fontTools to honour `fsType` guards and subset strategies. Update `TextConversionPipeline._plan_embedding` to persist glyph stats and surface embedding data via `DrawingMLRenderResult.assets`, with regression tests that unzip the PPTX fixture and assert `ppt/fonts/*.odttf` presence.
- **Slice 3 – Text path + WordArt classification**: Port `core/services/text_path_processor.py`, `core/algorithms/deterministic_curve_positioning.py`, and `text_warp_classifier.py` into `src/svg2ooxml/geometry/algorithms/` and `services/text/`. Extend `ir/text_path.py` to mirror svg2pptx’s metrics and update `TextConversionPipeline._plan_wordart` to use the deterministic classifier before falling back to heuristics. Cover with unit tests in `tests/unit/map/text/test_wordart_classifier.py` and integration fixtures that exercise SVG `<textPath>` samples.
- **Slice 4 – Mapper & writer integration**: Refine `map/converter/text.py` to emit `EnhancedRun` metadata (kerning, language, spacing, outline) and drive policy decisions for WordArt vs. glyph outlines. Update `drawingml/shapes_runtime.py` and `drawingml/writer.py` to output `<a:latin>/<a:ea>/<a:cs>` font slots, kerning (`kern`), leading (`lnSpc`), and WordArt body properties, adding unit coverage in `tests/unit/drawingml/test_text_writer.py`.
- **Slice 5 – Packaging & end-to-end validation**: Teach the export pipeline (`io/presentation/packager.py`, `presentation/writer.py`) to serialise font parts, relationship entries, and content types from the DrawingML asset registry, and ensure EMF/vector fallbacks travel with metadata. Add integration (`tests/integration/text/test_font_embedding_pipeline.py`) and visual (`tests/visual/golden/text_wordart_*`) baselines comparing svg2pptx outputs for embedded fonts, WordArt presets, and fallback scenarios.

## Testing Strategy

* **Unit tests**
  - Policy decisions: high/low/balanced quality scenarios, missing fonts, conservative mode, WordArt classification toggles.
  - Font service: font discovery on fixture directories, permission parsing, subset caching.
  - Text mapper: translating sample SVG text (plain, missing fonts, on-path) into IR with expected metadata.
  - WordArt classification: use svg2pptx baseline data (arc, wave, inflate/deflate) to assert correct preset/tolerance.
  - Writer: verify runs include kerning/leading/language tags; WordArt output matches preset expectation; font relationships emitted when embedding requested.

* **Integration tests**
  - Convert sample SVGs covering: embedded fonts, references to common families, warped text, multi-language runs, horizontal/vertical writing.
  - Check generated IR scenes and DrawingML fragments (snapshot tests).

* **Visual/regression tests**
  - End-to-end conversions producing PPTX artifacts to confirm WordArt vs. outline decisions render identically in PowerPoint.
  - Compare subset font sizes and ensure packaging includes expected font parts.

## Risks & Mitigations

* **Font licensing:** embedding may be prohibited; policy must respect fsType and fall back gracefully.
* **Platform variability:** system font paths differ; ensure font service handles missing directories.
* **Complex scripts:** shaping requires HarfBuzz or similar; initial implementation may focus on Latin scripts with clear TODOs for complex shaping.
* **WordArt misclassification:** fallback to warp/glyph when confidence low; log decisions for diagnostics.
* **Performance:** font subsetting and WordArt fitting can be heavy—cache results and allow configuration to disable features.

## Open Questions

1. Should we rely solely on WordArt presets or support custom warp geometry for unmatched paths? (Current plan: WordArt when confident, EMF/outline otherwise.)
2. How far do we push embedded fonts by default—always embed when available, or rely on system fonts unless configured?
3. Do we need HarfBuzz or other shaping libraries to match PowerPoint layout fidelity for complex scripts?
4. How to expose text policy overrides via CLI/SDK (quality profiles, embedding toggles)?

## Next Steps

1. **WordArt integration** — Replace heuristic preset guesses with svg2pptx’s deterministic text warp classifier so we correctly map path geometry to PowerPoint presets and set confidence thresholds from empirical data.
2. **Embedding pipeline** — Wire `FontEmbeddingEngine` into fontTools, emit subset font parts/relationships during export, and persist `DrawingMLRenderResult.assets.fonts` into the packaging step with regression tests that inspect generated PPTX. Break this into:
   - integrate fontTools and build subsetting (fsType checks, glyph extraction, variation/collection handling) with unit coverage around `FontEmbeddingEngine`.
   - extend the PPTX packaging layer to materialise `ppt/fonts/*.odttf`, relationships, and content types from the asset snapshot, plus fallbacks when embedding is disallowed.
   - add regression tests that convert sample SVGs, unzip the resulting PPTX, and assert embedded font presence, relationship wiring, and fallback behaviour.
3. **Font discovery hardening** — Register platform/system font directories by default (macOS, Windows, Linux) and surface CLI/config switches (`--font-dir`, `--disable-wordart`, etc.) that feed into the policy provider overrides.
4. **Writer enhancements** — Emit kerning/leading/language attributes and honour theme font slots; add fallbacks when native WordArt is disabled or confidence is low so diagnostics remain consistent.
5. **Coverage & validation** — Add integration fixtures that exercise embedded fonts, WordArt, and fallback paths, including visual regression comparisons against svg2pptx outputs and pptx inspection scripts.

By mirroring svg2pptx’s proven text pipeline, this ADR provides a roadmap to bring svg2ooxml’s font and text handling to parity, enabling high-fidelity, PowerPoint-native output with reliable fallbacks.
