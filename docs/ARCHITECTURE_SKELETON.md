# Architecture Skeleton

This repository currently exposes a placeholder implementation of the full svg2ooxml stack. Every major subsystem from svg2pptx already has a matching package so we can port functionality in-place without reshuffling directories later. Use this document as a quick reference for what lives where and which modules are still stubs.

## High-Level Layers

- **Parser Layer** (`parser/`, `css/`, `transforms/`, `units/`, `viewbox/`, `color/`, `clip/`, `masks/`)
  Responsible for ingesting SVG markup, normalising geometry, interpreting units, and preparing reusable scene metadata. Most files are lightweight scaffolds; the svg2pptx logic will replace these stubs.
  - `parser/dom_loader.py`, `parser/normalization.py`, `parser/style_context.py`, `parser/reference_collector.py`, and `parser/statistics.py` slice the legacy `core/parse/parser.py` into modular entry points ready for porting.
  - `core/parser/xml_utils.py` provides the safe iteration helpers previously located under `legacy/parser/xml`.

- **Intermediate Representation** (`ir/`, `elements/`, `geometry/`, `paint/`, `fonts/`, `text/`)  
  Houses IR models, geometry helpers, paint definitions, and text layout primitives. These packages are empty wrappers right now to keep imports stable for upcoming ports.

- **Mapping & Rendering** (`map/`, `filters/`, `multipage/`, `presentation/`, `drawingml/`)
  Will contain the Clean Slate mapper, filter conversions, multi-slide splitting, and PPTX packaging logic. Stubs live in each directory so the complete pipeline can be wired as modules arrive.
  - `filters/effects/*` includes placeholders for displacement map, component transfer, and specular lighting conversions while `filters/image/color_adjustment.py` stands in for image-level color handling.
  - `drawingml/generator.py` and `map/ir_converter.py` anchor the DrawingML geometry path and IR conversion logic from svg2pptx.

- **Pipeline & Policies** (`pipeline/`, `policy/`, `services/`)
  Orchestrates dependency injection, policy decisions, and staged execution. Each subpackage has placeholder `__init__.py` files plus subfolders for policies/stages/service providers.
  - `policy/engine.py`, `policy/targets.py`, `services/conversion.py`, and `services/cache.py` mirror the heavy service management files from svg2pptx, now ready to receive real implementations.
  - `services/setup.py` and `services/providers/registry.py` mark the entry point for DI wiring and provider registration.

- **Automation & Integration** (`animations/`, `batch/`, `api/`, `examples/`, `tools/`)
  Reserved for animation conversion, batch processing, REST exposure, and tooling. Only minimal docstrings exist today; functionality will drop in once the core converter stabilises.
  - `api/routes/svg.py`, `batch/workers/huey.py`, and `cli/main.py` are placeholders for the public surfaces previously served by FastAPI, Huey, and the CLI.

- **Performance & Diagnostics** (`performance/`, `services/cache.py`, `tests/`)
  Collects profiling hooks, metrics recorders, and cache inspectors so the mature instrumentation from svg2pptx has a landing zone. The `testing/` directory now includes fixtures, golden outputs, and visual baselines to mirror the legacy regression assets.

- **Compatibility & Preprocessing** (`compat/`, `preprocessing/`)
  Hosts heuristic fallbacks and sanitizers. Files such as `compat/fallbacks.py` and `preprocessing/sanitizers.py` exist so the fidelity-preserving tweaks from svg2pptx can be ported without moving code later.

## Placeholder File Expectations

Every package exports:

- A docstring in `__init__.py` describing the intended responsibility.
- (Optional) subpackages such as `geometry/algorithms/` or `services/registry/` to anchor future modules.
- No concrete implementations yet—unit tests will be added when real code is ported.

## Migration Guidance

1. When porting legacy modules, replace the placeholder docstring with the real implementation and add tests mirroring svg2pptx coverage.
2. If a subsystem requires additional structure (e.g., splitting `map/` into `map/groups/`, `map/shapes/`), create the subpackages before copying code so the hierarchy stays predictable.
3. Update `docs/structure.md` and `docs/svg2pptx_component_map.md` whenever folders move or are filled in.
4. Avoid introducing new top-level packages without reflecting the change in the component map—keeping that document in sync is the primary guard against regressions.

With this skeleton in place, we can port high-fidelity svg2pptx modules file-for-file while maintaining a clean, discoverable tree.
