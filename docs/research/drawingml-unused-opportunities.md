# Unused DrawingML Opportunities (Gap-Oriented)

Date: 2026-02-23

Goal: identify DrawingML features we are not fully using today that are likely
better fits for current fidelity gaps than additional fallback layering.

Context: `Figma -> SVG -> OOXML (PPTX) -> Google Slides import`.

## Implementation Status (2026-02-23)

Implemented (policy-gated, default off):
- `effectDag` container support for composite/mask paths (`enable_effect_dag`).
- Effect container preservation (`effectLst` + `effectDag`) in filter merge/render paths.
- Blip fallback enrichment framework (`enable_blip_effect_enrichment`) with strict allowlist transforms.
- Native color-transform candidate extraction for fallback blip enrichment
  (`enable_native_color_transforms`) for:
  - `feColorMatrix(saturate)` -> `satMod`
  - `feColorMatrix(hueRotate)` -> `hueOff`
  - `feComponentTransfer` simple alpha linear -> `alphaModFix`

Implemented (mainline, default on):
- Richer marker mapping for native `headEnd`/`tailEnd` type/size inference from marker IDs.
- Marker-geometry profiling in traversal metadata (`marker_profiles`) so
  DrawingML marker types can be selected deterministically from marker shapes.
- Pattern tile transform mapping for simple scale/translate/mirror matrices into
  `a:tile` (`sx`, `sy`, `tx`, `ty`, `flip`).
- Visual fixture added for transformed pattern tiles:
  `tests/visual/fixtures/resvg/pattern_tile_transforms.svg`.

Still open:
- Broader `feColorMatrix`/`feComponentTransfer` native mappings beyond current allowlist.
- Compatibility qualification matrix (PowerPoint + Google Slides) for default-on decisions.
- Visual corpus delta reporting and staged rollout thresholds.

## High-Impact Opportunities

### 1) Use `a:effectDag` for composite/mask graphs

Why it matters:
- Current filter composite path builds `alphaMod`/`alphaModFix` structures for
  masking/compositing, but our effect merge path is `effectLst`-only.
- `effectLst` normalization explicitly keeps only the `CT_EffectList` set and
  drops non-list children like `alphaMod*`.

Current code reality:
- Composite builds alpha operators under `effectLst`:
  `src/svg2ooxml/filters/primitives/composite.py:457`
- Effect merge allows only: `blur`, `fillOverlay`, `glow`, `innerShdw`,
  `outerShdw`, `prstShdw`, `reflection`, `softEdge`:
  `src/svg2ooxml/drawingml/shapes_runtime.py:661`
- Non-list effect children are intentionally ignored:
  `src/svg2ooxml/drawingml/shapes_runtime.py:688`

Better DrawingML fit:
- Use `a:effectDag` for non-`effectLst` effect graphs (alpha ops, nested
  containers), keep `effectLst` for simple standalone effects.

Expected gain:
- Closes a major part of the current composite/mask "generated but dropped"
  behavior without forcing raster/EMF.

Risk:
- Viewer compatibility variance (especially in Google Slides import) must be
  validated with targeted fixtures.

Status:
- Implemented behind policy flag (`enable_effect_dag`), default off (PPT-first).

---

### 2) Use color transform primitives in correct contexts

Why it matters:
- We currently treat many color/filter transforms as unavailable because they
  are not valid under `effectLst`.
- Several useful transforms are valid on color nodes or in effect containers.

Current code reality:
- `feColorMatrix` comments note missing `effectLst` equivalents for
  `satMod`/`hue`/`luminanceToAlpha`:
  `src/svg2ooxml/filters/primitives/color_matrix.py:130`

Better DrawingML fit:
- Apply color transforms where they are valid:
  - On color elements (`srgbClr`/`schemeClr`): `alphaMod`, `hueOff`, etc.
  - In `effectDag`/`cont` or `blip` chains where supported.

Expected gain:
- Native handling for a larger subset of `feColorMatrix` /
  `feComponentTransfer` cases (especially solid-fill or simple image paths).

Risk:
- Requires splitting current filter emit logic by allowed parent context.

Status:
- Partially implemented for blip-context candidates only, behind
  `enable_native_color_transforms` + enrichment path.

---

### 3) Use blip-level effects for raster fallback assets

Why it matters:
- Raster fallback images are currently embedded with minimal post-processing
  semantics; we lose an opportunity to keep some filter logic in OOXML.

Current code reality:
- Filter fallback frequently emits `blipFill` placeholders/comments:
  `src/svg2ooxml/drawingml/filter_renderer.py:257`
- Picture template accepts this path:
  `assets/pptx_templates/picture_shape.xml`

Better DrawingML fit:
- On `<a:blip>`, emit supported image effects (`duotone`, `clrChange`,
  `alphaMod*`, etc.) for compatible filter subsets.

Expected gain:
- Better fidelity than plain fallback bitmap while staying in first-class
  DrawingML image semantics.

Risk:
- Need strict allowlist and compatibility tests per effect type.

Status:
- Implemented behind `enable_blip_effect_enrichment` with allowlisted tags.

---

### 4) Use `xfrm` rotation/flip and proper group transform boxes

Why it matters:
- We bake many transforms into geometry, which reduces editability and can
  inflate path complexity.

Current code reality:
- Path geometry writer emits move/line/cubic commands, no transform attrs:
  `src/svg2ooxml/drawingml/generator.py:95`
- Group mapper emits `p:grpSp` without full `a:xfrm` group box controls:
  `src/svg2ooxml/core/pipeline/mappers/group_mapper.py:47`

Better DrawingML fit:
- For compatible cases, emit `a:xfrm` (`rot`, `flipH`, `flipV`) on shapes.
- For grouped transforms, emit `chOff`/`chExt` along with group extents where
  grouping is preserved.

Expected gain:
- More editable output and fewer "baked path" conversions.

Risk:
- Transform behavior differs by host app and object type; requires fixture
  verification.

---

### 5) Expand custom geometry commands beyond cubic-only

Why it matters:
- Current custom geometry path conversion only emits `moveTo`, `lnTo`,
  `cubicBezTo`, `close`.

Current code reality:
- Supported command set is fixed:
  `src/svg2ooxml/drawingml/generator.py:95`

Better DrawingML fit:
- Add support for `arcTo` and `quadBezTo` when source geometry matches these
  forms.

Expected gain:
- Better arc fidelity and potentially smaller/more natural geometry for SVG arc
  heavy content.

Risk:
- Requires robust arc parameter conversion and good round-trip tests.

## Medium-Impact Opportunities

### 6) Richer marker native mapping via `headEnd`/`tailEnd` variants

Current code reality:
- Native line-end helper maps to one fixed triangle style:
  `src/svg2ooxml/drawingml/markers.py:28`

Opportunity:
- Map more simple marker archetypes to native arrowhead types/sizes before
  expanding to separate geometry.

Expected gain:
- Higher editability and smaller XML for common arrowheads.

Status:
- Implemented on mainline.

---

### 7) Fully use `blipFill` tile attributes for pattern transforms

Current code reality:
- Tile path uses fixed values (`tx=0`, `ty=0`, `sx=100000`, `sy=100000`,
  `flip=none`):
  `src/svg2ooxml/drawingml/paint_runtime.py:359`

Opportunity:
- Map pattern scale/offset/mirror into `a:tile` attributes where possible.

Expected gain:
- Better native pattern behavior for transformed/offset tiles without extra
  rasterization.

Status:
- Implemented for axis-aligned transforms (scale/translate/mirror); complex
  rotate/skew transforms intentionally fall back to safe defaults.

## Lower-ROI Opportunities (for now)

- `scene3d` / `sp3d` as approximations for lighting filters:
  likely complex and not reliable for SVG parity.
- Reflection/preset shadow enrichment:
  available infrastructure exists, but less direct impact on current top gaps.

## Recommended Execution Order

1. Expand color-transform allowlist and context mappings.
2. Build compatibility matrix (PowerPoint + Google Slides) for current flags.
3. Define rollout gates and switch defaults when acceptance thresholds pass.
4. Transform preservation (`xfrm`/group box) for editability.
5. Arc/quad geometry command expansion.

## Minimal Validation Plan Per Opportunity

For each feature:
- Add one SVG unit fixture and one PPTX golden XML assertion.
- Add one Google Slides import screenshot diff fixture.
- Record fallback percentage deltas before/after on the same corpus.

## External Spec Anchors (for implementation)

- EffectDag class and child model:
  https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.effectdag?view=openxml-3.0.1
- EffectList class (limited child set):
  https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.effectlist?view=openxml-3.0.1
- Blip class (supports image effects like `duotone`, `clrChange`,
  `alphaMod*`, `fillOverlay`):
  https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.blip?view=openxml-3.0.1
- Transform2D (`xfrm`) attributes (`rot`, `flipH`, `flipV`):
  https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.transform2d?view=openxml-3.0.1
- ArcTo and QuadraticBezierCurveTo availability:
  https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.arcto?view=openxml-3.0.1
  https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.quadraticbeziercurveto?view=openxml-3.0.1
