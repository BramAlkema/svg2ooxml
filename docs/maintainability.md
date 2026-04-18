# Maintainability Guardrails

This project intentionally favors smaller modules with focused responsibilities.
To keep the codebase maintainable as it grows:

- Soft limit: `800` lines per Python file (warning threshold).
- Hard limit: `1500` lines per Python file (CI/test failure threshold).

## Checks

- Run local report:

```bash
python tools/check_file_sizes.py
```

- Run with stricter or custom thresholds:

```bash
python tools/check_file_sizes.py --soft-limit 600 --hard-limit 1500
```

- Unit enforcement:
  - `tests/unit/test_maintainability_file_sizes.py` fails if any Python file
    exceeds the hard limit.

## Refactor Pattern

When a file approaches the soft limit:

1. Extract pure helpers first (no side effects).
2. Extract IO/provider code into dedicated modules.
3. Keep the original facade/class/API stable.
4. Add targeted tests for extracted seams.
5. Confirm parity in the canonical `.venv` and the containerised render lane.

## Project Split Roadmap

Current priority modules above the soft limit:

1. `src/svg2ooxml/io/pptx_writer.py`
2. `src/svg2ooxml/render/filters.py`
3. `src/svg2ooxml/core/styling/style_extractor.py`
4. `src/svg2ooxml/core/ir/text_converter.py`
5. `src/svg2ooxml/common/geometry/algorithms/curve_text_positioning.py`

Execution order:

1. Split writer/IO orchestration from XML emitters (`pptx_writer.py`).
2. Split render pipeline orchestration from primitive filter ops (`render/filters.py`).
3. Split style parsing from CSS cascade resolution (`style_extractor.py`).
4. Split text layout extraction from IR object construction (`text_converter.py`).
5. Split numeric geometry kernels from path/curve adapters (`curve_text_positioning.py`).
