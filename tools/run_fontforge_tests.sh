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

spec = importlib.util.find_spec("fontforge")
if spec is None:
    raise SystemExit(f"fontforge unavailable in {sys.executable}")
print(f"fontforge ok: {spec.origin}")
PY

pytest \
  tests/unit/services/fonts/test_fontforge_utils.py \
  tests/unit/services/fonts/test_font_loader.py \
  tests/unit/services/fonts/test_eot.py
