# Contributing to svg2ooxml

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/BramAlkema/svg2ooxml.git
cd svg2ooxml
./tools/bootstrap_venv.sh
source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
```

## Making Changes

1. **Create a feature branch** from `main`.
2. **Write tests** — unit tests go in `tests/unit/`, integration tests in `tests/integration/`.
3. **Run the checks** before pushing:
   ```bash
   ruff check src tests
   black src tests
   pytest
   ```
4. **Keep commits bisectable** — each commit should build and pass tests.

## Pull Request Process

1. Open a PR against `main` with a clear description of the change.
2. Include the problem statement, approach, and validation steps.
3. Ensure CI passes — the pre-commit hooks run linting and type checks.
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

See [CLAUDE.md](CLAUDE.md) for a full architecture overview and module guide. Key ADRs in `docs/adr/` document important design decisions.

## Licensing

- Source code: AGPL-3.0-only
- Add SPDX headers to new files (see `docs/licensing.md`)

## Questions?

Open an issue or start a discussion — we're happy to help.
