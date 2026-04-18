#!/usr/bin/env bash
set -euo pipefail

VENV_DIR=${VENV_DIR:-.venv}

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "error: virtualenv not found at $VENV_DIR" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
python - <<'PY'
import importlib.util
import sys

spec = importlib.util.find_spec("skia")
if spec is None:
    raise SystemExit(f"skia unavailable in {sys.executable}")
print(f"skia ok: {spec.origin}")
PY

pytest \
  tests/unit/render/test_pipeline.py \
  tests/unit/drawingml/test_writer_raster.py \
  tests/integration/core/test_pipeline.py \
  tests/integration/test_filter_raster_pipeline.py
