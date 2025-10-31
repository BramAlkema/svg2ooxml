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

1. **Filter planner** – Bring over the pyportresvg filter planner and execution
   pipeline. Populate `render.filters.plan_filter` / `apply_filter` and add unit
   tests mirroring `tests/unit/filters`.
2. **Mask/clip rasterisation** – Port the resvg mask and clip rasterisers into
   `render.mask_clip`. Provide fast-failure guards while the implementation is
   incomplete.
3. **Render surface orchestration** – Flesh out `render.pipeline` and
   `render.surface` to drive resvg-based rendering. Integrate with the DrawingML
   export path behind a feature flag.
4. **Exporter gating** – Ensure API/export services detect missing renderer
   features and surface actionable errors instead of crashing.
5. **Testing** – Expand `tests/unit/render` and add end-to-end validation under
   `tests/integration/core/test_pipeline.py` once the new pipeline is wired in.

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
