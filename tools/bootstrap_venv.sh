#!/usr/bin/env bash

# Ensure a project virtual environment exists and has the local developer extras.
# Usage: ./tools/bootstrap_venv.sh [--force]

set -euo pipefail

if [[ -n "${PYTHON_BIN:-}" ]]; then
    PYTHON_BIN=${PYTHON_BIN}
elif command -v python3.14 >/dev/null 2>&1; then
    PYTHON_BIN=python3.14
elif command -v python3.13 >/dev/null 2>&1; then
    PYTHON_BIN=python3.13
else
    PYTHON_BIN=python3
fi
VENV_DIR=${VENV_DIR:-.venv}
INSTALL_EXTRAS=${INSTALL_EXTRAS:-dev,render,color,slides,api,cloud,visual-testing}
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
    echo "Install Python 3.14/3.13 or set PYTHON_BIN to the desired interpreter." >&2
    exit 1
fi

EXPECTED_VERSION=$("$PYTHON_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)

verify_venv_python() {
    local cfg="$1/pyvenv.cfg"
    if [[ ! -f "$cfg" ]]; then
        return 1
    fi
    local version
    version=$(grep -E '^version = ' "$cfg" | awk '{print $3}')
    [[ "$version" == "$EXPECTED_VERSION".* ]]
}

if [[ -d "$VENV_DIR" ]]; then
    if verify_venv_python "$VENV_DIR"; then
        echo "✔ Using existing Python $EXPECTED_VERSION virtualenv at $VENV_DIR"
    else
        if [[ "$FORCE" -eq 1 ]]; then
            echo "ℹ Removing $VENV_DIR (not a Python $EXPECTED_VERSION environment)"
            rm -rf "$VENV_DIR"
        else
            echo "ERROR: $VENV_DIR exists but is not a Python $EXPECTED_VERSION environment." >&2
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

echo "ℹ Installing svg2ooxml with local developer extras: [$INSTALL_EXTRAS]"
"$VENV_DIR/bin/pip" install -e ".[${INSTALL_EXTRAS}]" >/dev/null

SITE_PACKAGES=$("$VENV_DIR/bin/python" - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)

if ! "$VENV_DIR/bin/python" -c "import fontforge" >/dev/null 2>&1; then
    HOMEBREW_FONTFORGE_SITE="/opt/homebrew/lib/python${EXPECTED_VERSION}/site-packages"
    if [[ -d "$HOMEBREW_FONTFORGE_SITE" ]]; then
        printf '%s\n' "$HOMEBREW_FONTFORGE_SITE" > "$SITE_PACKAGES/homebrew-fontforge.pth"
        echo "ℹ Linked Homebrew FontForge bindings from $HOMEBREW_FONTFORGE_SITE"
    fi
fi

FONTFORGE_STATUS="unavailable"
if "$VENV_DIR/bin/python" -c "import fontforge" >/dev/null 2>&1; then
    FONTFORGE_STATUS="available"
fi

SKIA_STATUS="unavailable"
if "$VENV_DIR/bin/python" -c "import skia" >/dev/null 2>&1; then
    SKIA_STATUS="available"
fi

cat <<EOF

Virtualenv ready at $VENV_DIR.
Activate with:
  source $VENV_DIR/bin/activate

Reminder: use $VENV_DIR/bin/python and $VENV_DIR/bin/pytest for local work.
Interpreter: Python $EXPECTED_VERSION via $PYTHON_BIN
FontForge bindings: $FONTFORGE_STATUS
Skia bindings: $SKIA_STATUS

Tip: set PYTHON_BIN, INSTALL_EXTRAS, or VENV_DIR before running to customise the setup.
EOF
