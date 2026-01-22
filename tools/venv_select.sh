#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: source tools/venv_select.sh [311|314]" >&2
}

if [[ ${#} -ne 1 ]]; then
  usage
  return 2 2>/dev/null || exit 2
fi

case "$1" in
  311)
    source .venv311/bin/activate
    ;;
  314)
    source .venv/bin/activate
    ;;
  *)
    usage
    return 2 2>/dev/null || exit 2
    ;;
esac

python -c "import sys; print(sys.executable)"
