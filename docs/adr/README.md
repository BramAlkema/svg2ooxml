# Architecture Decision Records

This document consolidates converter-side architectural decisions for
svg2ooxml. Individual ADR files have been archived — this is the single source
of truth for the converter repo.

Empirical PowerPoint research, oracle-corpus ownership, and PPTX lab tooling
decisions now live in the sibling `openxml-audit` repo. This repo owns SVG
parse -> IR -> DrawingML/PresentationML emission -> PPTX packaging decisions.

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

Start with `docs/internals/animation-documentation-map.md` for the current
split between converter specs, execution ledgers, emitted SSOTs, and
research-owned material in `openxml-audit`.

This section records durable animation decisions only. Program framing,
acceptance criteria, and cleanup mechanics live in the specs.

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

### Four-Layer Animation Fallback Architecture (ADR-031)

Animations that PowerPoint cannot express with one stable native primitive use
an ordered fallback ladder:

1. preset-backed native slots for stable authored families
2. a compound slot for stacking behaviour fragments in one executable group
3. flipbook playback for dead-path or sampled cases
4. Morph transitions for sole-animation geometry interpolation

Durable invariants:

- PowerPoint executes the `childTnLst` behaviour children directly, so preset
  metadata is a UI concern, not the runtime contract.
- Fallback choice is ordered by editability and structural stability:
  oracle-native -> compound -> flipbook -> morph.

The mapping taxonomy, evidence model, and current coverage live in:

- `docs/specs/svg-animation-native-mapping-spec.md`
- `docs/specs/animation-cleanup-rigour-spec.md`
- `docs/internals/animation-documentation-map.md`

### Large-File Refactor (ADR-032, completed)

All 11 Python files over 1000 lines split into sub-modules per
`docs/specs/refactor-large-files.md`. Pure moves, no behaviour changes.
One file per commit, 2412 tests green throughout.

| File | Before | After |
| --- | ---: | ---: |
| `core/pptx_exporter.py` | 2823 | 662 |
| `filters/renderer.py` | 1756 | 622 |
| `drawingml/raster_adapter.py` | 1557 | 1058 |
| `core/ir/text_converter.py` | 1309 | 778 |
| `elements/pattern_processor.py` | 1248 | 655 |
| `drawingml/animation/handlers/transform.py` | 1146 | 796 |
| `core/styling/style_extractor.py` | 1130 | 453 |
| `core/ir/shape_converters.py` | 1122 | 530 |
| `drawingml/writer.py` | 1101 | 738 |
| `core/traversal/hooks.py` | 1033 | 342 |
| `core/animation/parser.py` | 1032 | 612 |

Shared infrastructure extracted to base classes (`_simple_oracle_gate`,
`_build_discrete_set_sequence` in `AnimationHandler`). New sub-packages:
`core/export/`, `core/ir/text/`, `core/ir/shape/`, `core/styling/paint/`,
`elements/patterns/`, `filters/strategies/`, `drawingml/pipelines/`.

### Research / Converter Boundary (ADR-033)

The April 2026 animation push produced two different kinds of system:

1. converter logic that decides what XML to emit
2. empirical tooling that discovers which PowerPoint-authored XML shapes
   actually load, roundtrip, and play

Keeping both in one repo made the ownership blurry. Scratch decks, capture
artifacts, extractor scripts, and oracle notes started to look like product
assets even when they were really research evidence.

Decision:

- `svg2ooxml` owns conversion behavior: SMIL semantics, fallback policy,
  `NativeFragment`/template composition, handler gates, emitted asset SSOT,
  packaging, and release criteria.
- `openxml-audit` owns empirical PPTX infrastructure: oracle corpus,
  extraction/snapshot/diff lab tooling, timing probe decks, and research ADRs.
- `svg2ooxml` may keep thin compatibility bridges for developer ergonomics, but
  the canonical implementation and durable research docs live in
  `openxml-audit`.
- Converter-side claims that depend on PowerPoint behavior should point to
  evidence in `openxml-audit/docs/pptx_oracle/` or the `openxml-audit` ADRs,
  not to scratch decks or ad hoc notes.

Consequences:

- large temporary decks, captures, and render artifacts do not belong in the
  converter repo
- the converter keeps emitted-side SSOTs such as
  `src/svg2ooxml/assets/animation_oracle/`, because they are part of runtime
  behavior, not empirical corpus ownership
- research can evolve independently without forcing the converter repo to carry
  every probe artifact and lab concern
- when a new empirical finding matters to emission, it lands in
  `openxml-audit` first and is then consumed here as evidence-backed policy or
  template work

### App / Converter Boundary (ADR-034)

The same repository currently contains `figma2gslides`, a tool built on top of
the converter. It may ship from the same repository, but its public contract is
different from the core `svg2ooxml` conversion library.

Decision:

- `svg2ooxml` owns converter code, converter docs, and the converter-facing
  `svg2ooxml` CLI
- `figma2gslides` owns the higher-level tool surface that consumes the
  converter: app runtime, auth, hosting, plugin assets, legal pages, and
  app-local operational tooling
- app-owned materials live under `src/figma2gslides/` and
  `apps/figma2gslides/`
- root `cli/` remains converter-facing unless an entrypoint is deliberately
  declared as a tool built on the converter
- shipping `figma2gslides` in the same distribution must be deliberate,
  documented, and tested as a top-level tool, not accidental package bleed from
  broad discovery settings

Consequences:

- new Google auth, Firebase, hosting, or plugin UX work should land in the app
  surface, while shared conversion fixes stay in `svg2ooxml`
- converter docs may link to the app/tool surface, but should not absorb app
  operational detail unless it affects converter behavior
- package contents and public imports must make the library/tool distinction
  explicit

### Next Hardening Targets (ADR-035)

Status: accepted for the post-0.7.3 cleanup stream.

Context:

The April 2026 review passes were productive because they focused on complete
end-to-end seams instead of isolated files. They found real defects in URL
handling, relationship IDs, package paths, raw DrawingML fragment ingestion,
font/image loading, unit conversion drift, and oversized modules. The next
passes should keep that seam-based approach, but they need an explicit order so
we do not keep chasing whichever large file is most visible.

Decision:

Prioritize targets by public blast radius first, then data-boundary risk, then
visual-fidelity impact, then maintainability drag.

Target order:

1. **Published package and public surface boundary**

   Why: ADR-034 says `figma2gslides` is a tool on top of the converter, not the
   core converter API. The `0.7.3` local build copied it into the wheel through
   broad package discovery, but the repo does not yet test or document that
   surface clearly. That is a public contract bug: users should know which
   imports and entrypoints are supported converter API, which are supported
   higher-level tool API, and which are private internals.

   Scope:

   - `pyproject.toml` package discovery
   - `src/svg2ooxml/__init__.py`, `src/svg2ooxml/public.py`
   - root `cli/` entrypoints
   - wheel-content tests for both converter library and top-level tool contents
   - docs that describe the supported package and tool surfaces

   Exit criteria:

   - wheel contents are intentional and tested, including whether
     `figma2gslides` ships in the same distribution or a separate one
   - public import tests define the supported converter API and supported
     tool API separately
   - release notes and README do not blur tool internals into converter API

2. **Central trust-boundary registry**

   Why: the recent fixes added safe relationship IDs, safe package paths,
   safe URL handling, and safe XML-fragment ingestion, but the rules still live
   near the call sites. Boundary behavior should be obvious, shared, and tested
   as a system.

   Scope:

   - URL and file-reference policy for SVG, image, font, and CSS resources
   - package path and relationship-ID generation
   - XML parser options and raw-fragment admission
   - size/decompression limits for embedded image/font/filter data
   - test fixtures for malicious and malformed inputs

   Exit criteria:

   - every external input crosses one named boundary helper before use
   - no production code calls an unsafe XML parser directly
   - no package writer accepts raw relationship IDs or package paths without
     normalization
   - malicious fixture tests cover SVG, font, image, PPTX packaging, and
     DrawingML fragment paths

3. **Style, cascade, and unit context**

   Why: many visual bugs look like rendering bugs but originate earlier in
   style resolution or unit context. This area is also where ad-hoc conversion
   logic tends to reappear after centralization.

   Scope:

   - `common/style/resolver.py`
   - parser style context and CSS inheritance
   - `core/resvg/usvg_tree.py`
   - `core/resvg/gradient_resolution.py`
   - `common/gradient_units.py`
   - conversion-context propagation into gradients, patterns, text, and filters

   Exit criteria:

   - one context object carries viewport, DPI, inherited style, and conversion
     units through parse -> IR -> render
   - tests cover `em`, `%`, nested SVG viewport, inherited paint, `currentColor`,
     and gradient/filter coordinate spaces
   - duplicate unit/color parsing paths are removed; do not reintroduce render
     package tree or paint parsers

4. **Filter, mask, raster, and EMF fallback seam**

   Why: filters and masks are where native DrawingML, raster assets, EMF
   fallbacks, bounds inflation, relationships, and alpha compositing meet. That
   seam has high visual impact and high packaging risk.

   Scope:

   - `filters/`, especially primitive composition and fallback metadata
   - `drawingml/filter_renderer.py`
   - `drawingml/mask_writer.py`
   - `drawingml/raster_adapter.py`
   - `drawingml/emf_adapter.py`
   - asset registration in `drawingml/pipelines/asset_pipeline.py`

   Exit criteria:

   - every fallback asset has a deterministic owner, bounds, content type, and
     relationship ID before DrawingML emission
   - mask/filter bounds are tested against SVG filter-region semantics
   - raster and EMF output have shared validation hooks
   - PowerPoint package validation is part of focused regression tests

5. **Animation fallback policy after bee-class regressions**

   Why: the bee work proved that group animation fidelity needs conservative,
   evidence-backed policy rather than optimistic synthesis. We should keep
   improving animation, but only after the package and trust boundaries are
   stable.

   Scope:

   - mixed animated groups
   - transform-origin and hinge/pivot semantics
   - compound transforms and sampled center motion
   - generated fallback labels and metadata
   - openxml-audit capture evidence

   Exit criteria:

   - unsupported parent/child animation combinations degrade explicitly
   - transform-origin behavior is covered by focused visual or oracle tests
   - animation fallback metadata says what was preserved and what was dropped
   - empirical claims point to openxml-audit evidence

6. **Test-suite maintainability**

   Why: several test files are now much larger than the production files they
   cover. Large tests slow review and hide duplicated fixtures, even when the
   production code is under the line cap.

   Scope:

   - `tests/unit/map/test_ir_converter.py`
   - `tests/unit/core/test_pptx_exporter_animation.py`
   - `tests/unit/drawingml/test_writer.py`
   - shared fixture builders for scenes, SVG snippets, PPTX packages, and
     filter assets

   Exit criteria:

   - large test files split by behavior area
   - fixtures live near the domain they serve
   - failure output stays local to one behavior seam
   - maintainability checks include production files first, test files second

Non-targets for this stream:

- Do not start a broad NumPy conversion pass until style/unit context is
  stable. NumPy should accelerate known-good math, not conceal unclear units.
- Do not expand PowerPoint research assets in this repo; empirical capture and
  oracle corpus work belongs in `openxml-audit` per ADR-033.
- Do not pursue new feature surface before public converter/tool package
  boundaries are enforceable.

Consequences:

- The next commit should likely address package discovery/public surface before
  deeper renderer work.
- Security and package-boundary bugs outrank visual-fidelity bugs when both are
  available.
- Large-file splitting remains useful, but only when it follows a behavior seam
  and comes with targeted tests.
- Each pass should leave behind a small regression suite for the seam it
  hardened, not only ad hoc bug tests.

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

### Comprehensive OpenType Feature Support (ADR-030, proposed)

**Context.** svg2ooxml's stated goal is a comprehensive SVG→PPTX converter,
not an 80/20 tool. CSS (and therefore SVG 2 text) carries substantial
typography signals through `font-variant-caps`, `font-variant-numeric`,
`font-variant-ligatures`, `font-variant-position`, `font-variant-alternates`,
and the `font-feature-settings` escape hatch. PowerPoint's DrawingML text
schema exposes a few of these directly as run properties — `cap="small|all"`,
`baseline=` for sub/sup, `lang=` for locale-specific features, and GPOS
kerning survives automatically inside the EOT-wrapped font — but has no
runtime selector for the rest. For unmapped features, the rasteriser renders
whatever the font's default `cmap` points at, and dropping them silently is
a fidelity loss that compounds across editorial, data viz, and hand-authored
SVG inputs.

**Prior art in this repo.**

- `docs/reference/research/svg-to-drawingml-feature-map.md:320` — `font-variant:
  small-caps` is already implemented natively via `cap="small"` on
  `<a:rPr>`, validated against the .NET SDK. Small caps and all-small-caps
  are **not** candidates for baking because the native path is better:
  PowerPoint handles the cap synthesis itself with correct metrics.
- `docs/reference/research/svg-to-drawingml-feature-map.md:338–339` — `baseline-shift:
  super` / `baseline-shift: sub` already emit the `baseline` attribute on
  `<a:rPr>`, so `font-variant-position: sub|super` will share that path and
  also **not** need baking.
- `docs/reference/research/svg-to-drawingml-feature-map.md:363` — `xml:lang` / `lang`
  already flows to `<a:rPr lang="…"/>`, which triggers PowerPoint's
  locale-specific OT features (localised forms, required ligatures) at
  render time.
- `services/fonts/embedding.py:419–598` — `_select_ligature_glyphs` and
  `_glyph_ligature_sequences` already walk FontForge `getPosSub("*")`
  entries and keep `ligature`-kind glyphs through subsetting. This is
  subset-correctness, not baking: ligatures already reachable via the
  font's default `cmap` survive and render natively, so `liga` (common
  ligatures, enabled by default in most fonts) is **not** a baking target
  either.
- `docs/specs/FONT_EMBEDDING_ANALYSIS.md` +
  `FONT_INJECTION_QUICK_REFERENCE.md` + `FONT_DATA_FLOW_VISUAL.txt` — a
  2025-11-03 exploration pass mapping the entire font-embedding data flow
  across five injection points (WebFontProvider → TextPipeline →
  EmbeddingEngine → DrawingMLWriter → PPTXPackageBuilder). Any work
  touching the embedding pipeline should read these first. Notably flags a
  "metadata flow gap" at `text_pipeline.py:233–248` where `FontMatch`
  metadata is not explicitly merged into `FontEmbeddingRequest` metadata.
- `docs/internals/pipeline-analysis.md:364–368` — Known-gap list
  explicitly calls out `font-feature-settings` and `font-variation-settings`
  as unsupported. The adjacent bullet claiming `font-variant` is "stored but
  not applied" is **stale**: the feature map confirms small-caps is applied.
  Correcting that bullet is a docs-drift follow-up, out of scope for this
  ADR.
- `docs/internals/webfont-provider.md:491–492` — `font-feature-settings`
  and `font-variation-settings` listed under "Future", confirming the gap
  this ADR addresses.

**Decision.** Support the unmapped OT features by **baking** them into
synthetic embedded font variants at conversion time, rather than waiting
for a DrawingML schema change that is not coming. For each unique
`(family, sorted(feature_tags))` combination reached during IR conversion,
produce a baked font whose `cmap` and `glyf` tables reflect the
substitutions the requested GSUB features would have performed, save it
under a deterministic synthetic family name, embed it as a separate EOT
part in the PPTX, and rewrite the affected DrawingML text runs to reference
the synthetic name via `<a:latin typeface="…"/>`.

**Scope — in.** GSUB-driven features with no native DrawingML path:
figure styles (`onum`/`lnum`/`tnum`/`pnum`), fractions (`frac`/`afrc`),
ordinals (`ordn`), slashed zero (`zero`), discretionary ligatures (`dlig`),
historical ligatures (`hlig`), contextual alternates (`calt`), stylistic
alternates (`salt`), stylistic sets (`ss01`–`ss20`), character variants
(`cv01`–`cv99`), titling caps (`titl`), unicase (`unic`), and the raw
`font-feature-settings` escape hatch for anything else a user writes
explicitly. The high-value real-world subset is figure styles (data viz
needs `tnum`, editorial typography wants `onum`), fractions, and stylistic
sets; everything else is long tail but cheap once the pipeline exists.

**Scope — out.** `font-variant-caps` (all values): native via `cap="none|
small|all"`, existing code path, do not touch. `font-variant-position: sub|
super`: native via `baseline=`, existing code path. Default-on ligatures
(`liga`, `rlig`, `clig`): render via the source font's `cmap` plus existing
subset-time preservation in `_select_ligature_glyphs`. Kerning (`kern` /
GPOS): survives inside the EOT-wrapped font and PowerPoint honours it at
render time. Locale-dependent features: triggered by `lang=` on `<a:rPr>`.
`font-variation-settings` and variable fonts generally: a separate code
path via `fontTools.varLib.instancer` producing static instances at the
requested axis values — handled in a future ADR, not this one.

**Preconditions.** The OTF (CFF) → TTF (`glyf`) converter at
`services/fonts/otf2ttf.py` is a hard prerequisite because baking operates on
`glyf` outlines, and any CFF-flavoured source font must be rebuilt in TT form
before the bake step. That converter landed in the same session as this ADR
and is already wired into the embedding engine.

**Implementation order.**

1. Port `glyph_baking.py` from tokenmoulds under
   `services/fonts/glyph_baking.py`: runs GSUB substitutions in-process via
   `fontTools.subset` / manual `cmap` rewriting, preserves horizontal metrics
   and line metrics so layout does not shift, returns baked bytes.
2. Introduce a `BakedFontRegistry` keyed on `(family, frozenset(feature_tags))`
   with memoisation so each unique combination is baked at most once per
   conversion. Deterministic synthetic naming: `"<family> [<tag>,<tag>]"` with
   tags sorted, truncated and hash-suffixed if the PPTX font-name length
   budget is exceeded.
3. Extend `core/styling/style_extractor.py` to parse only the
   `font-variant-*` properties whose feature tags are in the baking scope
   (numeric, ligatures excluding `liga`, alternates, East Asian), plus the
   raw `font-feature-settings` escape hatch. `font-variant-caps`,
   `font-variant-position`, and the default-on ligature classes continue
   to flow through their existing native DrawingML paths and must **not**
   be routed into the baking registry. Normalise each text run to a
   canonical sorted tuple of OT feature tags so identical requests
   collapse on lookup.
4. Thread the registry through `core/ir/text_converter.py` and
   `drawingml/writer.py`: text runs gain a resolved `typeface` property that
   may differ from the source `font-family` when a baked variant is needed,
   and the DrawingML text renderer emits `<a:latin typeface="…"/>`
   accordingly.
5. Extend `FontEmbeddingEngine` so baked variants flow through the same EOT
   packaging path as regular embedded fonts, each with their own relationship
   and content-type entry.
6. Specimen corpus under `tests/corpus/font_variants/` with one SVG per
   feature value. Each test asserts that the generated PPTX contains the
   expected baked family, that the expected text run references it, and that
   the OpenXML audit still passes.

**Trade-offs.** PPTX size grows roughly linearly with the number of distinct
feature combinations used in the input SVG — the common case is one or two
baked variants per family. Baking adds fontTools work at conversion time,
but the registry makes it O(unique combinations) rather than O(text runs).
Synthetic family names are visible to PowerPoint users if they click into
the font picker, which is ugly but acceptable for fidelity wins.

**Interaction with the large-file refactor.** `style_extractor.py` (1130 LOC)
and `text_converter.py` (1309 LOC) are both on the split list in
`docs/specs/refactor-large-files.md`. Font-variant parsing should land on top
of the split, not underneath it: either wait for those PRs, or extract the
font-variant parsing into a new self-contained module under
`core/styling/paint/` that the refactor can integrate without rewriting.

**Open questions.**

- Cap on baked variants per family before we warn and degrade to the
  unbaked default? Proposal: soft limit of 8, logged at INFO level.
- Behaviour when the source font lacks a requested GSUB feature (e.g.
  `small-caps` on a font with no `smcp` lookup)? Proposal: log at DEBUG,
  fall through to the default cmap, do not synthesise small caps from
  scaled capitals.
- Should `font-variant-alternates: styleset(3)` produce a baked variant per
  invoked `ssNN` tag, or group them? Proposal: group, because real-world
  usage combines stylistic sets with other features.
- How to surface baking failures (corrupt source font, unsupported feature)
  without aborting the whole conversion? Proposal: per-run fallback plus a
  diagnostic in the asset registry, following the pattern already used for
  filter and mask fallbacks.

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

### PresentationML-First PowerPoint Oracle Strategy (ADR-029)
The product target is PresentationML, not a version-matrix of PowerPoint
behaviors. Primary correctness comes from spec-valid, semantically coherent
PresentationML plus validator coverage (`openxml-audit` and repo semantic
checks). PowerPoint remains an important runtime and oracle, but only for
high-risk constructs where ECMA and Microsoft docs do not fully determine
working emitted structures in practice: triggers, `interactiveSeq`, build-list
coupling, pane-sensitive effect wrappers, and other obscure animation cases.

For those cases, the durable research source of truth is XML-first:

1. saved PowerPoint-authored raw slide XML
2. extracted raw `p:timing` / `p:bldLst`
3. normalized XML and signatures for mining
4. human notes

Working `.pptx` decks are temporary authoring inputs, not the long-term oracle.
Compatibility policy stays intentionally small:

- keep one latest-PowerPoint smoke lane for slideshow/open/roundtrip checks
- avoid per-version support matrices unless a concrete regression demands it
- collapse proven oracle findings into emitter templates and validator rules

This keeps the architecture centered on `svg -> PresentationML` while still
using PowerPoint where it is the only practical oracle for emitted animation
structures.

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
