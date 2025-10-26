# Repository Guidelines

## Project Structure & Module Organization
House production code in `src/svg2ooxml/` and isolate responsibilities: `core/` for orchestration, `drawingml/` for XML writers, `policy/` for tunable decisions, `io/` for SVG/PPTX adapters, and `common/` for shared utilities. Tests mirror the package (`tests/unit`, `tests/integration`, `tests/visual`), with golden baselines in `tests/visual/golden/` and light fixtures under `assets/`. Keep living documentation, migration notes, and diagrams in `docs/`, runnable demos in `examples/`, and developer helpers inside `tools/`.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` — create and enter the virtual environment.
- `pip install -e .` — install svg2ooxml in editable mode (after `pyproject.toml` lands).
- `pip install -r requirements-dev.txt` — bring in pytest, black, mypy, ruff, and supporting tools.
- `pre-commit install` — enable formatting, lint, type, and security hooks.
- `pytest` — execute the default suite; send coverage and HTML reports to `reports/`.
- `pytest tests/unit -m "unit and not slow"` — quick feedback loop during active development.

## Coding Style & Naming Conventions
Run Black (4 spaces) and isort’s black profile through pre-commit; ruff handles quick linting. Use snake_case for functions and modules, PascalCase for classes, UPPER_SNAKE_CASE for constants, and keep public APIs typed so mypy with `strict_optional=True` stays green. While porting code from svg2pptx, strip unused parameters and align module names with the new package layout.

## Testing Guidelines
Pytest discovers `test_*.py`; mirror source paths (e.g., `src/svg2ooxml/core/pipeline.py` → `tests/unit/core/test_pipeline.py`). Use markers (`unit`, `integration`, `visual`, `slow`) to slice suites and document any new marker in `pytest.ini`. Hold statement coverage ≥70 % across `src/svg2ooxml`, and keep visual baselines in `tests/visual/golden/`, updating them with the helper script plus short before/after notes.

## Commit & Pull Request Guidelines
Write concise, imperative commit subjects (`Refactor policy mapper for shapes`) and keep changes bisectable. PR descriptions should call out the problem, the approach, and validation (commands, artifacts, follow-ups). Link issues or migration tickets, note configuration touches (`.env`, OAuth, queues), attach PPTX or visual diffs when the surface changes, and ensure pre-commit passes before review.

## Porting Checklist
When copying modules from svg2pptx, remove unused imports, collapse dead abstractions, and update package references to `svg2ooxml`. Bring over only pertinent tests, convert fixtures to the new asset layout, and log outstanding cleanup in `docs/porting.md`.
