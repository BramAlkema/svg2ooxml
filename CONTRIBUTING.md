# Contributing to svg2ooxml

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/BramAlkema/svg2ooxml.git
cd svg2ooxml
./tools/bootstrap_venv.sh
source .venv/bin/activate
pre-commit install
```

`./tools/bootstrap_venv.sh` is the canonical local setup entrypoint. It creates
`.venv`, installs the default editable extras, links Homebrew `fontforge` on
macOS when available, supports `--doctor` for a quick health check, and assumes
Python 3.14 for the standard local environment.

For reproducible Linux rendering and font/raster checks with Python 3.14 parity,
use the Docker render lane documented in
[`docs/guides/container-workflows.md`](docs/guides/container-workflows.md).

## Making Changes

1. **Create a feature branch** from `main`.
2. **Write tests** — unit tests go in `tests/unit/`, integration tests in `tests/integration/`.
3. **Run the checks** before pushing:
   ```bash
   pre-commit run --all-files
   ruff check src tests
   black src tests
   pytest
   ```
4. **Keep commits bisectable** — each commit should build and pass tests.

## Pull Request Process

1. Open a PR against `main` with a clear description of the change.
2. Include the problem statement, approach, and validation steps.
3. Ensure CI passes — the pre-commit hooks run shared formatting and linting checks.
4. Add or update tests for any new functionality.

## Code Style

- **Python 3.13+** — use modern syntax (type unions, `match`, etc.)
- **Black** formatting with 88-column lines
- **Ruff** for linting (mirrors pre-commit hooks)
- **Frozen dataclasses** (`@dataclass(frozen=True, slots=True)`) for value objects

## Test Tiers

| Marker | Purpose | Speed |
|--------|---------|-------|
| `unit` | Isolated logic tests | Fast |
| `integration` | Cross-module, may touch IO | Medium |
| `visual` | PPTX rendering comparison (needs LibreOffice) | Slow |

Run specific tiers:
```bash
pytest -m unit                    # fast
pytest -m integration             # medium
pytest -m visual                  # slow, needs LibreOffice
```

## Architecture

Start with [docs/README.md](docs/README.md) for the documentation map. Key ADRs in `docs/adr/` and implementation notes under `docs/internals/` document important design decisions.

## Licensing

- Source code: AGPL-3.0-only
- Add SPDX headers to new files (see `docs/licensing.md`)

## Questions?

Open an issue or start a discussion — we're happy to help.
