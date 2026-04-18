% Filter Exporter Strategy
% Draft — 2025-XX-XX

# Context

svg2ooxml currently resolves SVG filter primitives into `FilterEffectResult`
objects that carry DrawingML fragments or policy metadata. To unblock
bringing the filter stack into the PPTX exporter, we temporarily emit comment
hooks (`<!-- svg2ooxml:… -->`) so downstream components can identify the
intended effect. This keeps unit tests deterministic, but nothing in the
pipeline converts those hooks into working PowerPoint effects, EMF vector
fallbacks, or raster images.

By contrast, svg2pptx already ships a mature filter renderer:

- `core/filters/*` contains per-primitive processors that emit real DrawingML,
  EMF, or raster payloads.
- `core/services/filter_service.py` federates the registry, policy engine,
  and fallback strategies. It surfaces actual `<a:effectLst>` fragments or
  embeds EMF (`a14:base64Blip`) when a raster/vector fallback is the only
  option (ADR‑021).
- Policy rules decide when to use native blur/drop-shadow vs. EMF vs. raster,
  and the mapper simply appends the returned `CustomEffect` objects.

The goal of this design is to replace the svg2ooxml exporter hooks with
concrete rendering strategies, draw on svg2pptx’s proven architecture, and
stage the remaining work so we can deliver visual parity without a monolithic
rewrite.

# Goals & Non-Goals

## Goals

1. **Native Rendering** – Map the common primitives (blur, shadow, glow,
   flood, offset, color matrix, component transfer, morphology, convolve,
   lighting, composite, blend, merge/tile) to real DrawingML where PowerPoint
   has capable effects.
2. **Vector/Raster Fallbacks** – Provide a deterministic EMF (vector-first)
   path and a raster path, respecting policy hints and filter metadata.
3. **Pipeline Integration** – Allow `FilterService.resolve_effects` to output
   `CustomEffect` objects ready for PPTX serialization without extra hooks.
4. **Testable Surface** – Define unit/integration tests so we can validate
   each strategy in isolation (effect fragments) and end-to-end (mock PPTX
   builder).
5. **Incremental Adoption** – Keep changes staged; early merges should still
   provide value even if some primitives remain on the fallback path.

## Non-Goals

- Re-implement the entire svg2pptx filter module verbatim. We will port only
  the components required for svg2ooxml’s architecture, keeping policy and DI
  alignment.
- Finalize librsvg-based rasterization. We will design the interface but not
  deliver production-quality raster output in the first milestone.
- Converge the svg2pptx and svg2ooxml codebases immediately. Shared modules
  can be identified later if appropriate.

# Current State Summary (svg2ooxml)

_Update 2025-03:_ Composite, blend, component-transfer, lighting
(diffuse/specular), displacement-map, and turbulence primitives now emit
deterministic EMF fallbacks via `drawingml.emf_adapter`. The filter renderer
caches these assets and exposes them through `<a:blip>` placeholders so the PPTX
packager can embed real vector fallbacks instead of the original solid rectangle
stubs. Remaining primitives still rely on policy hints to request raster output
or future vector adapters.

Component|Responsibility|Limitations
---|---|---
`FilterService.resolve_effects`|Builds `FilterEffectResult` list, uses pipeline state for chaining, returns `CustomEffect` with hook comments.|Hooks are not understood by exporter; no EMF or raster output exists.
`FilterEffectResult`|Carries effect fragment, chosen strategy, fallback mode, metadata.|Metadata is rich enough for follow-up decisions.
`FilterRegistry`|Processes primitives, tracks pipeline state, seeds `SourceGraphic`/`SourceAlpha` with hook comments.|Outputs comment hooks for most unsupported primitives.
Policies|`FilterPolicyProvider` exposes simple knobs (strategy, anisotropic blur).|No per-primitive thresholds (e.g., drop shadow distance).
Mapper|Appends `CustomEffect` to IR elements.|Vector fallbacks now contain real EMF data for composite/blend; other primitives still depend on policy to select raster/vector modes.

# Reference Implementation (svg2pptx)

Key takeaways from svg2pptx (vetted via ADRs 020 & 021 and code under
`core/filters/` and `core/services/filter_service.py`):

- **Registry-first** – Each primitive either emits native DrawingML or
  returns structured metadata so the service can choose EMF/raster fallback.
- **Effect Composition** – Composite/blend/merge manipulates already-rendered
  fragments; they do not emit placeholder comments.
- **Fallback Strategy** – `_rasterize_filter` generates EMF via
  `core/map/emf_adapter.py`, caches blobs, and produces valid `<a14:blip>` DML.
- **Policy Checks** – EMF vs. raster is policy-driven; anisotropic blur steps
  down to EMF/raster depending on quality thresholds.
- **Testing** – Unit tests assert the presence of actual DML (`<a:blur>`,
  `<a:outerShdw>`, `<a:duotone>`, etc.) and EMF markers.

We will mirror this flow but adapt to svg2ooxml’s modules and dependency
graph.

# Proposed Architecture

```
SVG Filter Element
     │
     ▼
FilterRegistry (existing)
     │ FilterResult (drawingml / metadata / fallback)
     ▼
FilterRenderer (new)
 ├─ Native effect builder
 ├─ EMF adapter (vector-first)
 └─ Raster adapter (librsvg/in-memory Surface)
     │
     ▼
FilterService.resolve_effects → CustomEffect / fallback metadata
     │
     ▼
IR Mapper → PPTX Builder (existing)
```

## Components

### 1. `FilterRenderer`
New module (`src/svg2ooxml/drawingml/filter_renderer.py`) that:

- Accepts a `FilterEffectResult` list plus context (policy, viewport, dpi).
- Resolves the “effective strategy” per primitive (`native`, `emf`,
  `raster`), overriding service-level defaults as needed.
- Converts hook comments into true DrawingML using per-primitive helpers,
  reusing svg2pptx algorithms where possible.
- When `strategy` = `emf`, invokes the EMF adapter and returns the `<a:blip>`
  structure alongside metadata linking to the stored EMF blob.
- When `strategy` = `raster`, passes SVG subtree to a raster adapter (stubbed
  initially to deterministic placeholder) and returns `<a:blipFill>`.

### 2. Per-primitive builders
Module layout inspired by svg2pptx:

Path|Responsibility
---|---
`filters/drawingml/blur.py`|`feGaussianBlur`, identifies anisotropic vs. isotropic, returns `<a:effectLst><a:blur .../>`.
`filters/drawingml/shadow.py`|`feDropShadow` → `<a:outerShdw>`, `feFlood`+`feOffset` combos.
`filters/drawingml/color.py`|`feColorMatrix`, `feComponentTransfer`.
`filters/drawingml/morphology.py`|Maps to `<a:softEdges>` or `<a:glow>` approximations; notes when EMF is required.
`filters/drawingml/convolve.py`|`feConvolveMatrix` → `<a:biLevel>` or custom ext (mirroring svg2pptx).
`filters/drawingml/lighting.py`|`feDiffuseLighting`, `feSpecularLighting`, updates `<a:lightRig>` or uses EMF fallback.
`filters/drawingml/composite.py`|`feComposite`, `feBlend`, `feMerge`, `feTile`, merges fragments while respecting order.

Each module should accept a `FilterEffectResult` (metadata already parsed) to
avoid reparsing XML.

### 3. EMF & Raster adapters

- **EMF**: Port svg2pptx’s `core/map/emf_adapter.py` and related helpers into
  `svg2ooxml/io/emf/`. Provide a thin API:
  `generate_emf(filter_element, viewport, dpi) -> EmfResult`.
- **Raster**: Stub initial implementation returning a base64-encoded PNG with
  a simple gradient (deterministic). Later integrate librsvg.
- Cache EMF/raster outputs keyed by filter definition to avoid repeated work.

### 4. Policy integration

- Extend `FilterPolicyProvider` options: `max_shadow_blur`, `max_convolve_kernel`,
  `prefer_emf_for_component_transfer`, etc.
- `FilterRenderer` consults `filter_result.metadata` + policy to decide when
  to trigger EMF/raster fallback even if a native builder exists.

### 5. Mapper / PPTX Builder

- Mapper already appends `CustomEffect`. Ensure the builder understands the
  returned fragments:
  - `<a:effectLst>` for native effects → existing path.
  - `<a:blipFill>` (EMF/raster) → ensure relationships created (port svg2pptx
    logic from `core/presentation/blip_writer.py`).

# Strategy Matrix

Primitive|Native DrawingML|EMF/Raster fallback
---|---|---
`feGaussianBlur`|`<a:blur rad="…">` (anisotropic approximated via average)|EMF when policy disallows anisotropic native; raster for very large radius.
`feDropShadow`|`<a:outerShdw …>`|Raster if multiple stacked shadows (rare).
`feGlow`|`<a:glow …>`|Raster for complex color stops.
`feFlood`|`<a:solidFill>` overlay combined with composite.|Raster if combined with morphology requiring multi-pass.
`feOffset`|Translate geometry; combines with other primitives to adjust effect metadata.|EMF if offset applied to EMF fallback chain.
`feColorMatrix`|Map to `<a:duotone>`, `<a:biLevel>`, or `<a:lumMod>` depending on type.|Raster when matrix exceeds OOXML support.
`feComponentTransfer`|Chain `<a:duotone>`, `<a:biLevel>`, `<a:gamma>` approximations; fallback to EMF when multi-channel tables.|Raster final fallback.
`feMorphology`|`<a:softEdges>` or `<a:glow>` for dilate; EMF for erode with large radius.|Raster for extreme kernels.
`feConvolveMatrix`|Native when kernel fits OOXML `biLevel`/`duotone` patterns; else EMF.|Raster for arbitrary kernels.
`feComposite`|Merge upstream `<a:effectLst>` into single list, optionally adjust alpha.|Fallback only when inputs unresolved.
`feBlend`|Blend colors via `<a:effectLst>` combinations; EMF for modes unsupported by OOXML (e.g., color-dodge).|Raster ultimate fallback.
`feMerge`/`feTile`|Concatenate effects; no new DML required.|Fallback when sources unresolved.
`feImage`|If href is embedded, convert to `<a:blip>` relationship; else EMF placeholder.|Raster same as native (existing image).
`feDiffuseLighting`/`feSpecularLighting`|Approximate via `<a:lightRig>` or `<a:scene3d>` once ported; EMF fallback otherwise.|Raster optional.
`feDisplacementMap`|Vector output via `<a:duotone>` (per svg2pptx).|Raster fallback for complex maps.
`feTurbulence`|No native mapping → EMF/raster only.|Raster default.

# Implementation Plan

## Phase 1 – Infrastructure
1. Introduce `FilterRenderer` and wire into `FilterService.resolve_effects`.
2. Port svg2pptx EMF adapter (minimal functionality) and stub raster adapter.
3. Replace comment hooks with `build_exporter_hook` usage only during testing
   (e.g., behind feature flag) to ease validation.

## Phase 2 – Native builders
1. Port Gaussian blur, drop shadow, glow, color matrix, offset, flood, merge,
   tile, composite, blend from svg2pptx.
2. Extend `FilterEffectResult.metadata` to carry any additional fields
   required (e.g., `shadow_offsets`, `blend_mode`).
3. Update tests: existing hook assertions → actual DML checks.

## Phase 3 – Advanced primitives
1. Port morphology, component transfer, convolve matrix, displacement map
   with policy-based thresholds.
2. Implement lighting approximations or EMF path with metadata for exporter.
3. Document remaining edge cases (e.g., chain referencing `BackgroundImage`).

## Phase 4 – Raster integration
1. Integrate librsvg (optional dependency) via `io/rasterization`.
2. Plumb DPI, viewport, and cropping metadata to raster adapter.
3. Update policy toggles to choose between EMF and raster.

# Testing Strategy

Level|Tests|Notes
---|---|---
Unit|Per-primitive builder tests verifying generated DML matches expected OOXML.|Use svg2pptx fixtures as references; update existing unit tests.
Integration|`FilterService.resolve_effects` scenarios covering chaining, strategy overrides, policy hints.|Important to include EMF/raster fallback assertions.
Exporter|PPTX builder tests ensuring `<a:blip>`, relationships, and effect lists survive round-trip.|Leverage temporary stub builder or extend existing integration harness.
Visual (future)|Golden PPTX comparisons once exporter pipeline stable.|Optional but recommended for regression safety.

# Open Questions

1. **Librsvg vs. CairoSVG** – We need to evaluate the feasibility of shipping
   librsvg in our distribution; the design allows swapping raster adapters.
2. **EMF Packaging** – svg2pptx still embeds base64; we should decide whether
   to embed or package as separate relationships.
3. **Performance** – Convolution and lighting may be expensive; caching should
   include policy parameters and viewport.
4. **Shared code with svg2pptx** – Future step could extract common filter
   builders into a shared library. For now we will port selectively.

# Deliverables

- `FilterRenderer` module with native, EMF, raster strategies.
- Updated `FilterService` and registry to call renderer.
- Expanded policy provider with new knobs.
- Comprehensive unit tests replacing hook-based assertions.
- Documentation updates (`docs/adr/ADR-filters-port.md`) once native output
  lands.

With this plan we can progressively replace exporter hooks, lean on
svg2pptx’s proven behaviour, and keep the migration manageable in reviewable
chunks.
