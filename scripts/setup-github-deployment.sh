#!/bin/bash
# Setup GitHub Actions Deployment for svg2ooxml

set -e

echo "🚀 GitHub Actions Deployment Setup"
echo "==================================="
echo ""

# Configuration
PROJECT_ID="powerful-layout-467812-p1"
REGION="europe-west1"
SERVICE_NAME="svg2ooxml-export"
WIF_POOL="github-actions-pool"
WIF_PROVIDER="github-actions-provider"
SERVICE_ACCOUNT="github-actions-deployer"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
info() {
    echo -e "${GREEN}ℹ${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Get GitHub repository
echo "Enter your GitHub repository (e.g., username/svg2ooxml):"
read -p "> " GITHUB_REPO

if [ -z "$GITHUB_REPO" ]; then
    error "GitHub repository is required"
    exit 1
fi

echo ""
info "Using GitHub repository: $GITHUB_REPO"
info "Using GCP project: $PROJECT_ID"
echo ""

# Step 1: Firebase Token
echo "📱 Step 1: Firebase Authentication"
echo "-----------------------------------"
warn "You need to get a Firebase CI token"
echo ""
echo "Run these commands in a separate terminal:"
echo "  firebase login"
echo "  firebase login:ci"
echo ""
read -p "Have you got the Firebase token? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    warn "Please get the Firebase token first, then run this script again"
    exit 1
fi

echo ""
read -p "Enter your Firebase token: " FIREBASE_TOKEN
if [ -z "$FIREBASE_TOKEN" ]; then
    error "Firebase token is required"
    exit 1
fi

success "Firebase token saved"
echo ""

# Step 2: Workload Identity Federation
echo "🔐 Step 2: Workload Identity Federation"
echo "----------------------------------------"
info "Setting up Workload Identity Federation for GitHub Actions..."
echo ""

# Get project number
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
info "Project number: $PROJECT_NUMBER"

# Create Workload Identity Pool
info "Creating Workload Identity Pool..."
if gcloud iam workload-identity-pools describe $WIF_POOL \
    --project=$PROJECT_ID \
    --location=global &>/dev/null; then
    warn "Workload Identity Pool already exists, skipping..."
else
    gcloud iam workload-identity-pools create $WIF_POOL \
      --project=$PROJECT_ID \
      --location=global \
      --display-name="GitHub Actions Pool"
    success "Workload Identity Pool created"
fi

# Create Workload Identity Provider
info "Creating Workload Identity Provider..."
if gcloud iam workload-identity-pools providers describe $WIF_PROVIDER \
    --project=$PROJECT_ID \
    --location=global \
    --workload-identity-pool=$WIF_POOL &>/dev/null; then
    warn "Workload Identity Provider already exists, skipping..."
else
    gcloud iam workload-identity-pools providers create-oidc $WIF_PROVIDER \
      --project=$PROJECT_ID \
      --location=global \
      --workload-identity-pool=$WIF_POOL \
      --display-name="GitHub Actions Provider" \
      --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
      --issuer-uri="https://token.actions.githubusercontent.com"
    success "Workload Identity Provider created"
fi

# Create Service Account
info "Creating Service Account..."
if gcloud iam service-accounts describe $SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
    --project=$PROJECT_ID &>/dev/null; then
    warn "Service Account already exists, skipping..."
else
    gcloud iam service-accounts create $SERVICE_ACCOUNT \
      --project=$PROJECT_ID \
      --display-name="GitHub Actions Deployer"
    success "Service Account created"
fi

# Grant permissions
info "Granting permissions to Service Account..."

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin" \
  --condition=None \
  --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser" \
  --condition=None \
  --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.builder" \
  --condition=None \
  --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin" \
  --condition=None \
  --quiet

success "Permissions granted"

# Allow GitHub to impersonate Service Account
info "Allowing GitHub Actions to impersonate Service Account..."
gcloud iam service-accounts add-iam-policy-binding \
  $SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL/attribute.repository/$GITHUB_REPO" \
  --quiet

success "GitHub Actions can now impersonate Service Account"
echo ""

# Step 3: GitHub Secrets
echo "🔑 Step 3: GitHub Secrets"
echo "-------------------------"
info "You need to add these secrets to your GitHub repository:"
echo ""

WIF_PROVIDER_PATH="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL/providers/$WIF_PROVIDER"
WIF_SA_EMAIL="$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com"

echo "1. FIREBASE_TOKEN"
echo "   Value: $FIREBASE_TOKEN"
echo ""
echo "2. WIF_PROVIDER"
echo "   Value: $WIF_PROVIDER_PATH"
echo ""
echo "3. WIF_SERVICE_ACCOUNT"
echo "   Value: $WIF_SA_EMAIL"
echo ""

info "Go to: https://github.com/$GITHUB_REPO/settings/secrets/actions"
echo ""

read -p "Press Enter when you've added all secrets..."
echo ""

# Step 4: Stripe Secrets (optional)
echo "💳 Step 4: Stripe Environment Variables (Optional)"
echo "--------------------------------------------------"
warn "You can add Stripe keys as GitHub Secrets OR set them on Cloud Run directly"
echo ""
echo "For GitHub Secrets, add these:"
echo "  - STRIPE_SECRET_KEY"
echo "  - STRIPE_WEBHOOK_SECRET"
echo "  - STRIPE_PRICE_ID_PRO"
echo "  - STRIPE_PRICE_ID_ENTERPRISE"
echo ""

read -p "Have you added Stripe secrets? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    success "Stripe secrets added to GitHub"
else
    warn "You'll need to set Stripe environment variables on Cloud Run manually"
fi

echo ""

# Summary
echo "✅ Setup Complete!"
echo "=================="
echo ""
info "Next steps:"
echo "  1. Commit your changes"
echo "  2. Push to main branch: git push origin main"
echo "  3. Watch GitHub Actions deploy: https://github.com/$GITHUB_REPO/actions"
echo ""
info "Useful commands:"
echo "  View workflows: gh workflow list"
echo "  Trigger deploy: gh workflow run deploy-cloud-run.yml"
echo "  View logs: gcloud run services logs tail $SERVICE_NAME --region=$REGION"
echo ""
success "You're ready to deploy! 🚀"
