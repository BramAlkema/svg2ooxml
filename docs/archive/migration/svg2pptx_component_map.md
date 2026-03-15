# svg2pptx → svg2ooxml Component Map

This document captures the complete surface area of the legacy `svg2pptx` codebase so we can plan a faithful migration into `svg2ooxml`. Every major package under `core/` and the surrounding infrastructure folders are listed with their responsibilities and the intended home (or status) in the new repository. Use this as the master checklist when porting subsystems.

## Legend
- **Target** — Where the functionality should live in `svg2ooxml`. `TBD` means the destination folder needs to be created.
- **Plan** — High-level migration note: *Port*, *Refactor*, *Re-evaluate*, or *Supersede*.
- **Key Dependencies** — Upstream or downstream modules we must keep in sync.

## Core Packages

| svg2pptx/core/... | Responsibility (summary) | Target in svg2ooxml | Plan | Key Dependencies |
| --- | --- | --- | --- | --- |
| `algorithms` | Geometry/matrix utilities (SAT, polygon ops) | `src/svg2ooxml/geometry/algorithms` | Port (selective) | `core/clip`, `core/map`, `core/transforms` |
| `analyze` | Debug/inspection helpers for scenes | `tools/analysis` | Re-evaluate (optional) | `core/ir`, `core/map` |
| `animations` | SMIL parsing, animation mapping | `src/svg2ooxml/animations` | Port | `core/parse`, `core/policy`, `core/map` |
| `auth` | Google OAuth helpers | `api/auth` | Re-evaluate (keep external) | `api/`, `batch/` |
| `batch` | Huey-based batch processing | `services/batch` | Port later | `api/`, `io/` |
| `clip` | Clip path segmentation & mapping | `src/svg2ooxml/geometry/clip` | Port (after parser roadmap) | `core/paths`, `core/map` |
| `color` | Full color parsing, ICC, profiles | `src/svg2ooxml/color` | Port fully (current helper is placeholder) | `core/css`, `core/map`, `filters` |
| `compat` | Compatibility fallbacks (legacy behaviors) | `src/svg2ooxml/compat` | Re-evaluate, bring only needed cases | Various |
| `converters` | Legacy converter wrappers | Supersede (new pipeline) | Supersede | `core/pipeline` |
| `css` | CSS parsing, cascading rules | `src/svg2ooxml/css` | Port | `core/parse`, `core/map`, `core/text` |
| `data` | Sample fixtures & config data | `assets/`, `examples/` | Copy selectively | Many |
| `elements` | DOM abstractions for IR nodes | `src/svg2ooxml/elements` | Port | `core/ir`, `core/map` |
| `emf` | EMF export utilities | `src/svg2ooxml/io/emf` | Re-evaluate (maybe optional) | `core/map`, `core/paint` |
| `examples` | runnable demos | `examples/` | Copy curated set | Pipeline, CLI |
| `filters` | SVG filters to OOXML mapping | `src/svg2ooxml/filters` | Port | `core/map`, `core/policy` |
| `fonts` | Font discovery, embedding | `src/svg2ooxml/fonts` | Port | `core/text`, `io/` |
| `fractional_emu` | Precision math utilities | `src/svg2ooxml/geometry/fractional` | Port (needed for fidelity) | `core/ir`, `core/presentation` |
| `groups` | Group/canvas mapping logic | `src/svg2ooxml/map/groups` | Port | `core/map`, `core/policy` |
| `io` | File adapters (SVG ingest, PPTX output) | `src/svg2ooxml/io` | Already partially ported | `parser/`, `presentation/` |
| `ir` | Intermediate representation models | `src/svg2ooxml/ir` | Port | `core/map`, `core/policy` |
| `legacy` | Deprecated code kept for reference | Archive | Archive only, no port | None |
| `map` | Core scene mapper into DrawingML | `src/svg2ooxml/map` | Port in phases | `core/ir`, `drawingml/` |
| `multipage` | Multi-slide splitting logic | `src/svg2ooxml/pipeline/multipage` | Port | `core/policy`, `core/pipeline` |
| `paint` | Paint definitions & resolvers | `src/svg2ooxml/paint` | Port | `core/color`, `filters` |
| `parse` | Main SVG parser pipeline | `src/svg2ooxml/parser` | In progress | `css`, `transforms`, `units` |
| `parse_split` | Refactored parsing stages (validators, clip extractor) | Merge into `parser/` modules | Port gradually | `parse`, `clip`, `xml` |
| `paths` | Path parsing & normalization | `src/svg2ooxml/geometry/paths` | Port | `core/map`, `filters` |
| `performance` | Performance profiling hooks | `metrics/`, `tools/perf` | Optional | Many |
| `pipeline` | Clean Slate pipeline orchestration | `src/svg2ooxml/pipeline` | Port | All core subsystems |
| `policy` | Policy engine (quality vs. speed) | `src/svg2ooxml/policy` | Port | `core/map`, `filters`, `multipage` |
| `pre` | Preprocessing (sanitizers, heuristics) | `src/svg2ooxml/preprocessing` | Port selectively | `parse`, `css` |
| `presentation` | PPTX packaging, templates | `src/svg2ooxml/presentation` | Port | `drawingml`, `io` |
| `services` | Dependency injection & global services | `src/svg2ooxml/services` | Rework (lean DI) | All |
| `text` | Text layout, font mapping | `src/svg2ooxml/text` | Port | `fonts`, `css`, `map` |
| `transforms` | Transform parsing & matrix math | `parser/geometry` + `geometry/transforms` | In progress (expand) | `paths`, `map` |
| `units` | Unit conversion | `parser/units`, `geometry/units` | In progress | `parse`, `map`, `presentation` |
| `utils` | Shared utilities | `src/svg2ooxml/common` | Port sparingly | Many |
| `viewbox` & `viewbox_new` | ViewBox computations | `parser/units` or `geometry/viewbox` | Port | `parse`, `map` |
| `xml` | XML helpers (safe iteration, normalizers) | `core/parser/xml_utils.py` | Port | `parse`, `clip` |

## Additional Top-Level Folders

| svg2pptx path | Responsibility | Target | Plan | Notes |
| --- | --- | --- | --- | --- |
| `api/` | FastAPI service (REST) | `api/` in svg2ooxml | Port later | Relies on batch, auth |
| `adapters/` | Integration adapters | `adapters/` | Re-evaluate | |
| `analysis/` | Analysis scripts/documents | `docs/analysis`, `tools/analysis` | Copy curated set | |
| `archive/` + `archive_old/` | Historical code & docs | `archive/` | Keep as reference only | |
| `cli/` | CLI entry points | `cli/` | Port | Depends on pipeline |
| `data/`, `testing/`, `examples/` | Fixtures, test art | `assets/`, `testing/`, `examples/` | Copy as needed | |
| `deliverables/` | Reports & docs | `docs/deliverables` | Migrate selectively | |
| `development/`, `specs/`, `docs/` | Documentation | `docs/` | Port key specs & ADRs | Must keep ADR history |
| `metrics/`, `reports/`, `results/`, `visual_reports/` | Metrics outputs | `reports/`, `metrics/` | Optional | |
| `pipeline/` (root) | Generated reports, validation | `reports/` | Optional | |
| `scripts/`, `tools/` | Developer tooling | `tools/` | Port essential | |
| `tests/` (rich test suites) | Unit/integration/visual tests | `tests/` | Port gradually (new layout) | |
| `pptx_scaffold/` | PPTX templates | `pptx_scaffold/` | Port | |
| `presentationml/` | Example PPTX parts | `presentationml/` | Port | |

## Migration Strategy Outline

1. **Parser & Geometry Backbone** — Finish porting the parser, transforms, units, and viewBox utilities so clip/mask/color subsystems can reuse them without divergence.
2. **IR and Mapping** — Bring over the IR models (`core/ir`, `core/elements`) and the mapper (`core/map`, `core/policy`), anchored on the same data contracts as the legacy code.
3. **Rendering Surfaces** — Port paint, filters, text, fonts, and presentation packaging together so rendering fidelity is preserved.
4. **Pipeline & Services** — Recreate the Clean Slate pipeline, multipage logic, and service orchestration once the building blocks are in place.
5. **API/Batch/CLI** — Layer on automation, REST services, and tooling after the core conversion path is stable.

## Open Questions / TODOs

- Determine which compatibility modules are still required (e.g., legacy OOXML fallbacks, edge-case heuristics).
- Decide how much of the performance profiling infrastructure we want in the inaugural release.
- Audit `core/viewbox_new` vs. `core/viewbox` to choose the canonical implementation before porting.
- Review `core/services` to see whether we keep the dependency injection container or shift to simpler factories.
- Inventory test suites to understand which golden fixtures and visual diffs are mandatory for regression coverage.

Keep this map updated as subsystems move. Every migration PR should reference the rows it completes.
