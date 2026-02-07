# Porting Checklist – svg2pptx → svg2ooxml

The port is now focused on finishing the resvg-driven renderer and collapsing
what is left of the legacy package tree. This document tracks the current
status and the remaining work so we can finally delete `src/svg2ooxml/legacy`.

## Status Snapshot
- Core traversal, `<use>` expansion, style resolution, and parser utilities now
  live under `src/svg2ooxml/core/` and `src/svg2ooxml/common/`, with legacy
  modules re-exporting the modern implementations.
- The intermediate representation (scene, text, paint, geometry, animation) has
  moved to `src/svg2ooxml/ir/`; the legacy shim has now been removed.
- Masks, clip collection, hyperlinks, navigation, and service wiring run
  through the new core packages; the mapper and pipeline shims have been
  retired in favour of `core.pipeline`.
- DrawingML bridges (paint, EMF helpers) now live in `src/svg2ooxml/drawingml`,
  and the mapper package forwards to the new pipeline modules.
- Filter primitives, registry, and the resvg bridge now live under
  `src/svg2ooxml/filters/`; the legacy shim has been removed.
- Rendering helpers (`geometry`, `normalize`, `paint`) sit in
  `src/svg2ooxml/render/`, and the renderer pipeline (`filters`, `mask_clip`,
  `markers`, `rasterizer`, `surface`) now wrap the ported pyportresvg
  implementation.
- The unused compatibility heuristics stubs have been retired; any future
  cross-version adjustments should live under `core/compat/` with explicit docs.
- Performance metrics now live under `src/svg2ooxml/performance/metrics.py`,
  replacing the legacy redirect.
- Preprocessing and presentation facades expose the parser sanitizers and PPTX
  exporter directly without legacy shims.
- Obsolete top-level packages (`animations`, `batch`, `clip`, `compat`, `fonts`,
  `multipage`, `text`) have been removed along with their legacy counterparts.
- Clip tessellation helpers now live under `src/svg2ooxml/common/geometry/clip/`
  and are shared by the traversal runtime.

## Remaining Work at a Glance

| Area | Current state | Next actions |
| --- | --- | --- |
| Renderer integration | Pipeline and filter execution now run on the ported pyportresvg renderer | Wire the renderer into the exporter surfaces, add end-to-end coverage, and gate feature usage where platform support is still missing (e.g., gradients without fallbacks). |
| PPTX pipeline | `core/pipeline` exposes minimal scaffolding today | Decide whether to flesh out the modern pipeline API or steer callers to the higher-level exporter and document the supported surface. |
| Legacy package sweep | Legacy modules removed | Track downstream consumers in docs and trim outstanding references. |
| Documentation | Docs mention shims without pointing at the modern modules | Update references (this file, `docs/legacyport.md`, `docs/structure.md`) whenever a shim is removed or a new surface is stabilised. |

## Legacy Package Cleanup

All compatibility shims have been removed. The modern packages (`geometry`,
`units`, `performance`, `preprocessing`, `presentation`, etc.) surface the real
implementations, and the `legacy/` namespace no longer exists. Treat any
backfill work as first-class modules under `src/svg2ooxml/`.

## Resvg Integration Plan

1. **Filter planner** – ✅ Ported and exercised via `render.filters` with
   lighting/turbulence support and service integration.
2. **Mask/clip rasterisation** – ✅ Ported into `render.mask_clip` and wired
   through traversal and services.
3. **Render surface orchestration** – ✅ The resvg render pipeline owns shape /
   filter / mask processing.
4. **Exporter gating** – 🚧 In progress (see “Exporter & Policy Gating Plan”).
5. **Testing** – 🚧 End-to-end harness still needs a resvg-only integration
   suite and refreshed visual baselines.

## Shim Retirement Playbook
Use this checklist whenever a legacy package graduates to the modern tree:
1. Promote the code and add unit tests that mirror the new module path.
2. Replace legacy imports in production code and tests.
3. Update docs (`porting.md`, `legacyport.md`, `structure.md`) to reflect the
   new location.
4. Remove the shim, run targeted tests (unit + relevant integration/visual
   suites), and update documentation.

## Verification
- Default dev loop: `pytest tests/unit -m "unit and not slow"`
- Geometry/mask/map sweep: `pytest tests/unit/map`
- Renderer placeholders: `pytest tests/unit/render`
- End-to-end (once pipeline test exists): `pytest tests/integration/core/test_pipeline.py`

Keep coverage ≥70 % across `src/svg2ooxml`, document any skipped functionality,
and capture follow-up bugs in `docs/legacyport.md` or the tracker.

## Exporter & Policy Gating Plan

| Step | What | Owner / Notes |
| --- | --- | --- |
| 1 | Expose a `filter_strategy` toggle on `SvgToPptxExporter` (completed) | parser and exporter now pass the strategy to `configure_services`. |
| 2 | Shape the policy surface | extend `policy.rules` so filter policies can force `legacy`, `resvg`, or `resvg-only` modes per document. |
| 3 | Trace gating decisions | update `FilterService` and exporters so `ConversionTracer` logs `resvg_attempt`, `resvg_success`, and any fallbacks when strategy overrides apply. |
| 4 | Feature compatibility checks | layer policy-guard rails (e.g., disable resvg when lighting/turbulence unsupported) and surface explicit errors through the exporter. |

## End-to-End & Visual Validation Plan

1. **Dedicated resvg pipeline tests** – add `tests/integration/core/test_pipeline.py`
   that spins the render pipeline directly (no PPTX export) using small SVGs
   covering filters, masks, and clips. Gate it behind the resvg strategy so we
   can run it in CI.
2. **Visual baselines** – regenerate `tests/visual/golden/` assets with the
   resvg renderer enabled (`SVG2OOXML_VISUAL_FILTER_STRATEGY=resvg` when running
   `tools/visual/update_baselines.py`). Capture before/after notes for
   filters/masks and land the updated PNGs alongside a short changelog in
   `tools/visual/update_baselines.md`.
3. **Docs & toggles** – add a short guide (`docs/resvg.md`) outlining when to
   choose the resvg path, how to enable it via policy/exporter flags, and known
   gaps (e.g., performance costs, primitives still rasterised).
