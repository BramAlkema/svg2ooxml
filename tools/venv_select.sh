#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF' >&2
usage: source tools/venv_select.sh [default|<venv-path>]

default  -> .venv
EOF
}

if [[ ${#} -gt 1 ]]; then
  usage
  return 2 2>/dev/null || exit 2
fi

target="${1:-default}"

case "$target" in
  default|current)
    target=".venv"
    ;;
  ./*|/*)
    ;;
  .venv*)
    ;;
  *)
    usage
    return 2 2>/dev/null || exit 2
    ;;
esac

if [[ ! -f "$target/bin/activate" ]]; then
  echo "error: virtualenv not found at $target" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1090
source "$target/bin/activate"
python - <<'PY'
import sys
print(sys.executable)
print(sys.version.split()[0])
PY
