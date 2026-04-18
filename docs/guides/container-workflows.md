# Container Workflows

Use the local [`.venv`](../../.python-version) for day-to-day editing and fast
checks. Use the Docker render lane when you need a reproducible Linux
environment with Python 3.14 parity, raster dependencies, and stable output
directories.

OrbStack does not need a separate image definition. If Docker commands in this
repo are running on OrbStack, use the same render wrappers documented here.

## Roles

- Local `.venv`
  - Python 3.14
  - fastest loop for coding, linting, and most unit tests
  - Homebrew-backed `fontforge` on macOS
- Docker render lane
  - Python 3.14 inside the container too
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

- it preserves Python 3.14 parity with the local `.venv`
- it avoids relying on Debian's older `python3-fontforge` package
- it avoids claiming a public `pip install fontforge` release path before the
  upstream PyPI publication is actually in place

The image applies a one-line CMake adjustment before building because the
current upstream wheel configuration asks CMake for `Development.Module` but
later links against `Python3::Python`. Once upstream lands a fix and publishes
wheels, that workaround can go away.
