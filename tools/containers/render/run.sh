#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
IMAGE_NAME=${SVG2OOXML_RENDER_IMAGE:-svg2ooxml-render:dev}
REPORTS_DIR=${SVG2OOXML_REPORTS_DIR:-"$ROOT_DIR/reports"}
W3C_OUTPUT_DIR=${SVG2OOXML_W3C_OUTPUT_DIR:-"$ROOT_DIR/tests/corpus/w3c/output"}
FONT_CACHE_DIR=${SVG2OOXML_FONT_CACHE_DIR:-"$ROOT_DIR/.cache/svg2ooxml/fonts"}
TMP_DIR=${SVG2OOXML_CONTAINER_TMP_DIR:-"$ROOT_DIR/tmp/container"}

mkdir -p "$REPORTS_DIR" "$W3C_OUTPUT_DIR" "$FONT_CACHE_DIR" "$TMP_DIR"

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  "$(dirname "${BASH_SOURCE[0]}")/build.sh"
fi

docker_flags=(--rm -v "$ROOT_DIR:/workspace" -v "$REPORTS_DIR:/workspace/reports")
docker_flags+=(-v "$W3C_OUTPUT_DIR:/workspace/tests/corpus/w3c/output")
docker_flags+=(-v "$FONT_CACHE_DIR:/var/cache/svg2ooxml/fonts")
docker_flags+=(-v "$TMP_DIR:/var/tmp/svg2ooxml")
docker_flags+=(-w /workspace)

if [[ -t 0 && -t 1 ]]; then
  docker_flags+=(-it)
fi

if [[ $# -eq 0 ]]; then
  set -- /bin/bash
fi

exec docker run "${docker_flags[@]}" "$IMAGE_NAME" "$@"
