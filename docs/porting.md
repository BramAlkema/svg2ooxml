# Porting Checklist

The svg2ooxml codebase is mid-migration from svg2pptx. Packages that have not
yet been fully ported live under `src/svg2ooxml/legacy/` and are exposed through
compatibility shims so existing imports continue to function. This document
tracks what remains to move and the decisions we still owe.

## Recently Completed
- Introduced `legacy/` to house svg2pptx-era packages while we carve out the
  new `core/`, `drawingml/`, `policy/`, `io/`, and `common/` modules.
- Deleted stale `*.bak` re-export files; the new structure relies on explicit
  packages instead of auto-generated namespace lists.
- Added README guidance (installation, testing, structure) for contributors.
- Migrated the CSS style resolver to `src/svg2ooxml/common/style/`, the `<use>`
  expansion helpers plus traversal mixins to `src/svg2ooxml/core/styling/` and
  `src/svg2ooxml/core/traversal/`, and the DOM/normalisation/statistics utilities
  to `src/svg2ooxml/core/parser/`, keeping legacy shims for callers during the
  rollout.
- Migrated the conversion tracer into `src/svg2ooxml/core/tracing/`, leaving
  `svg2ooxml.map.tracer` as a compatibility shim while downstream imports move.
- Promoted the mask processor and resvg clip/mask collectors into
  `src/svg2ooxml/core/masks/` and `src/svg2ooxml/core/traversal/bridges/`,
  keeping legacy shims while services and tests switch to the new modules.
- Moved hyperlink processing into `src/svg2ooxml/core/hyperlinks/` with the
  service provider and CLI now relying on the new module, leaving the legacy
  shim for compatibility.
- Promoted the resvg paint bridge and EMF path adapters into
  `src/svg2ooxml/drawingml/bridges/`, keeping legacy re-exports for callers
  still pointing at `legacy.map`.
- Moved the policy hooks mixin into `src/svg2ooxml/core/ir/policy_hooks.py`
  while leaving a legacy shim to ease the remaining mapper cleanup.
- Promoted rectangle conversion, marker definitions/runtime, smart-font
  bridging, shape conversion mixins, DOM traversal helpers, and geometry
  fallbacks into the `core/ir` and `core/traversal` namespaces with legacy
  shims pointing at the new surfaces.

## High‑Priority Migrations

These are the “hot paths” still sitting in `legacy/` that block fidelity fixes
and new features. Each entry calls out where the code should land, the work
required, and the validation we expect before removing the shim.

| Legacy module                                     | Target package / module                           | Migration outline |
|--------------------------------------------------|---------------------------------------------------|-------------------|
| `legacy/css/resolver.py` + style helpers (used by IR converter, `<use>` expansion, text pipeline) | `src/svg2ooxml/common/style/resolver.py` | - ✅ Resolver now lives in `common/style/resolver.py`; legacy module re-exports for backward compatibility.<br>- Follow-up: collapse the `_legacy` redirect once callers move, and add focused tests under `tests/unit/common/test_style_resolver.py` covering inheritance/`!important`/clone scenarios.<br>- Update `StyleExtractor` to drop cache hacks when the new module is the only consumer. |
| `legacy/map/converter` (styles_runtime, traversal_hooks, transform/parser helpers) | `src/svg2ooxml/core/styling/` and `src/svg2ooxml/core/traversal/` | - ✅ Traversal stack (hooks, runtime, clipping, coordinate space) now lives under `core` and re-exports for compatibility.<br>- TODO: migrate the DrawingML path generator wiring and retire the remaining legacy shims once callers swap. |
| `legacy/parser/*` (DOM loader, `split` traversals, `svg_parser` workflows) | `src/svg2ooxml/core/parser/` (entry point + feature evaluators) | - ✅ Parser helpers (DOM loader, content sanitizer, color parsing, style context, references, result, normalization, statistics, services, units) now live under `core/parser`.<br>- ✅ Legacy shims removed; callers now import directly from the core surface. |
| `legacy/ir` data classes | `src/svg2ooxml/common/ir/` | - Relocate IR models and their helpers; adjust imports in `core/` and tests; document the stable API surface. |
| `legacy/geometry`, `legacy/units`, `legacy/transforms` | `src/svg2ooxml/common/geometry/`, `common/units/` | - Cherry-pick the minimal matrices/length utilities required by the new traversal/renderer.<br>- Introduce small, typed helpers and retire the broad legacy modules once consumers are migrated. |
| Remaining pipeline glue (`legacy/presentation`, `legacy/pipeline`, `legacy/render`) | `src/svg2ooxml/core/pipeline/` + `drawingml/` writers | - As soon as the DrawingML writer stabilises, move the PPTX packaging steps out of `legacy/presentation` and delete the compatibility CLI.<br>- Replace legacy render fallbacks with the new renderer surface (or drop if obsolete). |

## Outstanding Moves
- `legacy/map`, `legacy.render`, `legacy.paint`, and
  `legacy.filters` still implement the svg2pptx mapping pipeline. Plan the
  extraction into the new `core`/`drawingml` layers, splitting functionality
  into dedicated modules rather than monolithic translators.
- `legacy.ir` contains the intermediate representation types. Decide whether
  IR models remain shared under `common/` or evolve into a new dedicated
  package.
- `legacy.geometry`, `legacy.units`, and `legacy.transforms` power a lot of the
  adapter math. Identify the minimal APIs the new pipeline needs and move them
  into `common/geometry` helpers.
- `legacy.performance`, `legacy.batch`, and `legacy.multipage` are not yet
  wired into the new orchestrator. Confirm which surfaces we keep and whether
  they graduate into `core` versus becoming optional extras.
- `legacy.presentation` and `legacy.pipeline` currently feed the PPTX exporter.
  Once the new `drawingml.writer` flow lands, fold the remaining pieces into
  `io/` and retire the compatibility wrapper.

## Legacy Map Migration Blueprint

To unblock the remaining moves, the legacy map pipeline will migrate in the
following slices. Each batch keeps the compatibility re-exports in place until
callers and tests can switch over.

### Target package layout
- `src/svg2ooxml/core/ir/`: IR converter (`IRConverter`), scene models (`IRScene`,
  element metadata), traversal orchestration, and tracing hooks.
- `src/svg2ooxml/core/masks/`: mask and clip helpers (`MaskProcessor`, clip
  usage tracking) that feed both IR conversion and DrawingML writers.
- `src/svg2ooxml/core/hyperlinks/`: hyperlink processor plus DI glue currently
  surfaced from services.
- `src/svg2ooxml/core/traversal/bridges/`: `resvg` clip/mask collectors and
  element lookup bridges shared by traversal and mask extraction.
- `src/svg2ooxml/drawingml/bridges/`: `resvg` paint bridge, EMF fallbacks, and
  DrawingML-specific geometry adapters.
- `src/svg2ooxml/services/providers/`: service registration shims for masks,
  hyperlinks, EMF adapters, and tracing to replace the legacy `services.resolve`
  lookups.

### Migration batches
1. **IR core move – ✅**: create `core/ir/` and relocate `IRScene`, `IRConverter`,
   traversal mixins, and tracer preload logic. Update imports under
   `core/parser`, `io/pptx_writer`, CLI, and tests to use the new surface.
2. **Mask + clip services – ✅**: move `MaskProcessor`, clip/marker usage tracking,
   and `collect_resvg_*` helpers into `core/masks/` and `core/traversal/bridges/`.
   Teach the services setup to instantiate the new modules.
3. **Hyperlink + service wiring – ✅**: migrate `HyperlinkProcessor` and the service
   discovery helpers into `core/hyperlinks/` and concrete providers so callers
   stop depending on `legacy.map`.
4. **Resvg paint bridge / EMF adapters – ✅**: resvg paint bridge, gradient
   descriptors, and EMF path adapters now live under `drawingml/bridges/` with
   focused unit coverage in `tests/unit/drawingml`.
5. **Pipeline and mapper cleanup**: collapse the remaining legacy mapper
   wrappers into `core/pipeline/` entry points and delete the compatibility
  layer once downstream packages import from `core` and `drawingml`.

### Test realignment
- Duplicate `tests/unit/map/test_ir_converter.py`, `test_tracer.py`,
  `test_mask_processor.py`, and related fixtures under mirrored `tests/unit/core`
  or `tests/unit/drawingml` paths during each migration batch.
- Add integration coverage in `tests/integration/core/test_pipeline.py` once the
  new modules are live, ensuring compatibility shims can be removed without
  regressing the PPTX exporter.

## Follow-Up Actions
- Each promotion out of `legacy/` should:
  1. Add or update unit tests under `tests/unit/` mirroring the new module.
  2. Document the change (and any removed APIs) here and in `docs/structure.md`.
  3. Drop the compatibility shim once callers have moved to the new path.
- Record open questions about GCP integration, batching, or fonts alongside
  their owners so we maintain visibility on systems work required before the
  first release.
