#!/usr/bin/env bash

set -euo pipefail

PROJECT_ID="powerful-layout-467812-p1"
SECRET_DIR="secrets/local"
ENV_FILE=".env.local"
SERVICE_ACCOUNT_JSON="$SECRET_DIR/firebase-service-account.json"
TOKEN_KEY_FILE="$SECRET_DIR/token-encryption-key.txt"
WEB_CLIENT_ID_FILE="$SECRET_DIR/firebase-web-client-id.txt"
WEB_CLIENT_SECRET_FILE="$SECRET_DIR/firebase-web-client-secret.txt"

log() {
  printf '[local-api] %s\n' "$*" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "Missing required command: $1"
    exit 1
  fi
}

fetch_secret() {
  local secret_name=$1
  local output_path=$2
  log "Fetching secret ${secret_name}"
  gcloud secrets versions access latest \
    --secret "${secret_name}" \
    --project "${PROJECT_ID}" \
    > "${output_path}"
}

write_env_file() {
  local token_key
  local web_client_id
  local web_client_secret

  token_key=$(tr -d '\r\n' < "${TOKEN_KEY_FILE}")
  web_client_id=$(tr -d '\r\n' < "${WEB_CLIENT_ID_FILE}")
  web_client_secret=$(tr -d '\r\n' < "${WEB_CLIENT_SECRET_FILE}")

  cat > "${ENV_FILE}" <<EOF
export ENVIRONMENT=development
export GCP_PROJECT=${PROJECT_ID}
export GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
export FIREBASE_PROJECT_ID=${PROJECT_ID}
export FIREBASE_SERVICE_ACCOUNT_PATH=${SERVICE_ACCOUNT_JSON}
export GOOGLE_APPLICATION_CREDENTIALS=${SERVICE_ACCOUNT_JSON}
export TOKEN_ENCRYPTION_KEY=${token_key}
export FIREBASE_WEB_CLIENT_ID=${web_client_id}
export FIREBASE_WEB_CLIENT_SECRET=${web_client_secret}
export SVG2OOXML_RATE_LIMIT=200
export SVG2OOXML_RATE_WINDOW=60
export DISABLE_EXPORT_QUOTA=true
unset SERVICE_URL
EOF
  log "Wrote ${ENV_FILE}"
}

run_uvicorn() {
  if [ ! -f "${ENV_FILE}" ]; then
    log "Missing ${ENV_FILE}. Run '$0 setup' first."
    exit 1
  fi

  if [ ! -d ".venv" ]; then
    log "Virtualenv .venv not found. Run ./tools/bootstrap_venv.sh first."
    exit 1
  fi

  log "Loading environment from ${ENV_FILE}"
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  log "Activating virtualenv .venv"
  # shellcheck disable=SC1091
  source .venv/bin/activate

  require_cmd uvicorn
  log "uvicorn version: $(uvicorn --version || true)"
  log "Starting uvicorn on http://127.0.0.1:8080"
  exec uvicorn main:app --reload --host 0.0.0.0 --port "${PORT:-8080}"
}

cmd=${1:-}

case "${cmd}" in
  setup)
    require_cmd gcloud
    mkdir -p "${SECRET_DIR}"
    fetch_secret "firebase-service-account" "${SERVICE_ACCOUNT_JSON}"
    fetch_secret "token-encryption-key" "${TOKEN_KEY_FILE}"
    fetch_secret "firebase-web-client-id" "${WEB_CLIENT_ID_FILE}"
    fetch_secret "firebase-web-client-secret" "${WEB_CLIENT_SECRET_FILE}"
    write_env_file
    log "Setup complete. Run '$0 run' to start the API."
    ;;
  run)
    run_uvicorn
    ;;
  *)
    cat <<EOF
Usage: $0 <setup|run>

  setup  Fetch secrets from Secret Manager and create ${ENV_FILE}
  run    Source ${ENV_FILE}, activate .venv, and launch uvicorn
EOF
    exit 1
    ;;
esac
