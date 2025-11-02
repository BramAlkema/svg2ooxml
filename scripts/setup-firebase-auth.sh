#!/bin/bash
#
# Firebase Authentication Setup Script
#
# This script automates the Firebase and GCP setup required for
# Firebase Authentication integration with Google Slides export.
#
# Prerequisites:
# - gcloud CLI installed and authenticated
# - firebase CLI installed (npm install -g firebase-tools)
# - Project ID: svg2ooxml
#
# Usage:
#   ./scripts/setup-firebase-auth.sh
#

set -e  # Exit on error

PROJECT_ID="svg2ooxml"
REGION="europe-west1"
SERVICE_ACCOUNT="svg2ooxml-runner@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=========================================="
echo "Firebase Auth Setup for svg2ooxml"
echo "=========================================="
echo ""
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Account: $SERVICE_ACCOUNT"
echo ""

# Check if firebase CLI is installed
if ! command -v firebase &> /dev/null; then
    echo "❌ Firebase CLI not found."
    echo ""
    echo "Please install Firebase CLI:"
    echo ""
    echo "  Option 1 (Homebrew - Recommended for macOS):"
    echo "    brew install firebase-cli"
    echo ""
    echo "  Option 2 (npm):"
    echo "    npm install -g firebase-tools"
    echo ""
    echo "Then run this script again."
    exit 1
fi

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
    echo "❌ gcloud not authenticated. Please run:"
    echo "  gcloud auth login"
    exit 1
fi

# Set gcloud project
echo "Setting gcloud project to $PROJECT_ID..."
gcloud config set project "$PROJECT_ID"
echo "✅ Project set"
echo ""

# Step 1: Check if Firebase project exists, if not initialize it
echo "Step 1: Checking Firebase project..."
echo ""

# Login to Firebase (if not already logged in)
firebase login --no-localhost 2>/dev/null || true

# Check if project already has Firebase enabled
if firebase projects:list | grep -q "$PROJECT_ID"; then
    echo "✅ Firebase already enabled for project $PROJECT_ID"
else
    echo "Adding Firebase to GCP project $PROJECT_ID..."
    firebase projects:addfirebase "$PROJECT_ID"
    echo "✅ Firebase added to project"
fi
echo ""

# Step 2: Enable required APIs
echo "Step 2: Enabling required GCP APIs..."
gcloud services enable \
    firebase.googleapis.com \
    identitytoolkit.googleapis.com \
    secretmanager.googleapis.com \
    --project="$PROJECT_ID"
echo "✅ APIs enabled"
echo ""

# Step 3: Enable Google Sign-In provider
echo "Step 3: Enabling Google Sign-In provider..."
echo ""
echo "⚠️  Manual step required:"
echo "   Firebase CLI doesn't support enabling auth providers yet."
echo "   Please enable Google Sign-In manually:"
echo ""
echo "   1. Go to: https://console.firebase.google.com/project/$PROJECT_ID/authentication/providers"
echo "   2. Click on 'Google' provider"
echo "   3. Enable it"
echo "   4. Set public-facing name: 'svg2ooxml'"
echo "   5. Save"
echo ""
read -p "Press Enter after enabling Google Sign-In provider..."
echo "✅ Google Sign-In enabled (manual)"
echo ""

# Step 4: Configure OAuth consent screen
echo "Step 4: Configuring OAuth consent screen..."
echo ""
echo "⚠️  Manual step required:"
echo "   OAuth consent screen must be configured manually:"
echo ""
echo "   1. Go to: https://console.cloud.google.com/apis/credentials/consent?project=$PROJECT_ID"
echo "   2. Select 'External' user type (for all Google users)"
echo "   3. Fill in application details:"
echo "      - App name: svg2ooxml"
echo "      - User support email: (your email)"
echo "      - Authorized domains: a.run.app"
echo "   4. Add scopes:"
echo "      - https://www.googleapis.com/auth/drive.file"
echo "      - https://www.googleapis.com/auth/presentations"
echo "   5. Add test users (for Testing mode)"
echo "   6. Save and continue"
echo ""
read -p "Press Enter after configuring OAuth consent screen..."
echo "✅ OAuth consent screen configured (manual)"
echo ""

# Step 5: Create Firebase web app and get config
echo "Step 5: Creating Firebase web app..."
echo ""

# Check if app already exists
APP_ID=$(firebase apps:list --project="$PROJECT_ID" 2>/dev/null | grep "svg2ooxml-web" | awk '{print $4}' || echo "")

if [ -z "$APP_ID" ]; then
    echo "Creating new web app: svg2ooxml-web..."

    # Create web app (Firebase CLI method)
    firebase apps:create WEB "svg2ooxml-web" --project="$PROJECT_ID"

    # Get the app ID
    APP_ID=$(firebase apps:list --project="$PROJECT_ID" | grep "svg2ooxml-web" | awk '{print $4}')
    echo "✅ Web app created: $APP_ID"
else
    echo "✅ Web app already exists: $APP_ID"
fi

# Get Firebase config
echo ""
echo "Fetching Firebase config..."
firebase apps:sdkconfig WEB "$APP_ID" --project="$PROJECT_ID" > /tmp/firebase-config.json 2>/dev/null || {
    echo "⚠️  Could not fetch config automatically."
    echo "   Please get config manually:"
    echo "   1. Go to: https://console.firebase.google.com/project/$PROJECT_ID/settings/general"
    echo "   2. Scroll to 'Your apps'"
    echo "   3. Find 'svg2ooxml-web' app"
    echo "   4. Copy the config object"
    echo "   5. Save to: docs/setup/firebase-web-config.json"
    echo ""
    read -p "Press Enter after saving config..."
}

if [ -f /tmp/firebase-config.json ]; then
    mkdir -p docs/setup
    mv /tmp/firebase-config.json docs/setup/firebase-web-config.json
    echo "✅ Firebase config saved to: docs/setup/firebase-web-config.json"
fi
echo ""

# Step 6: Get or create Firebase service account key
echo "Step 6: Creating Firebase service account key..."
echo ""

# Find the Firebase Admin SDK service account
FIREBASE_SA=$(gcloud iam service-accounts list --project="$PROJECT_ID" \
    --filter="email:firebase-adminsdk*" \
    --format="value(email)" | head -1)

if [ -z "$FIREBASE_SA" ]; then
    echo "❌ Firebase Admin SDK service account not found."
    echo "   Firebase project may not be fully initialized."
    echo "   Please wait a few minutes and run this script again."
    exit 1
fi

echo "Found Firebase service account: $FIREBASE_SA"

# Create service account key
KEY_FILE="firebase-service-account.json"
if [ -f "$KEY_FILE" ]; then
    echo "⚠️  Key file already exists: $KEY_FILE"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping key creation"
        KEY_FILE=""
    fi
fi

if [ -n "$KEY_FILE" ]; then
    echo "Creating new service account key..."
    gcloud iam service-accounts keys create "$KEY_FILE" \
        --iam-account="$FIREBASE_SA" \
        --project="$PROJECT_ID"
    echo "✅ Service account key created: $KEY_FILE"
    echo "⚠️  IMPORTANT: This file contains sensitive credentials. Keep it secure!"
fi
echo ""

# Step 7: Create Secret Manager secrets
echo "Step 7: Creating Secret Manager secrets..."
echo ""

if [ ! -f "$KEY_FILE" ]; then
    echo "⚠️  No key file found. Skipping secret creation."
    echo "   Please run this script again to create secrets."
    exit 0
fi

# Create firebase-service-account secret
echo "Creating firebase-service-account secret..."
if gcloud secrets describe firebase-service-account --project="$PROJECT_ID" &>/dev/null; then
    echo "Secret already exists. Updating version..."
    gcloud secrets versions add firebase-service-account \
        --data-file="$KEY_FILE" \
        --project="$PROJECT_ID"
else
    gcloud secrets create firebase-service-account \
        --data-file="$KEY_FILE" \
        --replication-policy=automatic \
        --project="$PROJECT_ID"
fi
echo "✅ firebase-service-account secret created"

# Generate token encryption key
echo ""
echo "Generating token encryption key..."
python3 -c "from cryptography.fernet import Fernet; import base64; print(base64.urlsafe_b64encode(Fernet.generate_key()).decode())" > token-key.txt

# Create token-encryption-key secret
echo "Creating token-encryption-key secret..."
if gcloud secrets describe token-encryption-key --project="$PROJECT_ID" &>/dev/null; then
    echo "Secret already exists. Updating version..."
    gcloud secrets versions add token-encryption-key \
        --data-file=token-key.txt \
        --project="$PROJECT_ID"
else
    gcloud secrets create token-encryption-key \
        --data-file=token-key.txt \
        --replication-policy=automatic \
        --project="$PROJECT_ID"
fi
echo "✅ token-encryption-key secret created"

# Grant Cloud Run service account access to secrets
echo ""
echo "Granting Cloud Run service account access to secrets..."
gcloud secrets add-iam-policy-binding firebase-service-account \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" \
    --quiet

gcloud secrets add-iam-policy-binding token-encryption-key \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" \
    --quiet

echo "✅ IAM permissions granted"
echo ""

# Clean up sensitive files
echo "Cleaning up sensitive files..."
if [ -f "$KEY_FILE" ]; then
    read -p "Delete local service account key file? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm "$KEY_FILE"
        echo "✅ Deleted $KEY_FILE"
    else
        echo "⚠️  Remember to delete $KEY_FILE manually after testing"
    fi
fi

if [ -f "token-key.txt" ]; then
    rm token-key.txt
    echo "✅ Deleted token-key.txt"
fi
echo ""

# Summary
echo "=========================================="
echo "✅ Firebase Auth Setup Complete!"
echo "=========================================="
echo ""
echo "Secrets created in Secret Manager:"
echo "  - firebase-service-account"
echo "  - token-encryption-key"
echo ""
echo "Next steps:"
echo "  1. Review the manual configuration steps above"
echo "  2. Add authorized domains (see note below)"
echo "  3. Deploy to Cloud Run:"
echo "     git add ."
echo "     git commit -m 'feat: Add Firebase Auth integration'"
echo "     git push origin main"
echo ""
echo "⚠️  Authorized Domains:"
echo "   You need to manually add authorized domains to Firebase:"
echo "   1. Go to: https://console.firebase.google.com/project/$PROJECT_ID/authentication/settings"
echo "   2. Under 'Authorized domains', add:"
echo "      - svg2ooxml-export-sghya3t5ya-ew.a.run.app"
echo "      - localhost"
echo "      - (your Figma plugin domain)"
echo ""
echo "📚 Documentation:"
echo "   - Full spec: docs/specs/firebase-auth-google-slides-export.md"
echo "   - Implementation summary: docs/implementation-summary-firebase-auth.md"
echo "   - Figma plugin guide: docs/guides/figma-plugin-firebase-auth.md"
echo ""
echo "🎉 Setup complete!"
