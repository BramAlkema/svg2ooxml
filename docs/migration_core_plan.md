# Core Flow Migration Plan

This outline guides the move of svg2pptx's core conversion flow into svg2ooxml while keeping modules compact, refactoring continuously, and enforcing linting.

## 1. Prepare Reference Material
- List the source modules in svg2pptx that form the conversion path (parser, mapper, policy engine, package builder).
- Capture any implicit contracts (dataclasses, TypedDicts, enums) used across the flow; convert them into lightweight specs inside `docs/`.
- Record fixture coverage: note SVG samples and expected PPTX artifacts we need to port later.

## 2. Define Target Modules (Small Files)
- `src/svg2ooxml/core/parser.py` – SVG → intermediate shapes (limit to parsing helpers).
- `src/svg2ooxml/core/mapper.py` – transforms shapes into DrawingML-friendly structures.
- `src/svg2ooxml/core/policy_runner.py` – applies policy choices; depends only on `policy/`.
- `src/svg2ooxml/core/package.py` – assembles slides and delegates to `io/pptx_writer.py`.
- Keep each file focused; when a helper grows, split into `helpers/` submodule or move to `common/`.

## 3. Incremental Porting Steps
1. Copy the minimal parser logic, prune unused branches, and adapt imports to svg2ooxml names.
2. Port mapper functions in chunks; after each chunk, run tests and lint before moving on.
3. Introduce the policy runner; re-evaluate configuration objects to ensure TypedDict/dataclass fit and stay small.
4. Build the package module, reusing the new `drawingml.writer` placeholder; adjust writer implementations as they arrive.

## 4. Continuous Refactoring & Testing
- After each module port, replace placeholder tests with focused unit tests that mirror the new code.
- Leverage visual fixtures only when the mapper/package logic stabilizes; keep them out of tight loops.
- Maintain `docs/structure.md` and this plan to reflect new files or module splits.

## 5. Linting & Quality Gates
- Run `ruff check src tests` and `black --check src tests` after each ported module.
- Add mypy targets as types solidify; start with `mypy src/svg2ooxml/core` and expand outward.
- Gate commits locally via `pre-commit run --all-files` once hooks are active.

## 6. Exit Criteria for the Core Flow
- Parser, mapper, policy runner, and package modules live in svg2ooxml with clear docstrings.
- Unit tests cover happy path plus edge cases previously covered in svg2pptx.
- Lint (`ruff`, `black`) and type checks (`mypy`) succeed.
- Docs updated to reflect the new flow; issues logged for remaining subsystems (filters, text, batch, etc.).
- Colour engine parity achieved: gradients/patterns use OKLab statistics and
  raster normalisation supports perceptual linear RGB. Developers can inspect
  palette diagnostics via `tools/color_palette_report.py` (install `pip install -e .[color]`).
