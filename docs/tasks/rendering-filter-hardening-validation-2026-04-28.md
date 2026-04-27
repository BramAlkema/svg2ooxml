# Rendering and Filter Hardening Validation - 2026-04-28

## Scope

This batch tightens the DrawingML rendering/filter path and keeps the
decomposition work reviewable:

- Split shared dash-pattern normalization into `common.dash_patterns`.
- Split animation oracle/timing XML helpers out of larger writer modules.
- Split filter planner shared helpers into `filters.planner_common`.
- Harden raster adapter/bounds/preview input coercion.
- Harden `FilterService` strategy handling and runtime trace metadata.
- Add focused unit coverage for the extracted helpers and fallback behavior.

## Review Fixes

- Added all split helper modules to the tracked diff so clean checkouts can
  import the updated facade modules.
- Replaced multi-exception handlers with parenthesized syntax so older Python 3
  parsers do not fail test collection on changed files.

## Local Validation

Run from the repository root:

```bash
./.venv/bin/python -m ruff check src/svg2ooxml/drawingml/raster_preview.py src/svg2ooxml/drawingml/raster_adapter.py src/svg2ooxml/drawingml/raster_bounds.py src/svg2ooxml/filters/planner_common.py src/svg2ooxml/filters/lightweight.py src/svg2ooxml/filters/planner.py src/svg2ooxml/common/dash_patterns.py src/svg2ooxml/drawingml/animation/oracle_templates.py src/svg2ooxml/drawingml/animation/oracle_vocabulary.py src/svg2ooxml/drawingml/animation/timing_build_list.py src/svg2ooxml/drawingml/animation/timing_conditions.py src/svg2ooxml/drawingml/animation/timing_tree.py src/svg2ooxml/drawingml/animation/timing_values.py
./.venv/bin/python -m pytest tests/unit/common/test_dash_patterns.py tests/unit/filters/test_planner.py tests/unit/filters/test_lightweight.py tests/unit/drawingml/test_raster_bounds.py tests/unit/drawingml/test_raster_preview.py tests/unit/drawingml/test_rasterizer.py -q
./.venv/bin/python -m pytest tests/unit/filters tests/unit/services -q
./.venv/bin/python -m pytest tests/unit/drawingml -q
./.venv/bin/python -m pytest tests/unit tests/e2e -q
git diff --check
```

Latest local result:

- focused helper tests: `25 passed`
- filters/services: `305 passed`
- DrawingML: `1087 passed`
- unit plus e2e: `2766 passed`
- diff whitespace check: clean

## CI Follow-Up

After pushing the branch, inspect the GitHub Actions runs for the pushed head:

```bash
gh run list --branch fix/svg-animation-e2e --limit 10
gh run view <run-id> --log-failed
```
