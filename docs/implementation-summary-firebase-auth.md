# Firebase Authentication Implementation - Summary

**Date**: 2025-11-02
**Status**: ✅ Implementation Complete (Phase 1-4)
**Ready for**: Phase 1 Firebase Console Setup → Testing → Deployment

---

## Overview

Successfully implemented Firebase Authentication with Google OAuth for distributed Google Slides export functionality. This enables users to export SVG content to their own Google Slides workspaces, solving the service account 0-byte Drive storage quota limitation.

---

## Implementation Progress

### ✅ Phase 2: API Authentication (Completed)

**Duration**: ~2 hours
**Status**: 100% Complete

#### Task 2.1: Add Dependencies ✅
- Added `firebase-admin>=6.5.0` to requirements.txt and pyproject.toml
- Verified all imports work correctly
- Firebase Admin SDK v7.1.0 installed

#### Task 2.2: Create Firebase Initialization Module ✅
**File**: `src/svg2ooxml/api/auth/firebase.py`
- `initialize_firebase()` - Initialize Firebase Admin SDK with service account
- `verify_id_token(id_token: str)` - Verify Firebase ID tokens
- Supports both service account key file and Application Default Credentials
- Comprehensive error handling and logging

#### Task 2.3: Create Token Encryption Module ✅
**File**: `src/svg2ooxml/api/auth/encryption.py`
- `encrypt_token(token: str)` - Encrypt OAuth tokens using Fernet (AES-256)
- `decrypt_token(encrypted_token: str)` - Decrypt stored tokens
- `generate_encryption_key()` - Generate new encryption keys
- Secure: Never logs full tokens, only hashes

#### Task 2.4: Create Authentication Middleware ✅
**File**: `src/svg2ooxml/api/auth/middleware.py`
- `verify_firebase_token()` - FastAPI dependency for protected routes
- Extracts token from `Authorization: Bearer <token>` header
- Returns user info (uid, email, token, token_hash)
- Raises 401 Unauthorized on invalid/expired tokens
- Secure logging (only logs token hashes)

#### Task 2.5: Update Export Endpoint ✅
**File**: `src/svg2ooxml/api/routes/export.py`
- Added `user: dict = Depends(verify_firebase_token)` parameter
- Endpoint now requires authentication
- Returns 401 if no token or invalid token
- Updated docstring with authentication requirements
- Passes user info to export service

#### Task 2.6: Initialize Firebase on Startup ✅
**File**: `main.py`
- Added Firebase initialization to lifespan manager
- Initializes Firebase Admin SDK on app startup
- Graceful degradation if Firebase init fails (allows PPTX export)
- Proper logging for success and failure cases

---

### ✅ Phase 3: Drive API Integration (Completed)

**Duration**: ~2-3 hours
**Status**: 100% Complete

#### Task 3.1: Update Export Service for User Credentials ✅
**File**: `src/svg2ooxml/api/services/export_service.py`
- Added `user: Optional[dict] = None` parameter to `create_job()`
- Stores user info (uid, email, token_hash) in job document
- Encrypts and stores OAuth token for background processing
- Backward compatible (works with or without user)

#### Task 3.2: Update Background Tasks for Token Handling ✅
**Files**:
- `src/svg2ooxml/api/background/tasks.py`
  - Fetches job data to check for encrypted token
  - Includes encrypted token in Cloud Tasks payload
- `src/svg2ooxml/api/routes/tasks.py`
  - Added `auth_token_encrypted: str | None` to TaskRequest model
  - Decrypts token before processing
  - Deletes encrypted token from Firestore after successful completion
  - Graceful fallback if decryption fails

#### Task 3.3: Update Slides Publisher for User Credentials ✅
**File**: `src/svg2ooxml/api/services/slides_publisher.py`
- Added `user_token: str | None = None` parameter
- Created `_build_user_credentials(id_token: str)` helper function
- Uses user credentials when token provided
- Falls back to service account when no token (backward compatible)
- Proper logging for auth type used

#### Task 3.4: Update Export Service Process Job ✅
**File**: `src/svg2ooxml/api/services/export_service.py`
- Added `user_token: str | None = None` parameter to `process_job()`
- Updated `_publish_to_slides()` to accept and pass user_token
- Token flows through entire pipeline to slides publisher

---

### ✅ Phase 4: Deployment Configuration (Completed)

**Duration**: ~1 hour
**Status**: 100% Complete

#### Task 4.1: Update cloudbuild.yaml ✅
**File**: `cloudbuild.yaml`
- Added `FIREBASE_PROJECT_ID` environment variable
- Added `FIREBASE_SERVICE_ACCOUNT_PATH` environment variable
- Mounted secrets via `--update-secrets`:
  - `/secrets/firebase-service-account=firebase-service-account:latest`
  - `TOKEN_ENCRYPTION_KEY=token-encryption-key:latest`
- Ready for deployment once secrets are created

#### Task 4.2: Update GitHub Actions Workflow ✅
**File**: `.github/workflows/test-suite.yml`
- Added environment variables for testing:
  - `FIREBASE_AUTH_EMULATOR_HOST=localhost:9099`
  - `TOKEN_ENCRYPTION_KEY=<test-key>`
- Tests can run without real Firebase setup
- CI pipeline ready

---

## Files Summary

### 📁 New Files Created (4 files)

```
src/svg2ooxml/api/auth/
├── __init__.py (empty - package marker)
├── firebase.py (Firebase Admin SDK initialization and token verification)
├── encryption.py (Token encryption/decryption with Fernet)
└── middleware.py (FastAPI authentication middleware)
```

### 📝 Files Modified (9 files)

1. **requirements.txt** - Added firebase-admin>=6.5.0
2. **pyproject.toml** - Added firebase-admin to api extras
3. **main.py** - Firebase initialization on startup
4. **src/svg2ooxml/api/routes/export.py** - Auth required for export endpoint
5. **src/svg2ooxml/api/routes/tasks.py** - Token decryption in background tasks
6. **src/svg2ooxml/api/services/export_service.py** - User credentials throughout pipeline
7. **src/svg2ooxml/api/services/slides_publisher.py** - User authentication for Drive/Slides
8. **src/svg2ooxml/api/background/tasks.py** - Token handling in Cloud Tasks
9. **cloudbuild.yaml** - Secrets mounting for deployment
10. **.github/workflows/test-suite.yml** - Test environment variables

---

## Architecture Overview

### Authentication Flow

```
┌─────────────────┐
│  Figma Plugin   │
│                 │
│ 1. User signs   │
│    in with      │
│    Google       │
└────────┬────────┘
         │ Firebase Auth
         │ (Google OAuth)
         ↓
┌─────────────────┐
│ Firebase Auth   │
│ Returns ID      │
│ token           │
└────────┬────────┘
         │
         │ Authorization: Bearer <token>
         ↓
┌─────────────────┐
│ Cloud Run API   │
│ /api/v1/export  │
│                 │
│ 2. Verify token │
│    (middleware) │
└────────┬────────┘
         │
         │ 3. Create job with encrypted token
         ↓
┌─────────────────┐
│   Firestore     │
│  Job Document   │
│                 │
│ {               │
│   job_id,       │
│   user: {...},  │
│   auth_token_   │
│   encrypted     │
│ }               │
└────────┬────────┘
         │
         │ 4. Enqueue to Cloud Tasks
         ↓
┌─────────────────┐
│  Cloud Tasks    │
│                 │
│ POST /tasks/    │
│ process-export  │
└────────┬────────┘
         │
         │ 5. Decrypt token
         ↓
┌─────────────────┐
│ Export Service  │
│ process_job()   │
│                 │
│ 6. Convert SVG  │
│    to PPTX      │
└────────┬────────┘
         │
         │ 7. Upload with user credentials
         ↓
┌─────────────────┐
│ Slides          │
│ Publisher       │
│                 │
│ 8. Use user     │
│    token for    │
│    Drive API    │
└────────┬────────┘
         │
         │ 9. Slides created
         ↓
┌─────────────────┐
│ User's Google   │
│ Drive/Slides    │
│                 │
│ ✅ Presentation │
└─────────────────┘
```

### Security Model

**Token Lifecycle**:
1. **Client**: Firebase Auth popup → ID token (1-hour expiry)
2. **API**: Token verified by Firebase Admin SDK
3. **Storage**: Token encrypted with Fernet (AES-256) before Firestore storage
4. **Background**: Token decrypted for Drive API call
5. **Cleanup**: Token deleted from Firestore after successful processing

**Security Features**:
- ✅ Tokens encrypted at rest (Fernet with 256-bit key)
- ✅ Tokens never logged (only SHA-256 hashes logged)
- ✅ Tokens deleted after use
- ✅ Firebase Admin SDK verifies token signature
- ✅ Token expiration checked (1-hour max)
- ✅ Minimal OAuth scopes requested (`drive.file`, `presentations`)

---

## Next Steps: Before Testing

### ⚠️ Phase 1: Firebase Console Setup (Required)

Before you can test the implementation, you **must** complete Firebase setup. You can use the automated script or do it manually:

#### Option A: Automated Setup (Recommended) ✨

**Prerequisites**:
```bash
# Install Firebase CLI
# Option 1: Homebrew (Recommended for macOS)
brew install firebase-cli

# Option 2: npm
npm install -g firebase-tools

# Verify installation
firebase --version
gcloud --version
```

**Run the setup script**:
```bash
./scripts/setup-firebase-auth.sh
```

The script will:
- ✅ Enable Firebase on your GCP project
- ✅ Enable required APIs
- ✅ Create Firebase web app and get config
- ✅ Create Firebase service account key
- ✅ Create Secret Manager secrets with proper IAM permissions
- ⚠️ Prompt you for 2 manual steps (OAuth consent screen, Google Sign-In provider)

**Total time**: ~15 minutes (vs 2 hours manual)

#### Option B: Manual Setup

If you prefer manual setup, complete these steps:

#### 1.1 Create Firebase Project (30 min)
1. Go to https://console.firebase.google.com/
2. Click "Add project"
3. Select existing GCP project: `svg2ooxml`
4. Create project

#### 1.2 Enable Google Sign-In Provider (20 min)
1. Firebase Console → Authentication → Sign-in method
2. Enable "Google" provider
3. Set public-facing name: "svg2ooxml"
4. Save

#### 1.3 Configure OAuth Consent Screen (30 min)
1. Go to GCP Console → OAuth consent screen
2. Select user type: **External** (for all Google users)
3. Fill application details:
   - App name: "svg2ooxml"
   - Authorized domains: `a.run.app`
4. Add scopes:
   - `https://www.googleapis.com/auth/drive.file`
   - `https://www.googleapis.com/auth/presentations`
5. Add test users (for Testing mode)

#### 1.4 Add Authorized Domains (10 min)
1. Firebase Console → Authentication → Settings
2. Add authorized domains:
   - `svg2ooxml-export-sghya3t5ya-ew.a.run.app`
   - `localhost` (for local dev)
   - Figma plugin domain (TBD)

#### 1.5 Generate Web App Config (10 min)
1. Firebase Console → Project settings
2. Scroll to "Your apps"
3. Click "Add app" → Web
4. Register app: "svg2ooxml-web"
5. Copy Firebase config object
6. Save to `docs/setup/firebase-web-config.json`

#### 1.6 Create Firebase Service Account (15 min)
1. GCP Console → IAM & Admin → Service Accounts
2. Find Firebase service account: `firebase-adminsdk-xxxxx@svg2ooxml.iam.gserviceaccount.com`
3. Create JSON key
4. Download and store securely (DO NOT COMMIT)

#### 1.7 Create Secret Manager Secrets (15 min)

**Important**: Run these commands to create the required secrets:

```bash
# 1. Enable Secret Manager API
gcloud services enable secretmanager.googleapis.com --project=svg2ooxml

# 2. Create secret for Firebase service account
# (Replace with your downloaded key file)
gcloud secrets create firebase-service-account \
  --data-file=firebase-service-account.json \
  --replication-policy=automatic \
  --project=svg2ooxml

# 3. Generate token encryption key
python3 -c "from cryptography.fernet import Fernet; import base64; print(base64.urlsafe_b64encode(Fernet.generate_key()).decode())" > token-key.txt

# 4. Create secret for encryption key
gcloud secrets create token-encryption-key \
  --data-file=token-key.txt \
  --replication-policy=automatic \
  --project=svg2ooxml

# 5. Grant Cloud Run service account access
SERVICE_ACCOUNT="svg2ooxml-runner@svg2ooxml.iam.gserviceaccount.com"

gcloud secrets add-iam-policy-binding firebase-service-account \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor" \
  --project=svg2ooxml

gcloud secrets add-iam-policy-binding token-encryption-key \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor" \
  --project=svg2ooxml

# 6. Clean up local files (IMPORTANT for security)
rm firebase-service-account.json token-key.txt
```

---

## Testing Guide

### Local Testing (After Phase 1 Setup)

**Prerequisites**:
- Firebase project created
- Service account key available
- Encryption key generated

**Steps**:
1. Set environment variables:
   ```bash
   export FIREBASE_PROJECT_ID=svg2ooxml
   export FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/firebase-service-account.json
   export TOKEN_ENCRYPTION_KEY=<your-generated-key>
   export GCP_PROJECT=svg2ooxml
   ```

2. Run the API locally:
   ```bash
   source .venv/bin/activate
   uvicorn main:app --host 0.0.0.0 --port 8080
   ```

3. Test authentication:
   - Get a Firebase ID token (see Figma plugin guide)
   - Call API with token:
     ```bash
     curl -X POST http://localhost:8080/api/v1/export \
       -H "Authorization: Bearer <your-firebase-token>" \
       -H "Content-Type: application/json" \
       -d @test-payload.json
     ```

### Cloud Run Testing (After Deployment)

1. **Deploy** (after Phase 1 complete):
   ```bash
   git add .
   git commit -m "Add Firebase Auth integration"
   git push origin main
   ```

2. **Verify deployment**:
   ```bash
   gcloud run services describe svg2ooxml-export \
     --region=europe-west1 \
     --format=yaml
   ```

3. **Check secrets mounted**:
   - Look for `/secrets/firebase-service-account` in volumes
   - Look for `TOKEN_ENCRYPTION_KEY` in env vars

4. **Test with updated test script**:
   ```bash
   python test_slides_api.py
   ```
   - Script will prompt for Firebase ID token
   - Get token from Firebase Auth (see Figma plugin guide)

---

## Rollback Plan

If deployment fails or issues occur:

### Immediate Rollback
```bash
# Revert to previous Cloud Run revision
gcloud run services update-traffic svg2ooxml-export \
  --to-revisions=<PREVIOUS_REVISION>=100 \
  --region=europe-west1
```

### Code Rollback
```bash
# Revert the commit
git revert HEAD
git push origin main
```

### Graceful Degradation
The implementation includes graceful degradation:
- If Firebase fails to initialize, service starts without auth
- PPTX export still works without authentication
- Only Slides export requires authentication

---

## Success Metrics

### Week 1 Targets
- [ ] 0 authentication errors (excluding user denials)
- [ ] > 95% Slides upload success rate with user auth
- [ ] < 200ms token verification latency (p95)
- [ ] 0 production incidents

### Month 1 Targets
- [ ] > 100 successful Slides exports
- [ ] > 90% user authentication success rate
- [ ] < 5% token expiration errors
- [ ] Stay within free tier (< 1,000 MAU)

### Monitoring Queries

**Cloud Logging Queries**:
```
# Authentication failures
resource.type="cloud_run_revision"
severity="WARNING"
jsonPayload.message=~"Authentication failed"

# Slides upload with user auth
resource.type="cloud_run_revision"
jsonPayload.message=~"Using user credentials for Slides upload"

# Token encryption/decryption
resource.type="cloud_run_revision"
jsonPayload.message=~"Token (encrypted|decrypted) successfully"
```

---

## Open Questions / Blockers

1. **Figma Plugin Domain** ⚠️
   - **Status**: Pending
   - **Needed for**: Task 1.4 (Authorized domains)
   - **Action**: Get domain from plugin team

2. **Privacy Policy URL** ⚠️
   - **Status**: Pending
   - **Needed for**: Task 1.3 (OAuth consent screen)
   - **Action**: Decide on hosting location

3. **Test User Accounts** ⚠️
   - **Status**: Pending
   - **Needed for**: Task 1.3, Task 5.2
   - **Action**: Create or designate test accounts

---

## Cost Impact

**No Change**: Stays within free tier (~$0.14/month)

**Firebase Auth**:
- Free tier: 50,000 MAU
- Expected usage: < 1,000 MAU initially
- Cost: $0.00/month

**Existing Services** (unchanged):
- Cloud Run: ~$0.08/month
- Cloud Storage: ~$0.02/month
- Firestore: ~$0.01/month
- Cloud Tasks: ~$0.03/month

**Total**: ~$0.14/month

---

## Documentation References

- **Full Specification**: `docs/specs/firebase-auth-google-slides-export.md`
- **Detailed Task Breakdown**: `docs/tasks/firebase-auth-implementation-tasks.md`
- **Task Checklist**: `.tasks/firebase-auth-integration.md`
- **Figma Plugin Guide**: `docs/guides/figma-plugin-firebase-auth.md`

---

## Notes

### Architecture Decision
Kept existing GCP infrastructure (Cloud Run, Firestore, Cloud Storage, Cloud Tasks) and only added Firebase Auth for OAuth. Minimal changes, maximum benefit.

### Backward Compatibility
Service account fallback remains for:
- PPTX export (no auth required)
- Testing without Firebase
- Graceful degradation

### Security
- Tokens encrypted with Fernet (AES-256)
- Tokens deleted after use
- Never logged (only hashes)
- Minimal OAuth scopes

---

**Implementation Complete**: Phase 2-4 ✅
**Ready for**: Phase 1 Firebase Console Setup → Testing → Deployment
**Next Action**: Complete Phase 1 manual setup steps above
