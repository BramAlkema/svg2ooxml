#!/usr/bin/env bash
set -euo pipefail

source .venv311/bin/activate
python -c "import skia; print('skia ok')"
pytest tests/visual/test_resvg_visual.py tests/visual/test_svg_render.py
