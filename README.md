# svg2ooxml

SVG → Office Open XML conversion toolkit. The project is an evolution of the
internal svg2pptx converter and is being rebuilt around a small, well-typed
core that can run locally without GCP dependencies.

- **Core pipeline** – normalises SVGs via resvg and orchestrates stage execution.
- **DrawingML writers** – generate PPTX/Slides artefacts (currently stubs).
- **API surface** – FastAPI entry points with optional Firestore/Storage backends.
- **Legacy bridge** – svg2pptx-era modules live under `svg2ooxml.legacy`.

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

The developer requirements install svg2ooxml in editable mode with all runtime
extras (API, worker, cloud, rendering, colour, slides) plus linting and test
tooling. For a lean runtime-only stack use `pip install -r requirements.txt`.

## Development Workflow

- `ruff check src tests` – quick lint pass (mirrors the pre-commit hook).
- `black src tests` – formatting helper (the repo uses Black's 88-column style).
- `pytest` – runs the default suite; coverage and HTML reports land in `reports/`.
- `pytest -m "unit and not slow"` – tight loop for fast checks.
- `pre-commit install` – enable lint/type/security hooks before committing.
- `svg2ooxml visual` – launch the local side-by-side visual comparison server
  (requires LibreOffice's `soffice` binary for PPTX screenshots).
- `python -m tools.visual.w3c_suite` – build and render the curated W3C SVG
  fixtures; optionally compare against baselines once LibreOffice is
  configured.
- `gcloud auth login && gcloud run services list` – interact with the Cloud Run
  deployment once you complete the steps in [ADR-016](docs/adr/ADR-016-gcloud-client-setup.md).

The `pyproject.toml` declares optional extras—mix and match via
`pip install -e .[api]`, `.[worker]`, `.[cloud]`, `.[render]`, `.[color]`, or
`.[slides]` if you only need a subset of the runtime stack.

## Project Layout

Production code lives under `src/svg2ooxml/`:

- `common/` – shared helpers (temporary dirs, interpolation, timing).
- `core/` – converter entry points, pipeline orchestration, resvg integration.
- `drawingml/` – XML writers and asset registries.
- `io/` – SVG/PPTX adapters and file/stream helpers.
- `policy/` – tunable decisions and provider registries.
- `api/` and `services/` – REST API, background services, and integrations.
- `legacy/` – svg2pptx packages kept reachable during the migration; compatibility
  shims expose them under their historic import paths. See `docs/porting.md` for
  the remaining relocation plan.

Supporting folders:

- `docs/` – living architecture notes, structure guidelines, porting log.
- `tests/` – mirrors the package layout with `unit`, `integration`, and `visual`
  tiers (see `pytest.ini` markers).
- `assets/`, `testing/`, `reports/` – fixtures, temporary outputs, generated
  artefacts.
- `tools/` – helper scripts (e.g., color palette reports).

For a deeper dive, read `docs/structure.md`, `docs/testing.md`, and the ADRs in
`docs/adr/`.

## Visual Review

- Start the browser viewer with `svg2ooxml visual` (or `python -m tools.visual.server`).
- Pick an SVG fixture or provide a local path; the app renders the source SVG
  alongside LibreOffice screenshots of the generated PPTX.
- Install LibreOffice to enable PPTX → PNG rendering. The viewer auto-detects
  `/Applications/LibreOffice.app/Contents/MacOS/soffice` on macOS; use
  `SVG2OOXML_SOFFICE_PATH` for custom installs.

## Contributing

1. Create a feature branch and keep commits bisectable.
2. Run `pre-commit run --all-files` and `pytest` before pushing.
3. Update documentation (`docs/`, `README.md`, `docs/porting.md`) when moving or
   renaming modules.
4. Open a PR with the problem statement, approach, validation steps, and any
   follow-up tasks or assets (PPTX diffs, coverage reports, etc.).

Please capture outstanding migration work in `docs/porting.md` so the port stays
coordinated across modules.
