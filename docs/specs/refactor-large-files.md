# Refactor Spec: Files Over 1000 Lines

## Motivation

Eleven Python files in `src/svg2ooxml/` currently exceed 1000 lines. They concentrate too many concerns into single classes/modules, making them hard to test in isolation, slow to navigate, and prone to merge conflicts. This spec proposes a targeted split for each file with concrete seams, target module names, and ordering.

| # | File | Lines | Target after split |
|---|---|---:|---:|
| 1 | `core/pptx_exporter.py` | 2823 | ~600 facade + 3 modules |
| 2 | `filters/renderer.py` | 1756 | ~500 + 3 modules |
| 3 | `drawingml/raster_adapter.py` | 1557 | ~600 + 2 modules |
| 4 | `core/ir/text_converter.py` | 1309 | ~500 + 2 modules |
| 5 | `elements/pattern_processor.py` | 1248 | ~500 + 3 modules |
| 6 | `core/styling/style_extractor.py` | 1130 | ~500 + 2 modules |
| 7 | `drawingml/animation/handlers/transform.py` | 1129 | ~500 + 3 sub-handlers |
| 8 | `core/ir/shape_converters.py` | 1122 | ~500 + 2 modules |
| 9 | `drawingml/writer.py` | 1101 | ~600 orchestrator + AssetPipeline |
| 10 | `core/traversal/hooks.py` | 1033 | ~400 + 3 modules |
| 11 | `core/animation/parser.py` | 1032 | ~400 + 3 modules |

## Global Constraints

- **Preserve public API.** Nothing in `src/svg2ooxml/public.py` or symbols listed in `__init__.py` `__all__` may change import paths or signatures. Use re-exports from the original file when splitting.
- **One file per PR.** Each item below ships as a standalone PR with green tests; no cross-file refactors in a single commit.
- **Tests lead.** Before any move, add characterization tests (golden/integration) if coverage on the target file is below 70% line coverage. Run `.venv/bin/python -m pytest --cov=<module>` to check.
- **No behavior changes.** Refactors must be pure moves + renames. Any bugfix or simplification is a separate follow-up PR.
- **PEP 562 lazy loading.** After splitting, run `tools/rebuild_inits.py` so `__init__.py` re-exports stay consistent.
- **Dataclasses stay frozen.** IR and value objects remain `@dataclass(frozen=True, slots=True)`.
- **Use lxml only** (per project memory — never stdlib `xml`).

## Recommended Ordering

Order is picked by blast radius (low → high) so that early PRs build confidence before touching the exporter facade:

1. `core/animation/parser.py` — leaf module, clear seams
2. `drawingml/animation/handlers/transform.py` — single handler, isolated
3. `elements/pattern_processor.py` — self-contained
4. `core/ir/text_converter.py` — single converter
5. `core/styling/style_extractor.py`
6. `core/ir/shape_converters.py`
7. `core/traversal/hooks.py`
8. `filters/renderer.py`
9. `drawingml/raster_adapter.py`
10. `drawingml/writer.py`
11. `core/pptx_exporter.py` — facade, touches everything

---

## 1. `core/pptx_exporter.py` (2823)

**Purpose:** Orchestrates parse → IR → render → package pipeline plus animation sampling and variant expansion.

**Smells:** God-facade. `SvgToPptxExporter` (90–654) mixes pipeline orchestration, state, and result building; 40+ free helpers (655–2751) cover motion sampling, geometry, and serialization. `_coalesce_simple_position_motions` (1544) is a 400-line hub.

**Target split:**
- `core/pptx_exporter.py` — thin `SvgToPptxExporter` facade (~600 lines).
- `core/export/animation_processor.py` — animation serialization helpers (688–834) + motion sampling (1544–1957).
- `core/export/motion_geometry.py` — affine/rotation/projection utilities (2035–2460).
- `core/export/variant_expansion.py` — multipage and variant-expansion helpers.

**Risk:** High — many call sites. Land last. Add integration fixture covering at least one multipage + one animated deck before moving.

---

## 2. `filters/renderer.py` (1756)

**Purpose:** Selects native DrawingML / vector / raster / resvg strategy for SVG filter effects.

**Smells:** `FilterRenderer` mixes strategy selection, payload coercion, and filter application. Fallback chain (140–170) uses deep conditionals. Palette setup duplicated across render methods.

**Target split:**
- `filters/renderer.py` — `FilterRenderer` orchestrator (~500).
- `filters/strategies/native.py` — native DrawingML renderer (112–175).
- `filters/strategies/raster_fallback.py` — skia/placeholder fallback.
- `filters/strategies/resvg_bridge.py` — resvg adapter (~300 lines).
- `filters/palette.py` — EMF palette resolution helpers.

---

## 3. `drawingml/raster_adapter.py` (1557)

**Purpose:** Skia-backed PNG fallback generation for unrenderable filters.

**Smells:** Tight skia coupling; long `render_filter` (72–160); scattered defensive type checks (`_float_or`, `_is_number`, `_coerce_positive`).

**Target split:**
- `drawingml/raster_adapter.py` — `RasterAdapter` orchestration (~600).
- `drawingml/skia_bridge.py` — skia/image ops (1411–1547).
- `drawingml/paint_converter.py` — color/paint conversions (1450–1530).

---

## 4. `core/ir/text_converter.py` (1309)

**Purpose:** SVG `<text>` → IR text frame with font metrics, baseline, anchor.

**Smells:** `_convert_resvg_text` (85–450) does layout + style + baseline + embedding in one pass; hardcoded `FONT_FALLBACKS`.

**Target split:**
- `core/ir/text_converter.py` — `TextConverter` coordinator (~500).
- `core/ir/text/layout.py` — positioning, baseline, anchor.
- `core/ir/text/font_metrics.py` — scaling, size resolution, fallback table.

---

## 5. `elements/pattern_processor.py` (1248)

**Purpose:** Analyze SVG patterns, classify, match PowerPoint presets.

**Smells:** 44-method god class; nested preset dicts; caching interleaved with analysis.

**Target split:**
- `elements/pattern_processor.py` — `PatternProcessor` coordinator (~500).
- `elements/patterns/classifier.py` — complexity/type detection.
- `elements/patterns/preset_matcher.py` — PowerPoint preset mapping.
- `elements/patterns/geometry.py` — geometry/optimization analysis.

---

## 6. `core/styling/style_extractor.py` (1130)

**Purpose:** Extract SVG presentation attributes → IR paint structures.

**Smells:** One extractor covers solid/gradient/pattern/stroke/inheritance; gradient descriptor unpacking duplicated.

**Target split:**
- `core/styling/style_extractor.py` — `StyleExtractor` coordinator (~500).
- `core/styling/paint/gradient.py` — gradient paint resolver.
- `core/styling/paint/pattern.py` — pattern paint resolver (integrates with `pattern_processor`).

---

## 7. `drawingml/animation/handlers/transform.py` (1129)

**Purpose:** Build DrawingML timing XML for SVG transform animations.

**Smells:** Monolithic `build()` dispatch; paced-timing helpers (`compute_paced_key_times_2d`) are generic but live here; matrix utilities (`_resolve_affine_matrix`, `_project_affine_point`) also generic.

**Target split:**
- `drawingml/animation/handlers/transform.py` — `TransformAnimationHandler` dispatch (~400).
- `drawingml/animation/handlers/transform_scale.py` — scale strategy.
- `drawingml/animation/handlers/transform_rotate.py` — rotate strategy.
- `drawingml/animation/handlers/transform_translate.py` — translate/motion strategy.
- `drawingml/animation/timing_utils.py` — paced keyframe + matrix helpers (shared across handlers).

**Note:** Verify golden masters (`tests/golden/animation/`) stay byte-identical. Run with `--update-golden` only if XML reorderings are intentional.

---

## 8. `core/ir/shape_converters.py` (1122)

**Purpose:** Mixin providing per-element conversion (shapes, images, gradients).

**Smells:** Mixin composition (`ShapeResvgMixin` + `ShapeFallbackMixin`) hides the size; vector vs raster strategies interleaved; coordinate transforms duplicated.

**Target split:**
- `core/ir/shape_converters.py` — coordinator (~500).
- `core/ir/shape/resvg_converter.py` — Resvg path generation.
- `core/ir/shape/fallback_converter.py` — raster fallback.
- `core/ir/shape/image_converter.py` — image extraction/embedding.

**Open question:** Replace mixin composition with explicit composition (dependency-injected converters) — decide during PR, document in ADR if accepted.

---

## 9. `drawingml/writer.py` (1101)

**Purpose:** Render IR scene → DrawingML slide XML.

**Smells:** `DrawingMLWriter` couples shape/text/mask/animation/asset pipelines; `render_scene()` initializes 5+ interdependent pipelines.

**Target split:**
- `drawingml/writer.py` — `DrawingMLWriter` thin orchestrator (~600).
- `drawingml/pipelines/asset_pipeline.py` — new: asset registry, media indexing (currently inline).
- Strengthen existing `MaskPipeline` / `AnimationPipeline` boundaries — move stragglers out of `writer.py`.

---

## 10. `core/traversal/hooks.py` (1033)

**Purpose:** Traversal callbacks invoked by IR converter while walking SVG tree.

**Smells:** 30-method mixin covering shape creation, styling, clipping, masking, animation, filter; circular dependency with converter context.

**Target split:**
- `core/traversal/hooks.py` — `TraversalHooksMixin` coordinator (~400).
- `core/traversal/hooks/shape_creation.py`
- `core/traversal/hooks/styling.py`
- `core/traversal/hooks/clipping_masking.py`

---

## 11. `core/animation/parser.py` (1032)

**Purpose:** SMIL parser → animation IR.

**Smells:** 38 methods in `SMILParser`; duplicated numeric parsing (`_combine_numeric_values`, `_parse_numeric_list`, `_parse_motion_path_reference`); long `_parse_animation_element` (158–241).

**Target split:**
- `core/animation/parser.py` — `SMILParser` coordinator (~400).
- `core/animation/timing_parser.py` — timing extraction (687–879).
- `core/animation/transform_parser.py` — transform + motion detection.
- `core/animation/value_parser.py` — numeric + list + motion-path parsing.

---

## Acceptance Criteria

For each PR:

1. Target file is ≤ 700 lines (hard cap: 1000).
2. `pytest -m "unit and not slow"` green.
3. `pytest -m integration` green.
4. `ruff check src tests` and `mypy src` clean.
5. If the file has golden masters, they must be byte-identical (no `--update-golden` flag).
6. Public imports from `svg2ooxml` and `svg2ooxml.public` unchanged — verify via a `tests/unit/test_public_api.py` snapshot.
7. Total LOC delta ≤ +5% (net) — refactors should not grow the code base materially.

## Out of Scope

- Behavior changes, bug fixes, or performance tuning — file separate issues.
- Reworking `ConversionServices` registry wiring — handled under ADR-020 follow-ups.
- Splitting files between 700 and 1000 lines — revisit once the top 11 are done.
