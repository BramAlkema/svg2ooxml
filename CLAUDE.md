# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

svg2ooxml converts SVG markup into Office Open XML (PPTX) files. It parses SVG, builds a typed intermediate representation, renders DrawingML XML fragments, and packages them into valid PPTX. It also has a FastAPI service for Cloud Run deployment and a Figma plugin frontend.

## Build & Setup

```bash
./tools/bootstrap_venv.sh          # creates Python 3.11 venv
source .venv/bin/activate
pip install -r requirements-dev.txt # editable install with all extras + tooling
```

For a subset: `pip install -e .[slides]`, `.[render]`, `.[color]`, `.[api]`, `.[cloud]`.

## Common Commands

**Always use the project venv** — prefix all Python/pytest commands with `.venv/bin/`:

```bash
# Testing
.venv/bin/python -m pytest                              # default suite (unit + integration), stops on first failure
.venv/bin/python -m pytest -m unit                      # fast unit tests only
.venv/bin/python -m pytest -m "unit and not slow"       # tight dev loop
.venv/bin/python -m pytest -m integration               # cross-module tests
.venv/bin/python -m pytest -m visual                    # visual regression (needs render extra + LibreOffice)
.venv/bin/python -m pytest -k test_name                 # run single test by name

# Linting & formatting
.venv/bin/ruff check src tests      # lint (mirrors pre-commit hook)
.venv/bin/black src tests           # format (88-column)
.venv/bin/mypy src                  # type check

# Visual review
svg2ooxml visual                    # browser side-by-side viewer (needs LibreOffice soffice)
python -m tools.visual.w3c_suite    # batch render W3C SVG fixtures

# Local API dev
uvicorn main:app --reload           # FastAPI server
python cli/run_worker.py            # Huey background worker
```

pytest is configured with `--maxfail=1 --strict-markers`. Test markers: `unit`, `integration`, `visual`, `slow`, `smoke`, `requires_network`.

## Architecture

### Conversion Pipeline

```
SVG text
  → SVGParser.parse()              → ParseResult (lxml tree + metadata)
  → convert_parser_output()        → IRScene (typed intermediate representation)
  → DrawingMLWriter.render()       → DrawingMLRenderResult (XML fragments + assets)
  → PPTXPackageBuilder.write()     → .pptx file
```

`SvgToPptxExporter` is the high-level facade that orchestrates this pipeline, including multipage splits, animation sampling, and variant expansion.

### Key Modules (under `src/svg2ooxml/`)

- **`core/parser/`** — `SVGParser`, `ParserConfig`, `ParseResult`. CSS parsing via tinycss2, DOM via lxml.
- **`core/ir/`** — `IRConverter` transforms ParseResult into the typed IR scene graph.
- **`ir/`** — IR data structures: `IRScene`, scene graph nodes (Group, Shape, Text, Image), animation types. Entry point: `convert_parser_output()`.
- **`drawingml/`** — XML writers. `DrawingMLWriter` orchestrates shape/text/mask/animation rendering. Subnmodules for animation handlers, bridges (EMF, CustomGeometry), rasterizer.
- **`io/`** — `PPTXPackageBuilder` and `write_pptx()` package XML into PPTX. EMF relationship management.
- **`services/`** — Service registry (`ConversionServices` dataclass). `configure_services()` wires providers for gradients, filters, patterns, images, fonts, masks, clips, color spaces.
- **`policy/`** — `PolicyEngine` with pluggable providers for tunable decisions (filter strategy, geometry mode, slide sizing).
- **`core/animation/`** — SMIL animation parsing (`SMILParser`, `TimelineSampler`).
- **`filters/`** — SVG filter effect implementations.
- **`api/`** — FastAPI routes (`/api/v1/export`, `/api/v1/tasks`).
- **`public.py`** — Curated public API surface.

### Design Patterns

- **Frozen dataclasses** (`@dataclass(frozen=True, slots=True)`) for all value objects and IR nodes.
- **Service registry** — `ConversionServices` with dependency injection; supports `clone()` and override injection for testing.
- **Mapper ABC** — `core/pipeline/mappers/base.py` defines the element traversal pattern (PathMapper, ImageMapper, TextMapper).
- **Bridge pattern** — adapters for external formats (EMF, CustomGeometry, Resvg).
- **PEP 562 lazy loading** — `__init__.py` files use `__getattr__` for deferred imports. Regenerate with `tools/rebuild_inits.py`.

### Test Layout

Tests mirror production code: `tests/unit/`, `tests/integration/`, `tests/visual/`, `tests/smoke/`. Unit and integration markers are auto-applied by conftest based on directory. Visual tests produce artifacts in `reports/visual/` and require `skia-python` + LibreOffice.

## Project-Specific Notes

- Python >=3.10, targets py310 for ruff/black/mypy.
- The GCP project (`powerful-layout-467812-p1`) was deleted 2026-01-16 — Cloud Run and related CI/CD are currently non-functional.
- `SVG2OOXML_SOFFICE_PATH` env var overrides LibreOffice binary path; `SVG2OOXML_SOFFICE_USER_INSTALL` sets a custom profile dir if headless soffice crashes.
- ADRs in `docs/adr/` document key architectural decisions (resvg strategy, EMF fallbacks, queue/cache, gcloud setup).
- `docs/ROADMAP.md` tracks project status and priorities.
