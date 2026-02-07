# Architecture Guardian Memory

## Project: svg2ooxml
Converts SVG to PowerPoint PPTX via DrawingML. Python 3.10+, lxml-based XML generation.

## Centralized Conversion System (`common/conversions/`)
- `opacity.py`: `opacity_to_ppt(float) -> int` -- clamp [0,1] + round + scale to 0-100000
- `angles.py`: `degrees_to_ppt()`, `radians_to_ppt()`
- `scale.py`: `scale_to_ppt()` (unclamped), `position_to_ppt()` (clamped 0-1)
- ADR-022 migrated all inline `* 100000` patterns to centralized functions
- Animation module has its own `unit_conversion.py` with `PPT_OPACITY_FACTOR` (ADR-020 scope)
- ISSUE: No generic `fraction_to_ppt` -- `opacity_to_ppt` misused for non-opacity fractions

## DRY Violations (2026-02-07 audit)
- **4 `px_to_emu` implementations**: `common/units/conversion.py` (returns float), `drawingml/generator.py` (returns int, handles None), `common/conversions/powerpoint.py` (class method), `drawingml/animation/unit_conversion.py` (class method)

## Known Bugs (2026-02-07 audit)
- `core/resvg/text/drawingml_generator.py`: Missing imports for `px_to_emu` and `StrokeStyle`
- `core/pptx_exporter.py:547`: `Mapping` in type hint but not imported (latent)
- `ir/entrypoints.py:30`: `Dict` in type hint but not imported (latent)
- `core/ir/converter.py:36`: `AnimationDefinition` in type hint but not imported (latent)

## Stale Build Artifacts (2026-02-07 audit)
- `SOURCES.txt`: Missing new animation files
- `drawingml/animation/__init__.py`: Missing `id_allocator`, `timing_utils`, `unit_conversion`
- `drawingml/__init__.py`: Missing `graft_xml_fragment` from symbol map
- `pyproject.toml`: No `[project.scripts]` entry point; CLI at `cli/main.py` unreachable
- `requirements-dev.txt`: References `[worker]` extra which doesn't exist

## Debug Leftovers (2026-02-07 audit)
- `drawingml/writer.py:101-103,146-150`: In-function import logging/re, regex XML parsing
- `drawingml/animation_pipeline.py:106-109`: In-function import logging, debug info calls

## Module Boundary Violations (2026-02-07 audit)
- `core/pipeline/mappers/` generates DrawingML XML (should be in `drawingml/`)
- `core/traversal/` imports from `drawingml/generator` and `drawingml/custgeom_generator`
- `services/` has 12+ imports from `drawingml/`
- `filters/` imports from `drawingml/xml_builder` and `drawingml/filter_renderer`
- `ir/` is CLEAN -- no rendering imports

## ADR-021 Status (2026-02-07 audit)
- Phase 1 (graft_xml_fragment): COMPLETE
- Phase 2 (producers return elements): PARTIAL -- animation/navigation done, 6 graft sites remain
- Phase 3 (delete helper): BLOCKED

## Pipeline Architecture
- Writer: string-based (`_render_elements` -> `list[str]` -> template injection)
- `DrawingMLRenderResult.slide_xml`: str
- IRScene: mutable dataclass (metadata accumulation pattern)
- CustomGeometry: has both `xml: str` and `element: etree._Element` fields

## Key Constants
- PPT_OPACITY_SCALE = 100,000
- PPT_ANGLE_FACTOR = 60,000
- EMU_PER_PX = 9,525
- Slide size: 9144000 x 6858000 EMU

See also: [detailed-audit-notes.md](detailed-audit-notes.md) for full findings.
