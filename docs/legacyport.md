# Legacy Port Roadmap

## Current status

- IR models (scene/text/shapes/etc.) now live under `src/svg2ooxml/ir/`; the legacy shim has been removed and downstream callers target the modern package directly.
- Text/clip helpers (`core/ir/text_converter.py`, `core/traversal/clip_geometry.py`, `core/traversal/transform_parser.py`) removed the mapper dependency from API services, PPTX exporter, and clip service.
- API/export pipeline uses `svg2ooxml.ir.convert_parser_output` directly; no mapper shims remain in the code path.
- Mapper base classes and the primary element mappers (image/path/text/group) now reside in
  `src/svg2ooxml/core/pipeline/mappers/`, and unit tests import the updated modules directly.
- Navigation helpers live under `src/svg2ooxml/core/pipeline/navigation.py` and
  all runtime/services code imports the modern module directly.
- Render geometry, paint, filter, and mask helpers now live under `src/svg2ooxml/render/`
  with the legacy packages for paint/render removed after callers migrated. The
  new filter/mask placeholders raise ``NotImplementedError`` until the
  pyportresvg port arrives, ensuring callers fail fast.
- Geometry, units, performance, preprocessing, presentation, and clip helpers
  now live under the modern packages; no runtime code remains under
  ``svg2ooxml.legacy``.
- The unused `legacy.compat.heuristics` stub has been removed; any future
  heuristic adjustments should land under `core/compat/` with accompanying docs.

## Next milestones

### 1. Geometry & clip helpers
- ✅ Clip tessellation/bounds helpers live under `common/geometry/clip/`.
- ✅ The legacy clip module has been removed; ensure external integrations
  target the modern helpers.

### 2. UVBTC mapper extraction
- ✅ `svg2ooxml.map.mapper` now forwards directly to `core.pipeline.mappers` and `core.traversal.clip_geometry`, and the legacy mapper package has been removed.
- **Replace** any remaining `svg2ooxml.map` imports in downstream tools with the structured modules.
- **Document** the new mapper surface so external callers understand the supported entry points.

### 3. Pipeline API surface
- **Decide** whether the lightweight `core.pipeline` scaffolding should grow
  into a supported orchestration API or whether callers should continue using
  the higher-level exporters.
- **Document** the outcome so downstream tools rely on the exporter/services
  entry point instead of the removed legacy modules.

## Execution notes
- Work slice by slice; commit after each major chunk (e.g., geometry paths, units conversion) with tests green.
- Keep shims thin and temporary—document every promotion in `docs/porting.md`.
- Legacy modules have been removed; continue capturing downstream follow-ups in
  `docs/porting.md` as new surfaces settle.
