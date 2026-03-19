#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "Python not found. Set PYTHON_BIN or install python3." >&2
    exit 1
  fi
fi

DEFAULT_OPENXML_VALIDATOR="$PROJECT_ROOT/tools/openxml-audit"
if command -v openxml-audit >/dev/null 2>&1; then
  DEFAULT_OPENXML_VALIDATOR="openxml-audit"
fi

OPENXML_VALIDATOR_PATH="${OPENXML_VALIDATOR:-$DEFAULT_OPENXML_VALIDATOR}"
if [[ "$OPENXML_VALIDATOR_PATH" != "openxml-audit" && ! -e "$OPENXML_VALIDATOR_PATH" ]]; then
  echo "OpenXML validator not found: $OPENXML_VALIDATOR_PATH" >&2
  echo "Install 'openxml-audit' or set OPENXML_VALIDATOR to a valid validator path." >&2
  exit 1
fi
export OPENXML_VALIDATOR="$OPENXML_VALIDATOR_PATH"

MODE="${1:-required}"
if [[ "$MODE" != "required" && "$MODE" != "full" && "$MODE" != "all" ]]; then
  echo "Usage: $0 [required|full|all]" >&2
  exit 1
fi

run_required() {
  "$PYTHON_BIN" "$PROJECT_ROOT/tests/corpus/add_w3c_corpus.py" \
    --category pservers-grad \
    --limit 25 \
    --output "$PROJECT_ROOT/tests/corpus/w3c/w3c_gradients_metadata.json"

  "$PYTHON_BIN" "$PROJECT_ROOT/tests/corpus/run_corpus.py" \
    --corpus-dir "$PROJECT_ROOT/tests/svg" \
    --metadata "$PROJECT_ROOT/tests/corpus/w3c/w3c_gradients_metadata.json" \
    --output-dir "$PROJECT_ROOT/tests/corpus/w3c/output_gradients" \
    --report "$PROJECT_ROOT/tests/corpus/w3c/report_gradients.json" \
    --mode resvg \
    --openxml-audit \
    --openxml-required \
    --openxml-min-pass-rate 0.98

  "$PYTHON_BIN" "$PROJECT_ROOT/tests/corpus/add_w3c_corpus.py" \
    --category shapes \
    --limit 30 \
    --output "$PROJECT_ROOT/tests/corpus/w3c/w3c_shapes_metadata.json"

  "$PYTHON_BIN" "$PROJECT_ROOT/tests/corpus/run_corpus.py" \
    --corpus-dir "$PROJECT_ROOT/tests/svg" \
    --metadata "$PROJECT_ROOT/tests/corpus/w3c/w3c_shapes_metadata.json" \
    --output-dir "$PROJECT_ROOT/tests/corpus/w3c/output_shapes" \
    --report "$PROJECT_ROOT/tests/corpus/w3c/report_shapes.json" \
    --mode resvg \
    --openxml-audit \
    --openxml-required \
    --openxml-min-pass-rate 0.98

  "$PYTHON_BIN" "$PROJECT_ROOT/tests/corpus/add_w3c_corpus.py" \
    --category animate \
    --limit 40 \
    --output "$PROJECT_ROOT/tests/corpus/w3c/w3c_animation_metadata.json"

  "$PYTHON_BIN" "$PROJECT_ROOT/tests/corpus/run_corpus.py" \
    --corpus-dir "$PROJECT_ROOT/tests/svg" \
    --metadata "$PROJECT_ROOT/tests/corpus/w3c/w3c_animation_metadata.json" \
    --output-dir "$PROJECT_ROOT/tests/corpus/w3c/output_animation" \
    --report "$PROJECT_ROOT/tests/corpus/w3c/report_animation.json" \
    --mode resvg \
    --sample-size 20 \
    --sample-seed 20260221 \
    --openxml-audit \
    --openxml-required \
    --openxml-min-pass-rate 0.98
}

run_full() {
  "$PYTHON_BIN" "$PROJECT_ROOT/tests/corpus/add_w3c_corpus.py" \
    --category animate \
    --limit 40 \
    --output "$PROJECT_ROOT/tests/corpus/w3c/w3c_animation_metadata.json"

  "$PYTHON_BIN" "$PROJECT_ROOT/tests/corpus/run_corpus.py" \
    --corpus-dir "$PROJECT_ROOT/tests/svg" \
    --metadata "$PROJECT_ROOT/tests/corpus/w3c/w3c_animation_metadata.json" \
    --output-dir "$PROJECT_ROOT/tests/corpus/w3c/output_animation_full" \
    --report "$PROJECT_ROOT/tests/corpus/w3c/report_animation_full.json" \
    --mode resvg \
    --sample-size 40 \
    --sample-seed 20260221 \
    --openxml-audit \
    --openxml-required \
    --openxml-min-pass-rate 0.98
}

case "$MODE" in
  required)
    run_required
    ;;
  full)
    run_full
    ;;
  all)
    run_required
    run_full
    ;;
esac

echo "W3C animation gate run completed ($MODE)."
