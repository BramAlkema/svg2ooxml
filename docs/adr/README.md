# Architecture Decision Records

This document consolidates all architectural decisions for svg2ooxml.
Individual ADR files have been archived — this is the single source of truth.

---

## Core Pipeline

### Parser Decomposition
Break the monolithic parser into focused modules: dom_loader, normalization,
style_context, reference_collector. Services injected via `configure_services()`
to avoid global state mutation.

### Geometry & IR
Typed intermediate representation: `IRScene`, shapes, text, paint, effects.
Geometry stack handles paths, clip regions, and optional NumPy acceleration.
All IR nodes are frozen dataclasses.

### Units, ViewBox, Transforms
Centralized `UnitConverter` with fluent API and EMU constants. `ViewportEngine`
handles meet-or-slice logic. Transform utilities provide decomposition and
fractional EMU math. Eliminates ad-hoc coordinate conversions.

### Policy, Services, Mapping
`PolicyEngine` with pluggable providers by domain (image, text, geometry, mask,
filter). `ConversionServices` registry with dependency injection. Mapper ABC
defines element traversal pattern (path, image, text mappers).

### Batch Integration
Parser/preprocess pipeline for job payloads. Huey task integration for
background processing. Services injected via `configure_services()`.

---

## Rendering & Output

### Resvg Rendering Strategy
Three-tier rendering ladder: native DrawingML → resvg promotion → legacy raster.
Resvg filters/masks/clips executed via filter planner; output packaged as PNG or
promoted to EMF/vector. Strategy toggles exposed via exporter config and env vars.

### DrawingML Writer
Writer emits `DrawingMLRenderResult` with asset registry (fonts, media,
diagnostics). Exporter consumes registry for slide/relationship/content-type
generation. Separates shape assembly from PPTX packaging.

### EMF Procedural Fallbacks
Hybrid EMF containers for procedural effects (turbulence, lighting) combining
vector instructions with embedded bitmap tiles. Routing: native DrawingML →
mimicked DrawingML → hybrid EMF → PNG fallback.

### Font Embedding (EOT)
EOT-based pipeline converts subset OpenType fonts for PPTX packaging.
`PPTXPackageBuilder` writes .fntdata parts with proper relationships.
FontForge optional with graceful degradation.

### Text & WordArt
Multi-strategy text handling: native text, EMF fallback, WordArt presets,
outline conversion. Font discovery via `FontService`/`FontEmbeddingEngine`.
Deterministic curve positioning for WordArt classification.

### Color Engine
Fluent `Color` API with OKLab/OKLCh operations, harmony helpers, accessibility
checks. Bridges with lightweight Color model for backward compatibility.
Enables gradient palette optimization and raster normalization.

### Filter System
`FilterContext`/`FilterResult`/abstract `Filter` with registry and pipeline
dispatcher. Primitives: blur, shadow, glow, soft-edge, color matrix,
displacement, blend/composite, lighting, turbulence. Emits DrawingML effects
with rasterization hooks.

### EffectDag & Color Transforms
Dual native-effect architecture: `effectLst` for simple DrawingML effects,
`effectDag` for compositing/mask graphs needing alpha operators. Context-aware
color-transform emission. Policy-gated rollout.

---

## Animation

### SMIL Animation Support
SMIL/animated attribute sampler, timing engine, and multi-slide orchestrator.
IR animation types, SMIL parser, timeline sampler with interpolation. Native
timing XML writer with policy-driven fallbacks for easing/motion paths.

### Animation Writer Rewrite (ADR-020, completed)
All handlers return lxml elements; single `to_string()` at serialization
boundary. Fixed ID allocation, added click group wrapper, centralized unit
conversion. Implemented event-based begin triggers, paced calcMode,
additive/accumulate attributes, multi-keyframe translate, matrix decomposition.

### SMIL Parity & W3C Gating
Prioritizes SMIL semantic parity (begin triggers, mpath resolution, motion
rotation). Animation-focused W3C execution profiles as release gates.
Per-fragment degrade/omit behavior instead of timing suppression.

### Multi-Keyframe & Orbital Rotation
Multi-keyframe rotate (e.g., 0→360→0) splits into sequential `<p:animRot>`
segments. Rotation with cx/cy center emits companion `<p:animMotion>` orbital
arc. stroke-dashoffset animation maps to Wipe entrance effect. SMIL
min/max/restart/accumulate parsed and applied.

---

## Text Rendering Strategy

### Three-Tier Text Pipeline
1. **Native DrawingML** (preferred) — editable text with FontForge→EOT font
   embedding. Used for uniform spacing (`spc`), uniform rotation (`xfrm rot`),
   writing-mode (`vert`), baselines, and standard text properties.
2. **WordArt `prstTxWarp`** — text on curves. Always used for `textPath`;
   default preset (`textArchUp`) when no classifier match. Keeps text editable.
3. **Glyph outlines via Skia** (last resort) — per-character custGeom shapes
   for non-uniform dx/dy/rotate. Vector quality, not editable. Skia Font
   objects cached by (family, size).

### WordArt-First Policy
WordArt preferred over outlines for textPath: `prefer_native_wordart=True`,
lowered confidence threshold, fixed `prstTxWarp` schema (child element, not
attribute). Classifier relaxed for arch detection.

---

## Quality & Testing

### Eliminate String-Parse-Graft XML (ADR-021)
All XML-generating functions return lxml elements instead of strings.
`graft_xml_fragment()` helper as transitional bridge. Covers gradients, paint,
paths, filters, masks.

### Centralize Unit Conversions (ADR-022)
Consolidates scattered `× 60000` (angle), `× 100000` (opacity/scale), and EMU
conversions into `common/conversions/` utilities. Eliminates magic numbers and
inconsistent rounding.

### OOXML Schema Compliance (ADR-023, completed)
97 pre-existing schema violations fixed: headEnd/tailEnd ordering, filter bugs,
non-standard clipPath/mask elements. PowerPoint repairs eliminated. PPTX passes
OpenXML audit.

### Batch Performance (ADR-024)
Streaming build (O(1) memory), slide-level cache (warm re-runs ~95% faster),
parallel rendering (8-core ~4-6× speedup). Targets 2-3 min → 30-45s cold,
3-5s warm.

### Quality Roadmap (ADR-025, completed)
Deterministic W3C sampling + OpenXML audit gating in CI. Resvg-only default
path active. Filter/font hardening complete. Docker ergonomics ready.

### Dependency Footprint (ADR-026)
Dependency tiers: resvg + skia-python required, FontForge optional, LibreOffice
+ OpenXML audit test-only. Python 3.13 single runtime. Orbstack container for
full-stack development.

---

## Infrastructure (archived)

> The GCP project `powerful-layout-467812-p1` was deleted 2026-01-16.
> All Cloud Run, Firebase, and related CI/CD are non-functional.
> These decisions are preserved for reference if the service is rebuilt.

### Figma Export on Cloud Run (ADR-014)
Cloud Run with Cloud Build triggers, Cloud Storage staging, Firestore job
tracking, Google Drive/Slides API integration. Scalable serverless endpoint
for Figma plugin.

### Queue, Throttling, Cache (ADR-015)
Huey task queue with Redis backend. Per-IP rate limiting via slowapi.
Font cache in Cloud Storage. Content-addressed conversion cache.

### gcloud Client Setup (ADR-016)
Local gcloud CLI configuration: auth, project/region, Cloud Run/Build
components, environment variables.
