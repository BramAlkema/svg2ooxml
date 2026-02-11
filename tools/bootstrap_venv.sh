#!/usr/bin/env bash

# Ensure a Python 3.13 virtual environment exists and has dev dependencies.
# Usage: ./tools/bootstrap_venv.sh [--force]

set -euo pipefail

PYTHON_BIN=${PYTHON_BIN:-python3.13}
VENV_DIR=${VENV_DIR:-.venv}
FORCE=0

for arg in "$@"; do
    case "$arg" in
        --force)
            FORCE=1
            shift
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: ./tools/bootstrap_venv.sh [--force]" >&2
            exit 1
            ;;
    esac
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "ERROR: $PYTHON_BIN is not available on PATH." >&2
    echo "Install Python 3.13 or set PYTHON_BIN to the desired interpreter." >&2
    exit 1
fi

verify_venv_python() {
    local cfg="$1/pyvenv.cfg"
    if [[ ! -f "$cfg" ]]; then
        return 1
    fi
    local version
    version=$(grep -E '^version = ' "$cfg" | awk '{print $3}')
    [[ "$version" == 3.13.* ]]
}

if [[ -d "$VENV_DIR" ]]; then
    if verify_venv_python "$VENV_DIR"; then
        echo "✔ Using existing Python 3.13 virtualenv at $VENV_DIR"
    else
        if [[ "$FORCE" -eq 1 ]]; then
            echo "ℹ Removing $VENV_DIR (not a Python 3.13 environment)"
            rm -rf "$VENV_DIR"
        else
            echo "ERROR: $VENV_DIR exists but is not a Python 3.13 environment." >&2
            echo "Re-run with --force or remove the directory manually." >&2
            exit 1
        fi
    fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
    echo "ℹ Creating virtualenv with $PYTHON_BIN → $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "ℹ Upgrading pip/setuptools"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null

echo "ℹ Installing requirements-dev.txt (editable svg2ooxml + dev deps)"
"$VENV_DIR/bin/pip" install -r requirements-dev.txt >/dev/null

cat <<EOF

Virtualenv ready at $VENV_DIR.
Activate with:
  source $VENV_DIR/bin/activate

Tip: set PYTHON_BIN or VENV_DIR before running to customise the interpreter or location.
EOF
