# ADR: Geometry & Intermediate Representation Port

- **Status:** In Progress
- **Date:** 2025-XX-XX
- **Owners:** svg2ooxml migration team
- **Depends on:** ADR-parser-core (parser output contracts)
- **Blocks:** ADR-policy-map (mapper), ADR-filters-paint, ADR-text-fonts

## Context

svg2pptx defines a rich geometry and IR stack across several large modules:

- `core/paths/drawingml_generator.py`, `parser.py`, `path_system.py`, `arc_converter.py`, etc., convert SVG path commands into DrawingML-friendly primitives, handling transforms, coordinate systems, and Bezier approximations.
- `core/ir/scene.py`, `ir/shapes.py`, `ir/text.py`, and related files model the Clean Slate intermediate representation, including text layout, paint references, clip/mask linking, and validation rules.
- `core/elements/*.py` provide processors for gradients, patterns, and images that bridge parser definitions to IR paint structures.
- Fractional EMU math (`core/fractional_emu`), transform decomposition (`core/transforms/core.py`), and geometry algorithms (curve text positioning) underpin layout fidelity.

These modules are tightly coupled: path parsing relies on coordinate systems, IR scene builders expect certain paint/geometry structures, and elements processors manipulate numpy-backed data.

## Decision

Establish dedicated packages in svg2ooxml and port functionality into focused modules:

- **Geometry Layer**
  - `geometry/paths/parser.py`, `geometry/paths/drawingml.py`, `geometry/paths/arc_converter.py` – encapsulate path parsing, conversion to DrawingML primitives, and special-case arc handling.
  - `geometry/clip/`, `geometry/algorithms/curve_text_positioning.py`, `geometry/fractional/precision.py` – host reusable geometry helpers formerly in `core/clip` and `core/fractional_emu`.
  - `transforms/decomposition/` and `parser/geometry/matrix.py` – extend the existing Matrix2D helper with decomposition functions.

- **IR Models**
  - `ir/scene.py`, `ir/shapes.py`, `ir/text.py`, `ir/paint.py`, `ir/effects.py` – port data classes and validation logic directly, keeping module names consistent.
  - `elements/gradient_processor.py`, `elements/pattern_processor.py`, `elements/image_processor.py` – migrate processor logic with minimal changes, depending on the same IR paint models.

- **Integration Points**
  - Ensure `map/ir_converter.py` (once ported) consumes IR classes via clean imports (`from svg2ooxml.ir.scene import Scene` etc.).
  - Share precision helpers through `geometry/fractional/` instead of multiple inline numpy hacks.

Refactoring objectives:

- Reduce file size by splitting giant modules into clearly scoped files (`paths/drawingml_generator.py` → `geometry/paths/drawingml.py`, `geometry/paths/curve_tools.py`, etc.).
- Isolate numpy-dependent code under one package to simplify optional dependencies.
- Introduce type hints and dataclasses where legacy code used loose dictionaries.
- Maintain fidelity: do not change path tessellation or text shaping logic unless tests prove equivalence.

## Consequences

- **Pros**
  - Geometry and IR logic become discoverable and testable in isolation.
  - Mapper and filters can import from stable modules without reaching into legacy namespaces.
  - Future optimizations (e.g., alternative path generators) can swap modules cleanly.
- **Cons**
  - Porting effort is significant; must ensure behavior matches svg2pptx via regression tests.
- Some modules may still be large; additional slicing might be required once code is in place.

## Dependency Notes

- NumPy remains an **optional accelerator**. When available it backs matrix math via `ir/numpy_compat.py`; otherwise we fall back to pure-Python shims. Consumers that need deterministic output without NumPy must install the new `accel` extra (`pip install svg2ooxml[accel]`).
- Geometry tests exercise both code paths to ensure the absence of NumPy continues to produce valid (if slower) results.

## Migration Plan

1. ✔️ Ported IR dataclasses (`scene`, `shapes`, `text`, `paint`, `effects`, `geometry`) into `src/svg2ooxml/ir/`; validation utilities still pending.
2. ✔️ Move elements processors (gradient, pattern, image) into `src/svg2ooxml/elements/` preserving interfaces expected by IR and mapper layers.
3. ✔️ Geometry helpers now include fractional EMU conversion (`geometry/fractional/`), transform decomposition (`geometry/transforms/`), arc/path parsing (`geometry/paths/`), curve-text positioning, WordArt warp fitting, and the DrawingML serializer (`geometry/paths/drawingml.py`) backing the refactored path generator.
4. Path parsing/drawing started (`geometry/paths/parser.py`, `drawing.py`) and the first DrawingML path generator now emits custom geometry; policy integration now lives in `policy.geometry.apply_geometry_policy`, wiring mapper decisions into the shared architecture.
5. Update `map/ir_converter.py` stub to import the new IR classes and geometry helpers; adjust ADR-policy-map accordingly.
6. Add ADR-linked TODOs to each placeholder file and write unit tests comparing IR outputs and path tessellation to svg2pptx baselines.

## Status Notes

- Placeholder audit: remaining geometry/IR stubs should retain `TODO(ADR-geometry-ir)` breadcrumbs (tracked in GEOM-21); most core modules already migrated.
- Fractional EMU helpers (`geometry/fractional/*`) now have unit coverage comparing STANDARD vs ULTRA precision; maintain parity if the constants change.
- Downstream alignment: policy and mapper layers consume shared metadata fallbacks; keep filters/text ADRs synced with `svg2ooxml.ir` contracts when they progress.
