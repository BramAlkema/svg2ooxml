#!/usr/bin/env bash
set -euo pipefail

ensure_openxml_audit() {
    if command -v openxml-audit >/dev/null 2>&1; then
        return 0
    fi
    local repo="/workspace/openxml-audit"
    if [[ -f "$repo/pyproject.toml" || -f "$repo/setup.py" ]]; then
        python3 -m pip install -e "$repo" --break-system-packages \
            >/tmp/openxml_audit_install.log 2>&1 || {
            echo "WARN: openxml-audit install failed; see /tmp/openxml_audit_install.log" >&2
        }
    fi
}

ensure_openxml_audit
exec "$@"
