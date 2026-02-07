# GitHub Actions Deployment Setup

## Overview

This project uses GitHub Actions for automated deployment:
- **Firebase** (Hosting, Firestore Rules, Indexes) - Deploys on push to `main`
- **Cloud Run** (Backend API) - Deploys on push to `main`

## Prerequisites

Before GitHub Actions can deploy, you need to set up:
1. Firebase authentication token
2. Google Cloud Workload Identity Federation
3. GitHub Secrets

---

## Setup Instructions

### Step 1: Get Firebase Token

```bash
# Login to Firebase (opens browser)
firebase login

# Generate CI token
firebase login:ci

# Copy the token that's printed
# It looks like: 1//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Step 2: Set up Workload Identity Federation (Recommended)

This allows GitHub Actions to authenticate to Google Cloud without storing service account keys.

```bash
# Set variables
export PROJECT_ID="powerful-layout-467812-p1"
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export GITHUB_REPO="YOUR_GITHUB_USERNAME/svg2ooxml"  # e.g., "ynse/svg2ooxml"
export WIF_POOL="github-actions-pool"
export WIF_PROVIDER="github-actions-provider"
export SERVICE_ACCOUNT="github-actions-deployer"

# 1. Create Workload Identity Pool
gcloud iam workload-identity-pools create $WIF_POOL \
  --project=$PROJECT_ID \
  --location=global \
  --display-name="GitHub Actions Pool"

# 2. Create Workload Identity Provider
gcloud iam workload-identity-pools providers create-oidc $WIF_PROVIDER \
  --project=$PROJECT_ID \
  --location=global \
  --workload-identity-pool=$WIF_POOL \
  --display-name="GitHub Actions Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# 3. Create Service Account
gcloud iam service-accounts create $SERVICE_ACCOUNT \
  --project=$PROJECT_ID \
  --display-name="GitHub Actions Deployer"

# 4. Grant permissions to Service Account
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.builder"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

# 5. Allow GitHub Actions to impersonate Service Account
gcloud iam service-accounts add-iam-policy-binding \
  $SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL/attribute.repository/$GITHUB_REPO"

# 6. Get the Workload Identity Provider resource name
echo "WIF_PROVIDER: projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL/providers/$WIF_PROVIDER"
echo "WIF_SERVICE_ACCOUNT: $SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com"
```

### Step 3: Add GitHub Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions

Add these secrets:

1. **FIREBASE_TOKEN**
   - Value: The token from `firebase login:ci`
   - Used by: `deploy-firebase.yml`

2. **WIF_PROVIDER**
   - Value: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool/providers/github-actions-provider`
   - From Step 2 output
   - Used by: `deploy-cloud-run.yml`

3. **WIF_SERVICE_ACCOUNT**
   - Value: `github-actions-deployer@powerful-layout-467812-p1.iam.gserviceaccount.com`
   - From Step 2 output
   - Used by: `deploy-cloud-run.yml`

### Step 4: Set Cloud Run Environment Variables

These are needed BEFORE first deployment:

```bash
gcloud run services update svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --set-env-vars="
ENVIRONMENT=production,
STRIPE_SECRET_KEY=sk_test_YOUR_KEY_HERE,
STRIPE_WEBHOOK_SECRET=whsec_YOUR_SECRET_HERE,
STRIPE_PRICE_ID_PRO=price_YOUR_PRO_PRICE_ID,
STRIPE_PRICE_ID_ENTERPRISE=price_YOUR_ENTERPRISE_PRICE_ID
"
```

**Or set them as GitHub Secrets and add to the workflow** (more secure):

Add these GitHub Secrets:
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_ID_PRO`
- `STRIPE_PRICE_ID_ENTERPRISE`

Then update `.github/workflows/deploy-cloud-run.yml`:

```yaml
- name: Set Environment Variables
  run: |
    gcloud run services update svg2ooxml-export \
      --region=europe-west1 \
      --project=powerful-layout-467812-p1 \
      --set-env-vars="
    ENVIRONMENT=production,
    STRIPE_SECRET_KEY=${{ secrets.STRIPE_SECRET_KEY }},
    STRIPE_WEBHOOK_SECRET=${{ secrets.STRIPE_WEBHOOK_SECRET }},
    STRIPE_PRICE_ID_PRO=${{ secrets.STRIPE_PRICE_ID_PRO }},
    STRIPE_PRICE_ID_ENTERPRISE=${{ secrets.STRIPE_PRICE_ID_ENTERPRISE }}
    "
```

---

## Alternative: Service Account Key (Less Secure)

If you don't want to use Workload Identity Federation:

```bash
# Create service account
gcloud iam service-accounts create github-deployer \
  --project=powerful-layout-467812-p1

# Grant permissions
gcloud projects add-iam-policy-binding powerful-layout-467812-p1 \
  --member="serviceAccount:github-deployer@powerful-layout-467812-p1.iam.gserviceaccount.com" \
  --role="roles/run.admin"

# Create key
gcloud iam service-accounts keys create key.json \
  --iam-account=github-deployer@powerful-layout-467812-p1.iam.gserviceaccount.com

# Base64 encode for GitHub Secret
cat key.json | base64

# Add as GCP_SA_KEY secret in GitHub
```

Then modify `deploy-cloud-run.yml`:

```yaml
- name: Authenticate to Google Cloud
  uses: google-github-actions/auth@v2
  with:
    credentials_json: ${{ secrets.GCP_SA_KEY }}
```

---

## Deployment Workflow

### Automatic Deployment

1. **Make changes** to code
2. **Commit and push** to `main` branch
3. **GitHub Actions automatically**:
   - Runs tests
   - Builds Docker image
   - Deploys to Cloud Run
   - Deploys Firebase Hosting
   - Updates Firestore rules

### Manual Deployment

Go to GitHub → Actions → Select workflow → Run workflow

---

## What Gets Deployed

### Firebase Deployment (`deploy-firebase.yml`)

**Triggers on changes to**:
- `public/**` (payment pages)
- `firestore.rules`
- `firestore.indexes.json`
- `firebase.json`

**Deploys**:
- ✅ Firebase Hosting (auth.html, payment-success.html, payment-cancel.html)
- ✅ Firestore Security Rules
- ✅ Firestore Composite Indexes

**Time**: ~2-3 minutes

### Cloud Run Deployment (`deploy-cloud-run.yml`)

**Triggers on changes to**:
- `src/**` (Python source code)
- `main.py`
- `requirements.txt`
- `Dockerfile`
- `cloudbuild.yaml`

**Deploys**:
- ✅ FastAPI backend
- ✅ Stripe integration
- ✅ Subscription management
- ✅ Webhook handlers
- ✅ Export pipeline

**Time**: ~5-10 minutes

---

## Testing Deployments

### Test Firebase Deployment

```bash
# Check hosting
curl https://powerful-layout-467812-p1.web.app/auth.html

# Check payment pages
curl https://powerful-layout-467812-p1.web.app/payment-success.html
curl https://powerful-layout-467812-p1.web.app/payment-cancel.html
```

### Test Cloud Run Deployment

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1 \
  --format='value(status.url)')

# Test health endpoint
curl $SERVICE_URL/health

# Should return: {"status":"healthy"}
```

---

## Monitoring Deployments

### View GitHub Actions

1. Go to your repository on GitHub
2. Click "Actions" tab
3. See all workflow runs
4. Click on a run to see details

### View Cloud Build Logs

```bash
# List recent builds
gcloud builds list --region=europe-west1 --limit=5

# View specific build
gcloud builds log BUILD_ID --region=europe-west1
```

### View Cloud Run Logs

```bash
# Tail logs
gcloud run services logs tail svg2ooxml-export \
  --region=europe-west1 \
  --project=powerful-layout-467812-p1
```

---

## Troubleshooting

### Issue: Firebase deployment fails with "Permission denied"

**Solution**: Regenerate Firebase token
```bash
firebase logout
firebase login:ci
# Update FIREBASE_TOKEN secret in GitHub
```

### Issue: Cloud Run deployment fails with "Permission denied"

**Solution**: Check service account permissions
```bash
# Verify service account has required roles
gcloud projects get-iam-policy powerful-layout-467812-p1 \
  --flatten="bindings[].members" \
  --format="table(bindings.role)" \
  --filter="bindings.members:github-actions-deployer@powerful-layout-467812-p1.iam.gserviceaccount.com"
```

### Issue: Health check fails after deployment

**Solution**: Check Cloud Run logs
```bash
gcloud run services logs tail svg2ooxml-export --region=europe-west1
```

Common causes:
- Missing environment variables
- Startup errors in code
- Port configuration issues

---

## Next Steps

1. ✅ Set up Firebase token (Step 1)
2. ✅ Set up Workload Identity Federation (Step 2)
3. ✅ Add GitHub Secrets (Step 3)
4. ✅ Set Cloud Run environment variables (Step 4)
5. ✅ Commit and push to `main` branch
6. ✅ Watch GitHub Actions deploy automatically
7. ✅ Test deployed endpoints
8. ✅ Monitor for issues

---

## Security Best Practices

1. **Never commit secrets** to git
2. **Use GitHub Secrets** for all sensitive data
3. **Use Workload Identity Federation** instead of service account keys
4. **Rotate tokens** every 90 days
5. **Use least-privilege permissions** for service accounts
6. **Enable branch protection** on `main` to require reviews

---

## Useful Commands

```bash
# View GitHub Actions workflows locally
gh workflow list

# View recent workflow runs
gh run list

# View specific run
gh run view RUN_ID

# Re-run failed workflow
gh run rerun RUN_ID

# Manually trigger workflow
gh workflow run deploy-cloud-run.yml
gh workflow run deploy-firebase.yml
```

---

**Status**: ✅ Ready for setup
**Estimated Setup Time**: 30-45 minutes
**Deployment Time per Push**: 5-10 minutes
