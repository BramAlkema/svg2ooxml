#!/bin/bash

# Quick script to grant unlimited exports via Firestore REST API
# Usage: ./scripts/set-unlimited-quota.sh <user-uid>

set -e

PROJECT_ID="powerful-layout-467812-p1"
USER_UID="${1:-RxBg7fFhzAdDDbcxSnoqZo2mh7s2}"  # Default to your UID

echo "🔧 Granting unlimited exports to user: $USER_UID"

# Get access token
ACCESS_TOKEN=$(gcloud auth print-access-token)

# Update user document with unlimited_exports flag
curl -X PATCH \
  "https://firestore.googleapis.com/v1/projects/$PROJECT_ID/databases/(default)/documents/users/$USER_UID?updateMask.fieldPaths=unlimited_exports" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "unlimited_exports": {
        "booleanValue": true
      }
    }
  }'

echo ""
echo ""
echo "✅ Done! User $USER_UID now has unlimited exports"
echo ""
echo "Verification:"
curl -s "https://firestore.googleapis.com/v1/projects/$PROJECT_ID/databases/(default)/documents/users/$USER_UID" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | \
  python3 -c "import sys,json; data=json.load(sys.stdin); print('unlimited_exports:', data.get('fields', {}).get('unlimited_exports', {}).get('booleanValue', False))"
