# ADR: DrawingML Writer & PPTX Export Roadmap

- **Status:** In Progress
- **Date:** 2025-XX-XX
- **Owners:** svg2ooxml migration team
- **Depends on:** ADR-policy-map, ADR-text-fonts-and-wordart
- **Blocks:** ADR-text-layout, ADR-exporter-packaging (subset)

## Context

SVG→PPTX output fidelity now depends on two converging code paths:

1. The DrawingML writer, which turns the IR scene into individual slide XML fragments.
2. The PPTX package builder/export pipeline, which wraps those fragments, relationships, fonts, and media into a deliverable archive.

As of ADR-text-fonts-and-wordart we have:

* A cleaned-up text pipeline producing `EmbeddedFontPlan`, WordArt metadata, and richer run information.
* A staging DrawingML writer that now emits `DrawingMLRenderResult` snapshots with an asset registry for fonts, media, and diagnostics.
* A PPTX packager refactored to consume the asset registry, handling slide media, embedded fonts, and multi-slide outputs via `_PackagingContext` helpers.

However, writer/exporter responsibilities are still interleaved with legacy heuristics (template fragments, ad-hoc relationship updates), and the new font embedding flow needs a clear contract for packaging font subsets, relationship wiring, and content types. Without a dedicated ADR we risk ad-hoc fixes and divergence from the svg2pptx baseline.

## Decision

Document a separate roadmap for the DrawingML writer & PPTX exporter to:

* Decouple writer responsibilities (shape assembly, WordArt body generation, run-level styling) from packaging concerns (relationships, content types, media manifests).
* Define interfaces that carry embedding and diagnostics metadata from `DrawingMLWriter` to the exporter via the asset registry rather than incidental lists.
* Establish a packaging surface that can scale to multiple slides, alternative layouts, and upcoming visual regression suites.

This ADR becomes the authoritative plan for the remaining work after ADR-text-fonts-and-wordart’s Slice 4, and before end-to-end validation (Slice 5).

## Goals

1. **Writer modernisation**
   * Emit DrawingML text runs with kerning, language, and font-slot metadata driven by the policy layer.
   * Expand WordArt rendering to include body properties (auto-fit, warp parameters) and reflow support.
   * Split shape/scene generation into composable helpers that can be unit-tested independently.

2. **Exporter packaging clarity**
   * Formalise the asset registry contract (fonts, media, diagnostics) and surface a single packaging API that consumes those descriptors.
   * Move template mutations (`presentation.xml`, relationships, content-types) into explicit functions with schema-aware helpers rather than string replacements.
   * Support multiple slides, slide masters, and additional relationships without duplicating template fragments.

3. **Diagnostics & observability**
   * Preserve mapping between IR elements and packaged assets (shape ID ↔ relationship ID ↔ file path) for debugging and visual regression tooling.
   * Ensure embedding decisions (permission denied, subset failure) bubble up through consistent metadata for CLI/API reporting.

## Non-goals

* Rewriting the entire PPTX exporter or template set (we reuse the clean-slate template with minimal deltas).
* Integrating full multi-slide authoring—we target single-slide MVP with room for future extension.
* Replacing the svg2pptx packaging CLI; this ADR only scopes core library behaviour.

## Implementation Plan

1. **Refactor writer entry points**
   * Extract `render_textframe`/`render_wordart` body property builders.
   * Introduce an asset registry that the writer can populate (fonts, filter blobs, hyperlinks) with typed descriptors.
   * Teach run serialization to consume `EnhancedRun` metadata while staying backwards compatible with basic `Run`.

2. **Package builder redesign**
   * Replace string replacements with XML-aware updates for presentation part, relationships, and content types.
   * Introduce a packaging context that accepts the writer’s asset registry and produces unique filenames, relationship IDs, and overrides.
   * Generalise existing media helpers so fonts, vector fallbacks, and future assets reuse the same code paths.

3. **Testing & validation**
   * Unit tests for font packaging (writes `/ppt/fonts/*.ttf`, registers relationships/content-types).
   * Snapshot tests that diff generated slide XML for WordArt vs. non-WordArt text frames.
   * Integration test: build PPTX, unzip, and verify relationships/content-types for fonts and images.
   * Outline future visual regression hooks that leverage packaged metadata.

## Consequences

* Cleaner separation between renderer and packager surfaces, aligning with dependency injection from ADR-policy-map.
* Easier to extend the exporter later (multi-slide, notes, masters) since relationships/overrides are centralised.
* Slightly higher upfront complexity—service setup must propagate the asset registry—but enables deterministic packaging behaviour.

## Status Notes

* Text pipeline already provides enriched metadata (`EmbeddedFontPlan`, WordArt candidate data). Writer/exporter must honour those contracts.
* Current template assets remain valid; no binary templates need updating, only in-memory XML adjustments.
* End-to-end validation (Slice 5 of ADR-text-fonts-and-wordart) will rely on this ADR; completion should be tracked in both documents.
* 2025-03-XX — Implemented asset registry-backed `DrawingMLRenderResult` and packaging context; PPTX builder now deduplicates media/fonts and supports multi-slide output via the new API.

## Open Questions

1. Should we store packaged font data on disk before zipping (for CLI debugging), or keep everything in-memory?
2. How do we expose packaging diagnostics—logger, return object, or callback interface?
3. Do we need a migration helper to port svg2pptx template customisations (themes, masters) once multi-slide support lands?

By separating writer/exporter concerns into this ADR we keep the text roadmap focused while providing clear guidance for remaining packaging work. Once implemented, the packaging layer will reliably surface embedded fonts, relationships, and metadata required for Slice 5 validation.
