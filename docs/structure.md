# File Structure Overview

The repository is now organised around the svg2ooxml runtime layers plus a
`legacy/` namespace that keeps svg2pptx-era modules reachable while the port is
in flight.

```
src/
  svg2ooxml/
    __init__.py          # public entry points + version helper
    _legacy.py           # helper used by compatibility shims
    common/              # cross-cutting helpers (time, interpolation, temp dirs)
    core/                # orchestration, pipeline, tracing, resvg integration
    drawingml/           # OOXML writers + asset registries
    io/                  # SVG/PPTX adapters and storage abstractions
    policy/              # tunable decisions and policy providers
    api/                 # HTTP layer, request/response models, services
    services/            # long-lived service wiring (fonts, gradients, etc.)
    legacy/              # svg2pptx packages parked until they are ported
      animations/
      batch/
      clip/
      clipmask/
      color/
      compat/
      css/
      elements/
      filters/
      fonts/
      geometry/
      ir/
      map/
      multipage/
      paint/
      parser/
      performance/
      pipeline/
      preprocessing/
      presentation/
      render/
      text/
      transforms/
      units/
      viewbox/
```

Compatibility wrappers live at `svg2ooxml/<package>/__init__.py` and simply
delegate to the `legacy` tree so existing imports (and tests) continue to run.
Actively ported modules should be promoted out of `legacy/` once refactored,
with the move recorded in `docs/porting.md`.

Folders outside `src/` remain unchanged:

- `cli/`, `examples/`, `tools/` – developer entry points and helper scripts.
-   `tools/visual/server.py` and `tools/visual/w3c_suite.py` power manual and
    batch visual comparisons (LibreOffice, Google Slides). See `docs/testing.md`
    for usage.
- `tests/` – mirrors the production layout; use markers (`unit`, `integration`,
  `visual`, `slow`) to scope runs.
- `docs/` – living documentation, architecture notes, and migration plans. The
  new [ADR-016](docs/adr/ADR-016-gcloud-client-setup.md) describes the gcloud
  configuration needed to interact with the Cloud Run export service described
  in ADR-014.
- `assets/`, `testing/`, `reports/` – fixtures, golden outputs, and generated
  artefacts.

Keep modules small; split by behaviour only when a file grows beyond a handful
of focused functions. Update this document whenever modules move between the
core packages and the legacy namespace so contributors always know where logic
lives.
