#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [[ $# -eq 0 ]]; then
  set -- \
    tests/unit/render/test_pipeline.py \
    tests/unit/drawingml/test_writer_raster.py \
    tests/integration/core/test_pipeline.py \
    tests/integration/test_filter_raster_pipeline.py
fi

exec "$SCRIPT_DIR/run.sh" pytest "$@"
