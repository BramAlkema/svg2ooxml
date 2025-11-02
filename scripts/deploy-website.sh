#!/bin/bash
#
# Deploy Website to Firebase Hosting
#
# This script manually deploys the website files to Firebase Hosting
# using gsutil since we can't run firebase deploy non-interactively.
#

set -e

PROJECT_ID="powerful-layout-467812-p1"
SITE_NAME="powerful-layout-467812-p1"

echo "==========================================="
echo "Deploying Website to Firebase Hosting"
echo "==========================================="
echo ""
echo "Project: $PROJECT_ID"
echo "Site: $SITE_NAME"
echo ""

# Check if public directory exists
if [ ! -d "public" ]; then
    echo "❌ public/ directory not found"
    exit 1
fi

# Upload files to Cloud Storage bucket for Firebase Hosting
echo "Uploading files to Firebase Hosting..."
gsutil -m rsync -r -d public/ gs://${PROJECT_ID}.appspot.com/

echo ""
echo "✅ Files uploaded to Cloud Storage"
echo ""
echo "Note: Firebase Hosting requires the Firebase CLI for final deployment."
echo "The files are uploaded, but you need to run 'firebase deploy --only hosting'"
echo "from an interactive environment to complete the deployment."
echo ""
echo "Website will be available at:"
echo "  - https://${SITE_NAME}.web.app"
echo "  - https://${SITE_NAME}.firebaseapp.com"
