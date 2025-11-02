#!/bin/bash
#
# Update Firebase Hosting Website
#
# Quick script to deploy website changes to Firebase Hosting.
# Usage: ./scripts/update-website.sh
#

set -e

PROJECT_ID="powerful-layout-467812-p1"
REGION="europe-west1"

echo "=========================================="
echo "Deploying Website to Firebase Hosting"
echo "=========================================="
echo ""
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Check if public directory exists
if [ ! -d "public" ]; then
    echo "❌ public/ directory not found"
    echo "   Make sure you're in the project root directory"
    exit 1
fi

# Check if firebase.json exists
if [ ! -f "firebase.json" ]; then
    echo "❌ firebase.json not found"
    echo "   Make sure you're in the project root directory"
    exit 1
fi

# Show what will be deployed
echo "Files to deploy:"
ls -lh public/
echo ""

# Deploy
echo "Deploying to Firebase Hosting..."
gcloud builds submit \
  --config=cloudbuild-hosting.yaml \
  --region=$REGION \
  --project=$PROJECT_ID \
  .

echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "Website URLs:"
echo "  - https://${PROJECT_ID}.web.app"
echo "  - https://${PROJECT_ID}.firebaseapp.com"
echo ""
echo "Pages:"
echo "  - Homepage: https://${PROJECT_ID}.web.app/"
echo "  - Privacy:  https://${PROJECT_ID}.web.app/privacy.html"
echo "  - Terms:    https://${PROJECT_ID}.web.app/terms.html"
echo ""
