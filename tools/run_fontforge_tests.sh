#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate
python -c "import fontforge; print('fontforge ok')"
pytest tests/unit/services/fonts/test_font_loader.py tests/unit/services/fonts/test_eot.py
