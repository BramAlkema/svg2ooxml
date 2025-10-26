# Parser Helper Consolidation Plan

Transform parsing, viewBox math, SVG unit conversion, and color handling live in scattered modules throughout svg2pptx. Before we port them, centralize the responsibilities in svg2ooxml so every parser/mapping module depends on a single source of truth.

## 1. Current State Audit
- List all helpers in svg2pptx that deal with transforms (`core/transforms/parser.py`, matrix ops), unit conversion (`core/units/core.py`), viewBox normalization (`core/transforms/coordinate_space.py`), and color parsing (`core/css`, `core/color/parser.py`).
- Note their inputs/outputs, side effects (e.g., logging, service registration), and any implicit contracts with other modules.
- Capture gaps or inconsistencies (e.g., multiple functions parsing transform strings differently).

## 2. Target Modules in svg2ooxml
- `parser/geometry.py` – matrix utilities, transform parsing, reusable bounding-box helpers shared by clip/mask collectors.
- `parser/units.py` – abstract unit conversion hooks, default DPI handling, and viewBox-to-pixel calculations.
- `parser/colors.py` – minimal color parsing functions (hex/rgb/rgba/currentColor) ready for future policy hooks.
- `parser/context.py` – optional orchestrator that bundles geometry, units, and color helpers for downstream callers.

Keep files under ~150 lines; when logic grows, split into submodules (e.g., `parser/geometry/matrix.py`).

## 3. Incremental Porting Steps
1. Start with transform parsing: port the string tokenizer + matrix builder into `parser/geometry.py`, retaining only the minimal cases required by clip/mask traversal.
2. Introduce a lightweight unit converter in `parser/units.py` (common units: px, pt, in, cm, mm) plus viewBox normalization helpers.
3. Add basic color parsing (`#rgb`, `#rrggbb`, `rgb()`, `rgba()`) in `parser/colors.py`, returning simple tuples/TypedDicts to avoid premature coupling.
4. Create integration points by updating `SVGParser` to import these helpers and replacing inline logic (e.g., viewBox detection, transform parsing once used by clip/masks).

Run `ruff check src tests` and `pytest` after each step; update tests or add new ones mirroring critical paths from svg2pptx.

## 4. Validation & Documentation
- Add unit tests per new helper module (matrix parsing cases, unit conversion edge cases, color parsing fallbacks).
- Expand `docs/structure.md` to include the new modules and briefly describe their responsibilities.
- Update `docs/migration_core_plan.md` with checkboxes for each helper consolidation step so contributors can track progress.

## 5. Exit Criteria
- Transform, unit, viewBox, and color logic is centralized under `parser/`.
- All parser and collector modules consume the new helpers instead of rolling their own conversions.
- Lint and tests pass, and future porting tasks can rely on the shared utilities.
