#!/bin/bash
set -euo pipefail

CLIENT_JSON="client_secret_129309161606-p0sbjrf4u0ot61qbelbsmqft2i4547f5.apps.googleusercontent.com.json"
SCOPES="https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive.file,https://www.googleapis.com/auth/presentations"

echo "Launching browser auth..."
gcloud auth application-default login --client-id-file="${CLIENT_JSON}" --scopes="${SCOPES}"
