# File Structure Overview

The repository is now organised around the svg2ooxml runtime layers; the
`legacy/` namespace has been retired after the svg2pptx port.

```
src/
  svg2ooxml/
    __init__.py          # public entry points + version helper
    common/              # cross-cutting helpers (time, interpolation, temp dirs)
    core/                # SvgToPptxExporter, traversal, tracing, resvg integration
    drawingml/           # OOXML writers + asset registries
    export/              # public frame conversion helpers
    io/                  # SVG/PPTX adapters and storage abstractions
    policy/              # tunable decisions and policy providers
    services/            # long-lived service wiring (fonts, gradients, etc.)
  figma2gslides/
    app.py               # FastAPI entry point for the extracted app layer
    api/                 # app routes, middleware, publishing, testing helpers
    auth/                # Google OAuth / Drive helpers for the app layer
```

Folders outside `src/` remain unchanged:

- `cli/`, `examples/`, `tools/` – developer entry points and helper scripts.
-   `tools/visual/server.py` and `tools/visual/w3c_suite.py` power manual and
    batch visual comparisons (LibreOffice, Google Slides). See `docs/testing.md`
    for usage.
- `tests/` – mirrors the production layout; use markers (`unit`, `integration`,
  `visual`, `slow`) to scope runs.
- `docs/` – living documentation. Start with the
  [documentation guide](README.md), then use `adr/`, `internals/`, `specs/`,
  `tasks/`, `reference/`, and `notes/` by intent.
- `apps/figma2gslides/` – extracted Figma/Slides product surface and plugin
  assets, app-owned docs, and hosted legal pages.
- `docs/ROADMAP.md` – project status snapshot and near-term priorities.
- `assets/`, `testing/`, `reports/` – fixtures, golden outputs, and generated
  artefacts.

Keep modules small; split by behaviour only when a file grows beyond a handful
of focused functions. Update this document whenever modules move between the
core packages and the legacy namespace so contributors always know where logic
lives.
