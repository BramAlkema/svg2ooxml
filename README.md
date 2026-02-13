# svg2ooxml

> **Note (2026-01-16):** GCP project `powerful-layout-467812-p1` was deleted to stop billing charges. The Cloud Run service is no longer available. Can be restored within 30 days via `gcloud projects undelete powerful-layout-467812-p1`.

SVG → Office Open XML conversion toolkit (requires Python 3.13+). The project is an evolution of the
internal svg2pptx converter and is being rebuilt around a small, well-typed
core that can run locally without GCP dependencies.

- **Exporter + services** – ``SvgToPptxExporter`` drives parsing, IR mapping, and
  PPTX packaging through the service graph.
- **DrawingML writers** – generate PPTX/Slides artefacts (currently stubs).
- **API surface** – FastAPI entry points with optional Firestore/Storage backends.

## Getting Started

```bash
./tools/bootstrap_venv.sh
source .venv/bin/activate
```

## Docker (Orbstack)

On macOS, Homebrew's FontForge Python bindings are only available for Python 3.14,
while Skia requires Python 3.13. Use the Orbstack container for a full stack
(FontForge + Skia) environment.

Build the container image:

```bash
docker build -f Dockerfile.orbstack -t svg2ooxml-orb .
```

Run with persistent caches and outputs:

```bash
docker run --rm -it \
  -v "$(pwd)":/workspace \
  -v "$(pwd)/../openxml-audit":/workspace/openxml-audit \
  -v svg2ooxml-cache:/var/cache/svg2ooxml \
  -v "$(pwd)/reports":/workspace/reports \
  -v "$(pwd)/tests/corpus/w3c/output":/workspace/tests/corpus/w3c/output \
  svg2ooxml-orb
```

Cache/output directories are preconfigured at `/var/cache/svg2ooxml`, `/var/tmp/svg2ooxml`,
`/workspace/reports`, and `/workspace/tests/corpus/w3c/output`.
Mounting `../openxml-audit` makes the container auto-install `openxml-audit` at startup.

The developer requirements install svg2ooxml in editable mode with the full
runtime extras (API, cloud, render, color, slides, payments, visual-testing)
plus linting and test tooling. For leaner installs, use:

- `requirements.txt` for the Cloud Run API tier (same as `requirements-api.txt`).
- `requirements-core.txt` for the core converter only.
- `requirements-api.txt` for the API tier (no render stack).
- `requirements-render.txt` for render/visual tooling.
- `requirements-full.txt` for the complete stack.

## Local Development

For local development, you'll need to run two processes: the FastAPI server and the Huey worker.

**Running the FastAPI server:**

```bash
uvicorn main:app --reload
```

**Running the Huey worker:**

```bash
python cli/run_worker.py
```

The Huey worker is used for background tasks in the local development environment. For the production environment on Google Cloud, background tasks are handled by Google Cloud Tasks.

### Call the Cloud Run export API

Once you have authenticated with `gcloud` (see
[`ADR-016`](docs/adr/ADR-016-gcloud-client-setup.md)), you can exercise the live
service directly. The example below posts the W3C `struct-use-10-f` fixture and
requests a Google Slides deck. For a full local setup (FastAPI + real Firestore +
Drive) see [`docs/local-api-testing.md`](docs/local-api-testing.md).

```bash
TOKEN=$(gcloud auth print-identity-token)
SERVICE_URL=https://svg2ooxml-export-sghya3t5ya-ew.a.run.app

python - <<'PY' > payload.json
import json
from pathlib import Path

payload = {
    "frames": [
        {
            "name": "struct-use-10-f",
            "svg_content": Path("tests/svg/struct-use-10-f.svg").read_text(),
            "width": 480,
            "height": 360,
        }
    ],
    "figma_file_id": "w3c-struct-use-10-f",
    "figma_file_name": "W3C struct use",
    "output_format": "slides",
}
print(json.dumps(payload))
PY

curl -sS -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @payload.json \
  "$SERVICE_URL/api/v1/export"

JOB_ID=...
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$SERVICE_URL/api/v1/export/$JOB_ID" | jq
```

The status payload now includes `pptx_url`, `slides_url`, `slides_embed_url`,
and `slides_presentation_id` when the Slides promotion succeeds.

## Development Workflow

- `ruff check src tests` – quick lint pass (mirrors the pre-commit hook).
- `black src tests` – formatting helper (the repo uses Black's 88-column style).
- `pytest` – runs the default suite; coverage and HTML reports land in `reports/`.
- `pytest -m "unit and not slow"` – tight loop for fast checks.
- `pytest -m smoke tests/smoke/` – end-to-end tests against the deployed Cloud Run service (see `tests/smoke/README.md` for authentication setup).
- `python tools/check_file_sizes.py` – track large Python files against maintainability guardrails.
- `pre-commit install` – enable lint/type/security hooks before committing.
- `svg2ooxml visual` – launch the local side-by-side visual comparison server
  (requires LibreOffice's `soffice` binary for PPTX screenshots).
- `python -m tools.visual.w3c_suite` – build and render the curated W3C SVG
  fixtures; optionally compare against baselines once LibreOffice is
  configured.
- `gcloud auth login && gcloud run services list` – interact with the Cloud Run
  deployment once you complete the steps in [ADR-016](docs/adr/ADR-016-gcloud-client-setup.md).

The `pyproject.toml` declares optional extras—mix and match via
`pip install -e .[api]`, `.[cloud]`, `.[render]`, `.[color]`, `.[slides]`,
`.[payments]`, or `.[visual-testing]` if you only need a subset of the runtime
stack.

## Project Layout

Production code lives under `src/svg2ooxml/`:

- `common/` – shared helpers (temporary dirs, interpolation, timing).
- `core/` – converter entry points (including ``SvgToPptxExporter``), traversal,
  resvg integration, and the metadata describing the pipeline stages.
- `drawingml/` – XML writers and asset registries.
- `io/` – SVG/PPTX adapters and file/stream helpers.
- `policy/` – tunable decisions and provider registries.
- `api/` and `services/` – REST API, background services, and integrations.
  shims used during the migration have now been removed; see `docs/legacyport.md`
  for the historical port log.

Supporting folders:

- `docs/` – living architecture notes, structure guidelines, porting log.
- `tests/` – mirrors the package layout with `unit`, `integration`, and `visual`
  tiers (see `pytest.ini` markers).
- `assets/`, `testing/`, `reports/` – fixtures, temporary outputs, generated
  artefacts.
- `tools/` – helper scripts (e.g., color palette reports).

For a deeper dive, read `docs/structure.md`, `docs/testing.md`, and the ADRs in
`docs/adr/`.

Project status and priorities live in `docs/ROADMAP.md`.

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
