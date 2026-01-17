# Testing Guide

The automated suite is split into tiers so developers and CI can opt into the
right amount of coverage for a change. All markers are declared in
`pyproject.toml` and enforced via the `conftest.py` files under `tests/`.

## Markers

- `unit` – fast checks covering individual modules. Triggered automatically for
  every module inside `tests/unit/`.
- `integration` – cross-module flows that may touch the filesystem or external
  processes. All tests in `tests/integration/` receive this mark.
- `visual` – screenshot and PPTX comparison tests. They require the rendering
  extra (`pip install -e .[render]`) plus the golden baselines in
  `tests/visual/golden/`.
- `slow` – long-running scenarios. Presently unused but available for future
  regression suites.

Run specific tiers with:

```bash
pytest -m unit            # default fast loop
pytest -m integration     # heavier cross-module checks
pytest -m visual          # visual regression runs (opt-in)
```

Visual tests generate artefacts in `reports/visual/` and rely on Skia bindings
(`skia-python`) to produce bitmap diffs. Update baselines via the helper script
in `tools/` and capture before/after screenshots in the PR description.

For manual spot checks, launch the local visual viewer:

```bash
svg2ooxml visual  # or python -m tools.visual.server
```

Pick an SVG fixture or provide a file path to compare the raw markup with
LibreOffice-rendered PPTX slides side-by-side in the browser. Install
LibreOffice (`soffice`); the viewer auto-detects the standard macOS bundle path
(`/Applications/LibreOffice.app/Contents/MacOS/soffice`). Use
`SVG2OOXML_SOFFICE_PATH` for custom installs or Linux distributions. If headless
LibreOffice fails on macOS (exit code 1 or 134), set
`SVG2OOXML_SOFFICE_USER_INSTALL` to a writable directory (e.g. `/tmp/lo_profile`)
or pass `--soffice-profile` when running the visual tools.

The W3C sanity suite wraps the same tooling for a fixed list of fixtures:

```bash
python -m tools.visual.w3c_suite  # renders to reports/visual/w3c
```

Provide scenario names (e.g. `python -m tools.visual.w3c_suite struct-use-10-f`)
to focus on specific files. The script renders each SVG, drops artefacts to the
output directory, and—when baselines exist under `tests/visual/golden/w3c/`—runs
pixel diffs. To forward scenarios to the Cloud Run export API while rendering,
append:

```bash
python -m tools.visual.w3c_suite \
  --export-service-url "https://svg2ooxml-export-…run.app" \
  --auth-token "$(gcloud auth print-identity-token)"
```

Each scenario posts its SVG payload with the chosen `--export-format` (default
`slides`) and logs the job ID returned by the service.

CI jobs should keep visual tests in a dedicated stage so we can fan them out or
gate them on render-specific dependencies.
