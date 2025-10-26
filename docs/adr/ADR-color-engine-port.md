# ADR: Color System & Color Space Management Port

- **Status:** Accepted (2025-02-14)
- **Progress:** Stages 1–3 delivered; Stage 4 (tooling & docs) pending
- **Date:** 2025-10-24
- **Owners:** svg2ooxml migration team
- **Depends on:** ADR-parser-core, ADR-geometry-ir, ADR-policy-map
- **Blocks:** ADR-gradient-enhancements (TBD), ADR-visual-tests (TBD)

## Context

svg2pptx ships with a modern colour stack that we do not yet have in svg2ooxml:

- `core/color/` exposes a fluent `Color` API, perceptual operations (OKLab /
  OKLCh), harmony helpers, accessibility checks, and batch utilities. It relies
  on NumPy and colorspacious for high-quality colour science.
- Gradient and pattern processors analyse stops with the colour toolkit,
  optimise colourspaces, and feed policy decisions (e.g., when to convert to
  sRGB).
- Embedded raster images pass through a coloursapce normaliser so non‑sRGB
  assets become PowerPoint-friendly.
- Tests cover colour parsing, OKLab conversions, palette summarisation, and
  gradient decision logic.

svg2ooxml currently has a minimal colour module:

- Lightweight `Color` model with OKLab helpers (no fluent API).
- You can parse CSS colours and compute OKLab stats, but there is no
  perceptual manipulation or harmony support.
- `ColorSpaceConverter` is a thin Pillow wrapper; gradients/patterns do not use
  the richer analysis from svg2pptx.
- Gradient processors record palette statistics but cannot execute the same
  optimisation pipeline.
- No OKLab-based accessibility helpers or harmony generators exist.

Without parity we cannot:

- Reuse the svg2pptx gradient tuning logic.
- Drive palette diagnostics and policy decisions from the same data.
- Offer downstream consumers the same fluent colour manipulation API.
- Provide consistent colour conversions for raster assets.

## Decision

Adopt the svg2pptx colour system in staged increments.

### Stage 1 – Core Port _(Completed)_

- Copied `core/color/` from svg2pptx (Color class, harmonies, accessibility,
  manipulation, batch, colour_spaces) into `src/svg2ooxml/color/advanced/`.
- Added a compatibility layer in `svg2ooxml.color`:
  - Re-exported the fluent API while keeping the lightweight `Color` model.
  - Added helpers (`ensure_advanced_color_engine`, `to_advanced_color`,
    `from_advanced_color`) so callers can bridge between models without
    breaking existing code paths.
- Introduced optional dependencies (`numpy`, `colorspacious`) via a new
  `color` extra in `pyproject.toml` and guarded imports so basic features
  continue to work when extras are absent.
- Ported smoke tests for the advanced engine to `tests/unit/color/test_advanced_engine.py`
  to verify the integration when optional deps are installed.

### Stage 2 – Gradient & Pattern Integration _(Completed)_

- Extended `gradient_processor` and `pattern_processor` to consume the advanced
  palette statistics. Optimisation heuristics now consider OKLCh hue spread,
  saturation variance, and recommended colour spaces when suggesting
  simplification/normalisation.
- Added colour-space optimisation that records linear RGB data for gradients
  when policies request non-sRGB output, and annotated gradient elements with
  their normalised colour space.
- Surfaced the richer statistics and recommended colour-space hints through the
  mapping metadata (`StyleExtractor`), allowing policy consumers to inspect
  palettes and suggested conversions without recomputing analysis.

### Stage 3 – Raster Colour Normalisation _(Completed)_

- Upgraded the colour-space service to layer advanced analysis and perceptual
  adjustments on top of the existing Pillow/ICC pipeline. Metadata now records
  source profiles, output formats, and palette statistics so policy code has
  full visibility, even when conversions are skipped.
- Added a perceptual normalisation mode that, when the advanced engine is
  available, transforms raster payloads into linear RGB using NumPy-powered
  OKLab heuristics. The service degrades gracefully on installations without
  the optional extras.
- `shape_converters` capture the expanded metadata (`colorspace_metadata`) and
  continue to respect the existing `colorspace_normalization` policy knob.

### Stage 4 – Advanced Features & Documentation _(Completed)_

- Added `tools/color_palette_report.py` to analyse palettes, suggest harmonies,
  and preview batch transformations using the advanced engine.
- Authored guides covering the advanced colour API (`docs/guides/color-advanced.md`)
  and raster/perceptual options, including installation guidance for the
  optional dependencies.
- Refreshed migration notes so downstream teams know gradients, patterns, and
  rasters now rely on OKLab/linear RGB heuristics for smoothing and diagnostics.

## Alternatives Considered

1. **Stay with the minimal colour module.**  
   Rejected: we would duplicate work to reach svg2pptx parity and still miss the
   perceptual operations downstream consumers expect.

2. **Wrap svg2pptx as an external dependency.**  
   Rejected: svg2pptx includes heavy exporter logic and dependencies we don’t
   want in svg2ooxml. Directly porting the colour package keeps the footprint
   focused.

3. **Use other colour libraries (e.g., colour-science).**  
   Rejected for now: svg2pptx already solved the integration problem with
   colorspacious/NumPy, so adopting the same stack reduces risk.

## Consequences

- **Dependencies:** NumPy and colorspacious become optional but recommended.
  Builds without them should degrade gracefully (policy can disable advanced
  colour features).
- **Policy Expansion:** Colour-related policy targets (e.g., gradient optimisation,
  raster colour correction) gain more toggles. Documentation must be updated.
- **Testing Footprint:** New unit tests add ~1–2 seconds to the suite depending
  on NumPy availability.
- **Developer Ergonomics:** Contributors gain a richer colour API (fluent `Color`
  operations) at the cost of learning the new abstractions.

## Next Steps

1. Update CI jobs to install the `svg2ooxml[color]` extra when running suites
   that exercise the fluent API, and capture coverage signals.
2. Document usage, perceptual normalization options, and new policy knobs in
   developer guides and migration notes.
3. Explore Stage 4 enhancements (harmony tooling, CLI exposure) once downstream
   consumers validate the gradient/pattern/raster integrations.

## Open Questions

- Should we keep both the lightweight `Color` (float 0–1) and the new svg2pptx
  `Color` (int 0–255 + fluent API), or deprecate the existing model in favour of
  the richer one?
- How do we handle environments where NumPy/colorspacious are unavailable?
  (Option: offer a `--color-lite` policy that disables perceptual operations.)
- Do we expose harmony/accessibility utilities to end users via CLI tooling?
- Should colour decisions trigger telemetry/metrics similar to svg2pptx’s
  gradient analyser?

## Implementation Notes

- Stage 1 landed in svg2ooxml alongside optional dependency guards and bridging
  helpers; consumers can opt in to the new colour engine via
  `pip install -e .[color]`.
- Legacy code paths continue to use the lightweight `Color` dataclass by default
  until later stages rewire gradient and raster pipelines.
- Stage 2 connected gradient and pattern processors to the advanced palette
  statistics, exposing recommended colour spaces through policy metadata.
- Stage 3 introduced perceptual raster normalization with optional linear RGB
  output and richer metadata for downstream consumers.
- Stage 4 ships developer tooling (palette report CLI), documentation for the
  advanced API, and migration notes covering the new colour heuristics.
