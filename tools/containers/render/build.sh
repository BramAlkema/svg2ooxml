#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
IMAGE_NAME=${SVG2OOXML_RENDER_IMAGE:-svg2ooxml-render:dev}
DOCKERFILE_PATH=${SVG2OOXML_RENDER_DOCKERFILE:-"$ROOT_DIR/Dockerfile"}

exec docker build \
  -f "$DOCKERFILE_PATH" \
  -t "$IMAGE_NAME" \
  "$ROOT_DIR"
