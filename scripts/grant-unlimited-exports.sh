#!/bin/bash

# Script to grant unlimited exports to a user
# Usage: ./scripts/grant-unlimited-exports.sh <email>

set -e

PROJECT_ID="powerful-layout-467812-p1"

if [ -z "$1" ]; then
    echo "Usage: $0 <user-email>"
    echo "Example: $0 info@bramalkema.nl"
    exit 1
fi

USER_EMAIL="$1"

echo "🔍 Finding user with email: $USER_EMAIL"

# Get user UID from Firebase Auth
USER_UID=$(gcloud firestore documents query --project="$PROJECT_ID" \
  "SELECT __name__ FROM users WHERE email = '$USER_EMAIL' LIMIT 1" \
  --format="value(name)" | sed 's/.*\///')

if [ -z "$USER_UID" ]; then
    echo "❌ User not found with email: $USER_EMAIL"
    echo ""
    echo "Trying to find user by listing recent users..."
    gcloud firestore documents list users --project="$PROJECT_ID" --limit=10 --format="table(name,createTime,email)"
    exit 1
fi

echo "✅ Found user: $USER_UID"
echo ""
echo "📝 Setting unlimited_exports flag..."

# Update user document to add unlimited_exports flag
gcloud firestore documents update "users/$USER_UID" \
  --project="$PROJECT_ID" \
  --update-mask="unlimited_exports" \
  --set-flags="unlimited_exports=true"

echo ""
echo "✅ Success! User $USER_EMAIL now has unlimited exports"
echo ""
echo "You can verify with:"
echo "  gcloud firestore documents get users/$USER_UID --project=$PROJECT_ID"
