#!/bin/bash
#
# Firebase Authentication Setup Script (gcloud only)
#
# This script uses only gcloud commands (no Firebase CLI required)
# to set up Firebase Authentication for svg2ooxml.
#
# Prerequisites:
# - gcloud CLI installed and authenticated
# - Project ID: svg2ooxml
#
# Usage:
#   ./scripts/setup-firebase-auth-gcloud-only.sh
#

set -e  # Exit on error

PROJECT_ID="powerful-layout-467812-p1"
REGION="europe-west1"
SERVICE_ACCOUNT="svg2ooxml-runner@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=========================================="
echo "Firebase Auth Setup for svg2ooxml"
echo "(Using gcloud only - no Firebase CLI)"
echo "=========================================="
echo ""
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Account: $SERVICE_ACCOUNT"
echo ""

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

# Step 1: Enable required APIs
echo "Step 1: Enabling required GCP APIs..."
gcloud services enable \
    firebase.googleapis.com \
    identitytoolkit.googleapis.com \
    secretmanager.googleapis.com \
    --project="$PROJECT_ID"
echo "✅ APIs enabled"
echo ""

# Step 2: Check for Firebase service account
echo "Step 2: Checking for Firebase service account..."
echo ""

# Wait a moment for Firebase to initialize
echo "Waiting for Firebase service account to be created..."
sleep 5

# Try to find the Firebase Admin SDK service account
FIREBASE_SA=""
for i in {1..6}; do
    FIREBASE_SA=$(gcloud iam service-accounts list --project="$PROJECT_ID" \
        --filter="email:firebase-adminsdk*" \
        --format="value(email)" | head -1 || echo "")

    if [ -n "$FIREBASE_SA" ]; then
        echo "✅ Found Firebase service account: $FIREBASE_SA"
        break
    fi

    if [ $i -lt 6 ]; then
        echo "   Waiting for Firebase service account... (attempt $i/6)"
        sleep 10
    fi
done

if [ -z "$FIREBASE_SA" ]; then
    echo "⚠️  Firebase Admin SDK service account not found yet."
    echo ""
    echo "This is normal - Firebase initialization can take 2-5 minutes."
    echo ""
    echo "Next steps:"
    echo "  1. Enable Firebase manually:"
    echo "     https://console.firebase.google.com/project/$PROJECT_ID"
    echo "     Click 'Add Firebase' if prompted"
    echo ""
    echo "  2. Wait 2-5 minutes for initialization"
    echo ""
    echo "  3. Run this script again"
    echo ""
    exit 0
fi
echo ""

# Step 3: Create service account key
echo "Step 3: Creating Firebase service account key..."
echo ""

KEY_FILE="firebase-service-account.json"
if [ -f "$KEY_FILE" ]; then
    echo "⚠️  Key file already exists: $KEY_FILE"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Using existing key file"
    else
        echo "Creating new service account key..."
        gcloud iam service-accounts keys create "$KEY_FILE" \
            --iam-account="$FIREBASE_SA" \
            --project="$PROJECT_ID"
        echo "✅ Service account key created: $KEY_FILE"
    fi
else
    echo "Creating service account key..."
    gcloud iam service-accounts keys create "$KEY_FILE" \
        --iam-account="$FIREBASE_SA" \
        --project="$PROJECT_ID"
    echo "✅ Service account key created: $KEY_FILE"
fi

echo "⚠️  IMPORTANT: This file contains sensitive credentials. Keep it secure!"
echo ""

# Step 4: Create Secret Manager secrets
echo "Step 4: Creating Secret Manager secrets..."
echo ""

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
echo "✅ Secrets Created Successfully!"
echo "=========================================="
echo ""
echo "Secrets created in Secret Manager:"
echo "  ✅ firebase-service-account"
echo "  ✅ token-encryption-key"
echo ""
echo "=========================================="
echo "Manual Configuration Required"
echo "=========================================="
echo ""
echo "Complete these 4 manual steps in the Firebase/GCP Console:"
echo ""
echo "1️⃣  Enable Google Sign-In Provider"
echo "   https://console.firebase.google.com/project/$PROJECT_ID/authentication/providers"
echo "   - Click 'Google' provider"
echo "   - Enable it"
echo "   - Set public-facing name: 'svg2ooxml'"
echo "   - Save"
echo ""
echo "2️⃣  Configure OAuth Consent Screen"
echo "   https://console.cloud.google.com/apis/credentials/consent?project=$PROJECT_ID"
echo "   - Select 'External' user type"
echo "   - App name: svg2ooxml"
echo "   - Authorized domains: a.run.app"
echo "   - Add scopes:"
echo "     * https://www.googleapis.com/auth/drive.file"
echo "     * https://www.googleapis.com/auth/presentations"
echo "   - Add test users"
echo "   - Save"
echo ""
echo "3️⃣  Add Authorized Domains"
echo "   https://console.firebase.google.com/project/$PROJECT_ID/authentication/settings"
echo "   - Under 'Authorized domains', add:"
echo "     * svg2ooxml-export-sghya3t5ya-ew.a.run.app"
echo "     * localhost"
echo ""
echo "4️⃣  Get Firebase Web Config"
echo "   https://console.firebase.google.com/project/$PROJECT_ID/settings/general"
echo "   - Scroll to 'Your apps'"
echo "   - Click 'Add app' → Web (</> icon)"
echo "   - Register app: 'svg2ooxml-web'"
echo "   - Copy the config object"
echo "   - Save to: docs/setup/firebase-web-config.json"
echo ""
echo "=========================================="
echo "Next Steps"
echo "=========================================="
echo ""
echo "After completing the manual steps above:"
echo ""
echo "1. Deploy to Cloud Run:"
echo "   git add ."
echo "   git commit -m 'feat: Add Firebase Auth integration'"
echo "   git push origin main"
echo ""
echo "2. Test the deployment:"
echo "   python test_slides_api.py"
echo ""
echo "📚 Documentation:"
echo "   - Implementation summary: docs/implementation-summary-firebase-auth.md"
echo "   - Full spec: docs/specs/firebase-auth-google-slides-export.md"
echo "   - Figma plugin guide: docs/guides/figma-plugin-firebase-auth.md"
echo ""
echo "🎉 Secret setup complete!"
echo "   Complete the 4 manual steps above, then deploy."
