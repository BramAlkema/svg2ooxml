#!/usr/bin/env bash

# Ensure a project virtual environment exists and has the local developer extras.
# Usage: ./tools/bootstrap_venv.sh [--force] [--doctor]

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./tools/bootstrap_venv.sh [--force] [--doctor]

Options:
  --force   Recreate VENV_DIR when it targets a different Python minor version.
  --doctor  Report interpreter/module health and warn about stray side envs.

Environment:
  PYTHON_BIN       Preferred interpreter (default: python3.14)
  VENV_DIR         Virtualenv directory (default: .venv)
  INSTALL_EXTRAS   Editable extras to install (default: dev,render,color,slides,api,cloud,visual-testing)
EOF
}

if [[ -n "${PYTHON_BIN:-}" ]]; then
    PYTHON_BIN=${PYTHON_BIN}
elif command -v python3.14 >/dev/null 2>&1; then
    PYTHON_BIN=python3.14
elif command -v python3 >/dev/null 2>&1 && [[ "$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)" == "3.14" ]]; then
    PYTHON_BIN=python3
else
    echo "ERROR: Python 3.14 is required for the canonical local .venv." >&2
    echo "Install python3.14 or set PYTHON_BIN to a specific 3.14 interpreter." >&2
    exit 1
fi
VENV_DIR=${VENV_DIR:-.venv}
INSTALL_EXTRAS=${INSTALL_EXTRAS:-dev,render,color,slides,api,cloud,visual-testing}
FORCE=0
DOCTOR=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)
            FORCE=1
            ;;
        --doctor)
            DOCTOR=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
    shift
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "ERROR: $PYTHON_BIN is not available on PATH." >&2
    echo "Install Python 3.14 or set PYTHON_BIN to the desired interpreter." >&2
    exit 1
fi

EXPECTED_VERSION=$("$PYTHON_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)

list_extra_envs() {
    find . -maxdepth 1 -type d \
        \( -name '.venv-*' -o -name '.venv_*' -o -name '.venv[0-9]*' -o -name 'venv' -o -name 'ENV' \) \
        -print | sort
}

verify_venv_python() {
    local cfg="$1/pyvenv.cfg"
    if [[ ! -f "$cfg" ]]; then
        return 1
    fi
    local version
    version=$(grep -E '^version = ' "$cfg" | awk '{print $3}')
    [[ "$version" == "$EXPECTED_VERSION".* ]]
}

module_status() {
    local module_name="$1"
    "$VENV_DIR/bin/python" - "$module_name" <<'PY'
import importlib
import importlib.util
import sys

module_name = sys.argv[1]
spec = importlib.util.find_spec(module_name)
if spec is None:
    print(f"{module_name}: unavailable")
    raise SystemExit(0)

module = importlib.import_module(module_name)
version = getattr(module, "__version__", "unknown")
origin = getattr(spec, "origin", "built-in")
print(f"{module_name}: available ({version}) @ {origin}")
PY
}

print_summary() {
    local runtime_python
    local runtime_version
    local site_packages

    runtime_python=$("$VENV_DIR/bin/python" - <<'PY'
import sys
print(sys.executable)
PY
)
    runtime_version=$("$VENV_DIR/bin/python" - <<'PY'
import sys
print(sys.version.split()[0])
PY
)
    site_packages=$("$VENV_DIR/bin/python" - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)

    cat <<EOF

Virtualenv ready at $VENV_DIR.
Activate with:
  source $VENV_DIR/bin/activate

Interpreter: $runtime_version via $runtime_python
Site-packages: $site_packages
Extras: ${INSTALL_EXTRAS:-<none>}
$(module_status fontforge)
$(module_status skia)
EOF

    if extra_envs=$(list_extra_envs) && [[ -n "$extra_envs" ]]; then
        cat <<EOF

Stray side environments detected:
$extra_envs

Keep one canonical .venv for daily work. Side envs are left untouched.
EOF
    fi
}

if [[ "$DOCTOR" -eq 1 ]]; then
    echo "ℹ Doctoring $VENV_DIR"
    echo "Interpreter preference: $PYTHON_BIN (Python $EXPECTED_VERSION)"
    if [[ ! -d "$VENV_DIR" ]]; then
        echo "ERROR: $VENV_DIR does not exist." >&2
        exit 1
    fi
    if ! verify_venv_python "$VENV_DIR"; then
        echo "ERROR: $VENV_DIR exists but is not a Python $EXPECTED_VERSION environment." >&2
        exit 1
    fi
    print_summary
    exit 0
fi

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
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel

if [[ -n "$INSTALL_EXTRAS" ]]; then
    echo "ℹ Installing svg2ooxml with local developer extras: [$INSTALL_EXTRAS]"
    "$VENV_DIR/bin/pip" install -e ".[${INSTALL_EXTRAS}]"
else
    echo "ℹ Installing svg2ooxml without optional extras"
    "$VENV_DIR/bin/pip" install -e .
fi

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

print_summary
