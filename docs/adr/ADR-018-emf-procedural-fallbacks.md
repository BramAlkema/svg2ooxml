# ADR-018: EMF Enrichment for Procedural Filter Fallbacks

- **Status:** Proposed
- **Date:** 2025-03-09
- **Owners:** Renderer/Exporter Group
- **Depends on:** ADR-017 (resvg rendering strategy), ADR-filters-port, ADR-drawingml-writer-export
- **Replaces:** None

## Context

ADR-017 established a resvg-first pipeline with EMF/vector promotions for
simple filter stacks. The long-term mandate is to keep the pipeline entirely on
the “new route”: native DrawingML first, then mimicked DrawingML, followed by
EMF and, only as a last resort, raster content. When resvg cannot stay pure
vector, the current fallback is a PNG (or placeholder) attached to the effect
metadata. This is adequate for single-frame fidelity but has three drawbacks:

1. **Editability:** PNG fallbacks are opaque to downstream editors; geometry,
   gradients, or lighting cannot be tweaked inside Office apps.
2. **Scalability:** Rasters do not scale well for high-DPI decks, especially
   for procedural effects such as turbulence-based lighting or mask textures.
3. **Asset sprawl:** Mixing vector and raster assets for a single filter output
   complicates packaging and telemetry (multiple attachments, redundant cache
   entries).

At the same time, the project already maintains an EMF builder capable of
emitting vector primitives (paths, brushes, clips). Recent enhancements added
support for DIB pattern brushes and `EMR_STRETCHDIBITS`, enabling hybrid EMFs
that combine vector instructions with small embedded bitmaps.

We want to take advantage of these capabilities so that "fallback EMF" becomes
the canonical container for procedural effects that cannot stay purely vector,
instead of dropping to PNG.

## Decision

Adopt a **resvg-first fallback ladder** that prefers DrawingML outputs and uses
EMF enrichment only after DrawingML options are exhausted:

1. **Stay native DrawingML whenever possible**: ensure resvg promotions attempt
   direct DrawingML emission for filter paths that can be represented with
   available DrawingML primitives (gradients, blurs, composites).
2. **Fallback to mimicked DrawingML** when native semantics are unavailable but
   we can approximate the effect using synthetic geometry or animated fills
   (e.g., tiled gradients, pre-expanded masks). Keep this entirely within the
   DrawingML writer to avoid legacy renderers.
3. **Promote procedural filters into hybrid EMFs** only when DrawingML paths
   (native or mimicked) cannot preserve fidelity. Generate compact bitmap tiles
   (or vector stipples) and embed them inside EMF via DIB pattern brushes or
   `StretchDIBits`, retaining surrounding vector geometry to mirror SVG
   semantics.
4. **Extend promotion heuristics** to recognise when a stack should route to
   mimicked DrawingML versus hybrid EMF versus PNG (e.g., turbulence feeding
   `feDiffuseLighting`, blur+morphology masks, patterned composites).
5. **Provide a high-level EMF API** on top of `EMFBlob` that mirrors GDI
   commands (SetWorldTransform, Polygon, BitmapOut, TextOut) to simplify
   procedural drawing logic inside promotions.
6. **Trace and classify hybrid EMFs**, emitting dedicated stage events and
   metadata (`resvg_turbulence_emf`, lighting-specific flags) so telemetry and
   dashboards can distinguish vector, hybrid, and bitmap paths.
7. **Fallback gracefully**: when EMF enrichment fails (format mismatch,
   unsupported plan, size constraints), continue to fall back to PNG but record
   the failure reason for diagnostics.

## Consequences

### Positive

- **New-route fidelity**: the fallback ladder stays within DrawingML before
  considering EMF, reinforcing the resvg-first pipeline.
- **Improved editability**: downstream editors retain access to vector geometry
  (e.g., clipping paths, transforms) and can recolor/tile embedded textures.
- **Better scalability**: a single procedural tile (or vector stipple) can be
  reused across slides without large PNG assets.
- **Unified packaging**: each fallback remains a single EMF asset, simplifying
  relationship management and caching.

### Negative

- **Implementation complexity**: generating procedural tiles, constructing BMP
  headers, and coordinating EMF records introduces more code paths and error
  handling.
- **Asset size variance**: hybrid EMFs may be larger than pure vectors;
  telemetry must watch for oversized fallbacks.
- **Compatibility risk**: Office renders most EMF features, but rare constructs
  (certain ROP codes, high-DPI textures) need validation across PowerPoint
  versions.

## Work Plan

1. **API uplift**
   - [ ] Wrap `EMFBlob` in a higher-level helper (e.g., `EMFCanvas`) exposing
     drawing/state methods inspired by pyemf3 (`BitmapOut`, `SaveDC`, etc.).
   - [ ] Document constraints (supported bit depths, maximum tile size, colour
     space) for embedded DIBs.

2. **Promotion heuristics**
   - [ ] Prioritise native DrawingML, then mimicked DrawingML, then hybrid EMF,
     recording which branch the pipeline selects.
   - [ ] Recognise turbulence + lighting/composite chains and route them through
     EMF enrichment before PNG fallback.
   - [ ] Provide opt-out policy knobs (e.g., `max_turbulence_tile_px`) so
     clients can force raster output when necessary.

3. **Telemetry & tracing**
   - [ ] Emit dedicated events (`resvg_turbulence_emf`, `resvg_dib_brush`) and
     aggregate counters (`hybrid_emf_promotions`) in `resvg_metrics`.
   - [ ] Surface metrics in job summaries for dashboards (see ADR-017, Phase 3).

4. **Validation**
   - [ ] Add integration tests that compare DrawingML-first and hybrid EMF
     outputs against refreshed golden baselines (lighting + turbulence, mask
     textures, etc.).
   - [ ] Run targeted visual diffs to ensure EMF tiling matches PNG baselines
     within tolerance.

5. **Rollout**
   - [ ] Pilot the enriched EMFs behind a feature flag (e.g., `filter.emf_enrich`).
   - [ ] Collect telemetry and user feedback; expand coverage once stable.

## References

- ADR-017: Resvg Rendering Strategy and Migration Plan
- pyemf3 (https://github.com/jeremysanders/pyemf3) – reference implementation for
  EMF drawing primitives
- docs/telemetry/resvg_metrics.md – resvg metrics sent to job summaries
