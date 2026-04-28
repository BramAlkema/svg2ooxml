# Container Workflows

Use the local [`.venv`](../../.python-version) for day-to-day editing and fast
checks. Use the Docker render lane when you need a reproducible Linux
environment with pinned FontForge/skia/NumPy dependencies and stable output
directories.

The wrappers require a Docker-compatible engine. Docker Desktop, OrbStack, and
compatible remote Docker contexts can all use the same image and commands.

## Roles

- Local `.venv`
  - supports the package's Python 3.13 floor
  - may use Python 3.14 for local render/font tooling when Homebrew
    `fontforge` bindings or `skia-python` require it
  - keeps NumPy optional for base installs; install `render`, `color`, or
    `accel` extras for NumPy-backed paths
  - fastest loop for coding, linting, and most unit tests
  - Homebrew-backed `fontforge` on macOS
- Docker render lane
  - matched interpreter/tooling environment for FontForge/skia render checks
  - official FontForge Python module built from a pinned upstream commit
  - reproducible Linux environment for raster/filter/font tests
  - stable mounts for reports and W3C output

## Commands

Build the image:

```bash
./tools/containers/render/build.sh
```

Open a shell in the container with the repository mounted at `/workspace`:

```bash
./tools/containers/render/run.sh
```

Run the default container smoke suite:

```bash
./tools/containers/render/pytest.sh
```

Run a custom command:

```bash
./tools/containers/render/run.sh python -c "import fontforge, skia; print('ok')"
./tools/containers/render/run.sh pytest tests/unit/services/fonts/test_eot.py
```

## Mounts

The wrapper keeps a few mutable paths outside the image:

- `reports/` -> `/workspace/reports`
- `tests/corpus/w3c/output/` -> `/workspace/tests/corpus/w3c/output`
- `.cache/svg2ooxml/fonts/` -> `/var/cache/svg2ooxml/fonts`
- `tmp/container/` -> `/var/tmp/svg2ooxml`

The Python environment lives inside the image at `/opt/svg2ooxml-venv`, so
bind-mounting the repo does not hide the installed dependencies.

## FontForge Source Pin

The Docker image currently builds FontForge from the upstream commit pinned in
[`Dockerfile`](../../Dockerfile). That is intentional:

- it preserves parity with the local FontForge/skia/NumPy tooling environment
- it avoids relying on Debian's older `python3-fontforge` package
- it avoids claiming a public `pip install fontforge` release path before the
  upstream PyPI publication is actually in place

The image applies a one-line CMake adjustment before building because the
current upstream wheel configuration asks CMake for `Development.Module` but
later links against `Python3::Python`. Once upstream lands a fix and publishes
wheels, that workaround can go away.
