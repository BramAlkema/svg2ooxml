# Firebase Auth Integration - Tasks

**Feature**: Firebase Authentication for Distributed Google Slides Export
**Spec**: Historical app plan; no standalone app spec has been restored yet.
**Status**: 🔴 Not Started
**Estimated Time**: 10-14 hours
**Sprint**: TBD

---

## Overview

Enable distributed Google Slides export by implementing Firebase Authentication with Google OAuth. This allows users to export SVG content to their own Google Slides workspaces.

**Problem**: Service accounts have 0-byte Drive storage quota (2024+ policy)
**Solution**: User authentication via Firebase Auth with OAuth tokens

---

## Task Hierarchy

```
Phase 1: Firebase Setup (1-2h)
├── 1.1 Create Firebase Project
├── 1.2 Enable Google Sign-In
├── 1.3 Configure OAuth Consent
├── 1.4 Add Authorized Domains
├── 1.5 Generate Web Config
├── 1.6 Create Service Account
└── 1.7 Create Secret Manager Secrets

Phase 2: API Authentication (3-4h)
├── 2.1 Add Dependencies
├── 2.2 Create Firebase Module
├── 2.3 Create Encryption Module
├── 2.4 Create Auth Middleware
├── 2.5 Update Export Endpoint
└── 2.6 Initialize on Startup

Phase 3: Drive Integration (2-3h)
├── 3.1 Update Export Service
├── 3.2 Update Background Tasks
├── 3.3 Update Slides Publisher
└── 3.4 Update Process Job

Phase 4: Deployment (1h)
├── 4.1 Update cloudbuild.yaml
└── 4.2 Update GitHub Actions

Phase 5: Testing & Docs (2-3h)
├── 5.1 Write Unit Tests
├── 5.2 Write Integration Tests
├── 5.3 Update Test Scripts
└── 5.4 Documentation Review
```

---

## Phase 1: Firebase Setup

**Total Time**: 1-2 hours
**Status**: ⬜ Not Started
**Blocking**: Yes (required for all other phases)

### Task 1.1: Create Firebase Project

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: DevOps/Backend
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P0 (Blocking)

**Steps**:
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Add project"
3. Select existing GCP project: `svg2ooxml`
4. Disable Google Analytics (optional)
5. Create project

**Acceptance Criteria**:
- [ ] Firebase project created and linked to GCP
- [ ] Project ID: `svg2ooxml`
- [ ] Can access in Firebase Console

**Outputs**:
- Firebase project ID
- Firebase Console URL

**Blockers**: None

---

### Task 1.2: Enable Google Sign-In Provider

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: DevOps/Backend
- [ ] **Duration**: 20 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 1.1

**Steps**:
1. Firebase Console → Authentication → Sign-in method
2. Enable "Google" provider
3. Set public-facing name: "svg2ooxml"
4. Set support email
5. Save configuration

**Acceptance Criteria**:
- [ ] Google Sign-In enabled
- [ ] Provider shows "Enabled" status

**Outputs**:
- OAuth client ID (auto-generated)

**Blockers**: Task 1.1

---

### Task 1.3: Configure OAuth Consent Screen

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: DevOps/Backend
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 1.2

**Steps**:
1. Go to GCP Console → OAuth consent screen
2. Select user type: **External** (for all Google users)
3. Fill application details:
   - App name: "svg2ooxml"
   - User support email
   - Authorized domains: `a.run.app`
4. Add scopes:
   - `https://www.googleapis.com/auth/drive.file`
   - `https://www.googleapis.com/auth/presentations`
5. Add scope explanations
6. Add test users (for Testing mode)

**Acceptance Criteria**:
- [ ] Consent screen configured
- [ ] Required scopes added
- [ ] Test users added

**Outputs**:
- OAuth consent screen URL
- List of test user emails

**Notes**:
- App starts in "Testing" mode (100 users max)
- For public launch: submit for verification (1-2 weeks)

**Blockers**: Task 1.2

---

### Task 1.4: Add Authorized Domains

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: DevOps/Backend
- [ ] **Duration**: 10 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 1.1

**Steps**:
1. Firebase Console → Authentication → Settings
2. Under "Authorized domains", add:
   - `svg2ooxml-export-sghya3t5ya-ew.a.run.app`
   - `localhost` (for local dev)
   - Figma plugin domain: **TBD** (get from plugin team)
3. Save

**Acceptance Criteria**:
- [ ] Cloud Run domain added
- [ ] Localhost added
- [ ] Figma domain added (once known)

**Outputs**:
- List of authorized domains

**Blockers**: Task 1.1

**Questions**:
- ⚠️ What is the Figma plugin domain?

---

### Task 1.5: Generate Web App Config

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: DevOps/Backend
- [ ] **Duration**: 10 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 1.1

**Steps**:
1. Firebase Console → Project settings
2. Scroll to "Your apps"
3. Click "Add app" → Web
4. Register app:
   - App nickname: "svg2ooxml-web"
   - Firebase Hosting: No
5. Copy Firebase config object

**Acceptance Criteria**:
- [ ] Web app registered
- [ ] Config object saved to `apps/figma2gslides/docs/firebase-web-config.json`

**Outputs**:
- `apps/figma2gslides/docs/firebase-web-config.json` with:
  ```json
  {
    "apiKey": "...",
    "authDomain": "svg2ooxml.firebaseapp.com",
    "projectId": "svg2ooxml",
    "storageBucket": "svg2ooxml.appspot.com",
    "messagingSenderId": "...",
    "appId": "..."
  }
  ```

**Blockers**: Task 1.1

---

### Task 1.6: Create Firebase Service Account

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: DevOps/Backend
- [ ] **Duration**: 15 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 1.1

**Steps**:
1. GCP Console → IAM & Admin → Service Accounts
2. Find Firebase service account: `firebase-adminsdk-xxxxx@svg2ooxml.iam.gserviceaccount.com`
3. Click service account → Keys tab
4. Add key → Create new key → JSON
5. Download JSON key file
6. **SECURITY**: Store in password manager (never commit)

**Acceptance Criteria**:
- [ ] Service account key downloaded
- [ ] Key stored securely (not in repo)
- [ ] Key name: `firebase-service-account.json`

**Outputs**:
- `firebase-service-account.json` (secure storage only)

**Security Notes**:
- ⚠️ Never commit this file to git
- ⚠️ Add to `.gitignore` if not already
- ⚠️ Store in password manager or secure vault

**Blockers**: Task 1.1

---

### Task 1.7: Create Secret Manager Secrets

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: DevOps/Backend
- [ ] **Duration**: 15 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 1.6

**Steps**:
```bash
# 1. Enable Secret Manager API
gcloud services enable secretmanager.googleapis.com --project=svg2ooxml

# 2. Create secret for Firebase service account
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

# 6. Clean up local files
rm firebase-service-account.json token-key.txt
```

**Acceptance Criteria**:
- [ ] Secret Manager API enabled
- [ ] `firebase-service-account` secret created
- [ ] `token-encryption-key` secret created
- [ ] Service account has `secretAccessor` role on both secrets
- [ ] Local key files deleted

**Outputs**:
- Secret names in GCP Secret Manager
- IAM policy bindings

**Blockers**: Task 1.6

---

## Phase 2: API Authentication

**Total Time**: 3-4 hours
**Status**: ⬜ Not Started
**Depends on**: Phase 1 completion

### Task 2.1: Add Dependencies

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 15 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Phase 1

**Files to Modify**:
- `requirements.txt`
- `pyproject.toml`

**Changes**:

**requirements.txt**:
```diff
+ firebase-admin>=6.5.0
+ google-auth>=2.28.0
+ cryptography>=42.0.0
```

**pyproject.toml**:
```diff
[project.optional-dependencies]
api = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
+   "firebase-admin>=6.5.0",
+   "google-auth>=2.28.0",
+   "cryptography>=42.0.0",
]
```

**Steps**:
1. Update `requirements.txt`
2. Update `pyproject.toml`
3. Run: `pip install -e .[api,cloud,slides]`
4. Verify imports work

**Acceptance Criteria**:
- [ ] Dependencies added to both files
- [ ] `pip install` succeeds
- [ ] Can import: `import firebase_admin`
- [ ] Can import: `from google.auth import credentials`
- [ ] Can import: `from cryptography.fernet import Fernet`

**Blockers**: Phase 1 completion

---

### Task 2.2: Create Firebase Initialization Module

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 2.1

**File to Create**: `src/figma2gslides/api/auth/firebase.py`

**Implementation**: See detailed code in `firebase-auth-implementation-tasks.md` Task 2.2

**Functions**:
- `initialize_firebase()` - Initialize Firebase Admin SDK
- `verify_id_token(id_token: str)` - Verify Firebase ID token

**Acceptance Criteria**:
- [ ] File created at `src/figma2gslides/api/auth/firebase.py`
- [ ] `initialize_firebase()` works with service account
- [ ] `verify_id_token()` validates tokens correctly
- [ ] Appropriate logging (info, warning, error)
- [ ] Type hints and docstrings present
- [ ] Handles errors gracefully

**Tests**:
- [ ] `tests/unit/api/auth/test_firebase.py` created (Task 5.1)

**Blockers**: Task 2.1

---

### Task 2.3: Create Token Encryption Module

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 2.1

**File to Create**: `src/figma2gslides/api/auth/encryption.py`

**Implementation**: See detailed code in `firebase-auth-implementation-tasks.md` Task 2.3

**Functions**:
- `encrypt_token(token: str)` - Encrypt OAuth token
- `decrypt_token(encrypted_token: str)` - Decrypt stored token
- `generate_encryption_key()` - Generate new Fernet key

**Acceptance Criteria**:
- [ ] File created at `src/figma2gslides/api/auth/encryption.py`
- [ ] Encrypt/decrypt roundtrip works
- [ ] Invalid key raises ValueError
- [ ] Tampered token raises InvalidToken
- [ ] Appropriate logging

**Tests**:
- [ ] `tests/unit/api/auth/test_encryption.py` created (Task 5.1)

**Blockers**: Task 2.1

---

### Task 2.4: Create Authentication Middleware

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 45 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 2.2

**File to Create**: `src/figma2gslides/api/auth/middleware.py`

**Implementation**: See detailed code in `firebase-auth-implementation-tasks.md` Task 2.4

**Functions**:
- `verify_firebase_token()` - FastAPI dependency for token verification

**Acceptance Criteria**:
- [ ] File created at `src/figma2gslides/api/auth/middleware.py`
- [ ] Works as FastAPI dependency
- [ ] Returns user info on valid token
- [ ] Raises 401 on invalid token
- [ ] Raises 401 on expired token
- [ ] Logs authentication events

**Tests**:
- [ ] `tests/unit/api/auth/test_middleware.py` created (Task 5.1)

**Blockers**: Task 2.2

---

### Task 2.5: Update Export Endpoint for Authentication

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 2.4

**File to Modify**: `src/figma2gslides/api/routes/export.py`

**Changes**:
```diff
+ from ..auth.middleware import verify_firebase_token

@router.post(
    "",
    response_model=ExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
+   responses={
+       401: {"description": "Unauthorized - Invalid or missing token"},
+       403: {"description": "Forbidden - Insufficient permissions"},
+   }
)
async def create_export(
    request: ExportRequest,
+   user: dict = Depends(verify_firebase_token)  # NEW
) -> ExportResponse:
+   """Create export job (requires authentication).
+
+   Authentication:
+       Requires Firebase ID token in Authorization header
+   """
    # ... existing code
+   job_id = export_service.create_job(
+       frames=request.frames,
+       output_format=request.output_format,
+       user=user  # NEW
+   )
```

**Acceptance Criteria**:
- [ ] Endpoint requires Authorization header
- [ ] Returns 401 if no token
- [ ] Returns 401 if invalid token
- [ ] Returns 202 with valid token
- [ ] User info passed to export service

**Tests**:
- [ ] `tests/integration/test_export_auth.py` created (Task 5.2)

**Blockers**: Task 2.4

---

### Task 2.6: Initialize Firebase on App Startup

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 15 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 2.2

**File to Modify**: `src/figma2gslides/app.py`

**Changes**:
```diff
+ from figma2gslides.api.auth.firebase import initialize_firebase

+ @app.on_event("startup")
+ async def startup_event():
+     """Initialize Firebase Admin SDK on startup."""
+     try:
+         initialize_firebase()
+         logger.info("Application startup complete")
+     except Exception as e:
+         logger.error(f"Startup failed: {e}")
+         raise
```

**Acceptance Criteria**:
- [ ] Firebase initialized on app start
- [ ] Startup logs show success
- [ ] App fails to start if Firebase init fails

**Tests**:
- [ ] Manual: Run `uvicorn figma2gslides.app:app` and check logs

**Blockers**: Task 2.2

---

## Phase 3: Drive API Integration

**Total Time**: 2-3 hours
**Status**: ⬜ Not Started
**Depends on**: Phase 2 completion

### Task 3.1: Update Export Service for User Credentials

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 45 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 2.5, Task 2.3

**File to Modify**: `src/figma2gslides/api/services/export_service.py`

**Changes**:
```diff
def create_job(
    self,
    frames: List[Frame],
    output_format: str,
    figma_file_id: str = None,
    figma_file_name: str = None,
+   user: dict = None  # NEW
) -> str:
    # ... existing job_data

+   # NEW: Add user info if authenticated
+   if user:
+       from ..auth.encryption import encrypt_token
+
+       job_data["user"] = {
+           "uid": user["uid"],
+           "email": user.get("email"),
+           "token_hash": user["token_hash"]
+       }
+
+       job_data["auth_token_encrypted"] = encrypt_token(user["token"])
```

**Acceptance Criteria**:
- [ ] User info stored in job document
- [ ] Token encrypted before storage
- [ ] Works with or without user (backward compat)
- [ ] Proper logging

**Tests**:
- [ ] `tests/unit/api/services/test_export_service.py` updated

**Blockers**: Task 2.5, Task 2.3

---

### Task 3.2: Update Background Tasks for Token Handling

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 3.1

**Files to Modify**:
- `src/figma2gslides/api/background/tasks.py`
- `src/figma2gslides/api/routes/tasks.py`

**Changes in `tasks.py`**:
```diff
def enqueue_export_job(job_id: str) -> None:
    job_doc = db.collection("jobs").document(job_id).get()
    job_data = job_doc.to_dict()

    task_data = {"job_id": job_id}

+   # Include encrypted token if present
+   if "auth_token_encrypted" in job_data:
+       task_data["auth_token_encrypted"] = job_data["auth_token_encrypted"]
```

**Changes in `routes/tasks.py`**:
```diff
@router.post("/process-export")
async def process_export_task(request: TaskRequest):
+   encrypted_token = request.auth_token_encrypted
+
+   user_token = None
+   if encrypted_token:
+       from ..auth.encryption import decrypt_token
+       user_token = decrypt_token(encrypted_token)

+   export_service.process_job(job_id, user_token=user_token)

+   # Delete encrypted token after processing
+   if encrypted_token:
+       db.collection("jobs").document(job_id).update({
+           "auth_token_encrypted": firestore.DELETE_FIELD
+       })
```

**Acceptance Criteria**:
- [ ] Encrypted token passed to Cloud Tasks
- [ ] Token decrypted before processing
- [ ] Token deleted after job completion
- [ ] Works without token (backward compat)

**Tests**:
- [ ] `tests/integration/test_background_tasks_auth.py` created

**Blockers**: Task 3.1

---

### Task 3.3: Update Slides Publisher for User Credentials

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 1 hour
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 3.2

**File to Modify**: `src/figma2gslides/api/services/slides_publisher.py`

**Major Changes**:
```diff
+ from google.oauth2.credentials import Credentials as UserCredentials

def upload_pptx_to_slides(
    pptx_path: str,
    file_name: str,
+   user_token: str = None  # NEW
) -> dict:
+   if user_token:
+       credentials = _build_user_credentials(user_token)
+   else:
+       credentials = _get_service_account_credentials()

    # ... rest of function

+ def _build_user_credentials(id_token: str) -> UserCredentials:
+     """Build user credentials from Firebase ID token."""
+     return UserCredentials(token=id_token)

+ def _get_service_account_credentials() -> Credentials:
+     """Get service account credentials (fallback)."""
+     # ... existing service account logic
```

**Acceptance Criteria**:
- [ ] Accepts optional user_token parameter
- [ ] Uses user credentials when token provided
- [ ] Falls back to service account when no token
- [ ] Uploads to user's Drive successfully
- [ ] Proper error handling for expired tokens

**Tests**:
- [ ] `tests/integration/test_slides_publisher_user_auth.py` created

**Blockers**: Task 3.2

---

### Task 3.4: Update Export Service Process Job

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 3.3

**File to Modify**: `src/figma2gslides/api/services/export_service.py`

**Changes**:
```diff
def process_job(
    self,
    job_id: str,
+   user_token: str = None
) -> None:
    # ... existing logic

    if output_format == "slides":
        slides_info = slides_publisher.upload_pptx_to_slides(
            pptx_path=pptx_path,
            file_name=file_name,
+           user_token=user_token  # NEW
        )
```

**Acceptance Criteria**:
- [ ] User token passed to slides publisher
- [ ] Works with and without token
- [ ] Job metadata updated correctly

**Tests**:
- [ ] `tests/integration/test_export_service_user_auth.py` created

**Blockers**: Task 3.3

---

## Phase 4: Deployment Configuration

**Total Time**: 1 hour
**Status**: ⬜ Not Started
**Depends on**: Phase 3 completion

### Task 4.1: Update cloudbuild.yaml

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: DevOps
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Task 1.7

**File to Modify**: `cloudbuild.yaml`

**Changes**:
```diff
- name: gcr.io/google.com/cloudsdktool/cloud-sdk
  args:
    - gcloud
    - run
    - deploy
    - $_SERVICE
    # ... existing args
-   - --set-env-vars=PYTHONPATH=/workspace/src,GCP_PROJECT=$PROJECT_ID,...
+   - --set-env-vars=PYTHONPATH=/workspace/src,GCP_PROJECT=$PROJECT_ID,CLOUD_TASKS_LOCATION=$_REGION,CLOUD_TASKS_QUEUE=svg2ooxml-jobs,FIREBASE_PROJECT_ID=svg2ooxml,FIREBASE_SERVICE_ACCOUNT_PATH=/secrets/firebase-service-account
+   - --update-secrets=/secrets/firebase-service-account=firebase-service-account:latest,TOKEN_ENCRYPTION_KEY=token-encryption-key:latest
```

**Acceptance Criteria**:
- [ ] Secrets mounted in Cloud Run
- [ ] Environment variables set correctly
- [ ] Build succeeds
- [ ] Deployment succeeds

**Tests**:
- [ ] Deploy and check Cloud Run environment
- [ ] Verify secrets mounted at `/secrets/firebase-service-account`
- [ ] Verify `TOKEN_ENCRYPTION_KEY` environment variable set

**Blockers**: Task 1.7 (secrets must exist)

---

### Task 4.2: Update GitHub Actions Workflow

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: DevOps
- [ ] **Duration**: 15 minutes
- [ ] **Priority**: P1 (Important)
- [ ] **Depends on**: Phase 3

**File to Modify**: `.github/workflows/test-suite.yml`

**Changes**:
```diff
- name: Run test suite
+ env:
+   FIREBASE_AUTH_EMULATOR_HOST: localhost:9099
+   TOKEN_ENCRYPTION_KEY: dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcwo=
  run: |
    python -m pytest -m "not visual" --maxfail=1 --disable-warnings
```

**Acceptance Criteria**:
- [ ] Tests run successfully in CI
- [ ] Test encryption key provided
- [ ] No Firebase errors in CI

**Tests**:
- [ ] Push to trigger GitHub Actions
- [ ] Verify all tests pass

**Blockers**: Phase 3 completion

---

## Phase 5: Testing & Documentation

**Total Time**: 2-3 hours
**Status**: ⬜ Not Started
**Depends on**: Phase 3 completion

### Task 5.1: Write Unit Tests for Auth Modules

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 1 hour
- [ ] **Priority**: P0 (Blocking)
- [ ] **Depends on**: Tasks 2.2, 2.3, 2.4

**Files to Create**:
1. `tests/unit/api/auth/test_firebase.py`
2. `tests/unit/api/auth/test_encryption.py`
3. `tests/unit/api/auth/test_middleware.py`

**Test Coverage**:
- [ ] Firebase: valid token, expired token, invalid signature
- [ ] Encryption: roundtrip, invalid key, tampered ciphertext
- [ ] Middleware: valid token, missing token, invalid token

**Acceptance Criteria**:
- [ ] All unit tests pass
- [ ] Code coverage > 80% for auth modules
- [ ] Tests run in CI (GitHub Actions)

**Blockers**: Tasks 2.2, 2.3, 2.4

---

### Task 5.2: Write Integration Tests

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 1 hour
- [ ] **Priority**: P1 (Important)
- [ ] **Depends on**: Phase 3

**Files to Create**:
1. `tests/integration/test_export_auth.py`
   - Test export with valid token
   - Test export without token (401)
   - Test export with invalid token (401)

2. `tests/integration/test_slides_user_auth.py`
   - Test Slides upload with user credentials
   - Verify presentation in test user's Drive
   - Cleanup after test

**Acceptance Criteria**:
- [ ] All integration tests pass
- [ ] Tests use real Firebase Auth (or emulator)
- [ ] Tests clean up resources

**Blockers**: Phase 3 completion

---

### Task 5.3: Update Test Scripts

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P1 (Important)
- [ ] **Depends on**: Task 1.5

**File to Modify**: `test_slides_api.py`

**Changes**:
```diff
+ def get_test_user_token() -> str:
+     """Get Firebase ID token for testing."""
+     return input("Enter Firebase ID token: ")

def create_slides_export_job(base_url: str) -> str:
+   id_token = get_test_user_token()
+
    response = requests.post(
        f"{base_url}/api/v1/export",
        json=request_data,
        headers={
            "Content-Type": "application/json",
+           "Authorization": f"Bearer {id_token}"
        }
    )
```

**Acceptance Criteria**:
- [ ] Script prompts for Firebase ID token
- [ ] Script includes Authorization header
- [ ] End-to-end test works with user auth

**Blockers**: Task 1.5 (need Firebase config)

---

### Task 5.4: Documentation Review

- [ ] **Status**: ⬜ Not Started
- [ ] **Owner**: Backend
- [ ] **Duration**: 30 minutes
- [ ] **Priority**: P2 (Nice to have)
- [ ] **Depends on**: All tasks

**Review Documents**:
- [ ] Restore a first-class Firebase auth app spec
- [ ] `apps/figma2gslides/docs/firebase-auth-implementation-tasks.md` - Up to date?
- [ ] `apps/figma2gslides/figma-plugin-firebase-auth.md` - Clear instructions?
- [ ] API documentation - Includes auth requirements?

**Acceptance Criteria**:
- [ ] All docs reviewed and updated
- [ ] No broken links
- [ ] Code examples accurate
- [ ] Troubleshooting section complete

**Blockers**: All implementation tasks

---

## Pre-Deployment Checklist

Before deploying to production:

- [ ] **Phase 1**: All Firebase setup tasks complete
- [ ] **Phase 2**: API authentication implemented
- [ ] **Phase 3**: Drive integration complete
- [ ] **Phase 4**: Deployment configs updated
- [ ] **Phase 5**: All tests passing
- [ ] **Unit tests**: Coverage > 80%
- [ ] **Integration tests**: All passing
- [ ] **Manual test**: End-to-end with real account succeeds
- [ ] **Security**: No tokens in logs
- [ ] **Security**: Secrets in Secret Manager
- [ ] **Cost**: Verify free tier usage
- [ ] **Docs**: All documentation updated

---

## Post-Deployment Verification

After deploying:

- [ ] Cloud Run deployment succeeds
- [ ] API health check passes
- [ ] Firebase initializes on startup (check logs)
- [ ] Test authenticated endpoint with curl + token
- [ ] Run `test_slides_api.py` with real account
- [ ] Verify Slides created in test user's Drive
- [ ] Check Cloud Tasks queue processing
- [ ] Monitor logs for errors
- [ ] Verify temporary file cleanup (next day)

---

## Rollback Plan

If deployment fails:

1. [ ] Revert to previous Cloud Run revision
2. [ ] Investigate failure in logs
3. [ ] Fix issues locally
4. [ ] Re-test before re-deploying

**Command**:
```bash
gcloud run services update-traffic svg2ooxml-export \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region=europe-west1
```

---

## Success Metrics

Track these after deployment:

**Week 1**:
- [ ] 0 authentication errors (excluding user denials)
- [ ] > 95% Slides upload success rate
- [ ] < 200ms token verification latency (p95)
- [ ] 0 production incidents

**Month 1**:
- [ ] > 100 successful Slides exports
- [ ] > 90% user authentication success rate
- [ ] < 5% token expiration errors
- [ ] Stay within free tier (< 1,000 MAU)

---

## Open Questions / Blockers

Track unresolved questions:

1. **Figma plugin domain**: What domain will the plugin use?
   - **Status**: ⚠️ Pending
   - **Needed for**: Task 1.4
   - **Action**: Ask plugin team

2. **Privacy policy URL**: Where to host privacy policy?
   - **Status**: ⚠️ Pending
   - **Needed for**: Task 1.3 (OAuth consent screen)
   - **Action**: Decide on hosting location

3. **Test user accounts**: Which Google accounts for testing?
   - **Status**: ⚠️ Pending
   - **Needed for**: Task 1.3, Task 5.2
   - **Action**: Create or designate test accounts

---

## Notes

**Architecture Decision**: Keep existing GCP infrastructure (Cloud Run, Firestore, Cloud Storage, Cloud Tasks) and only add Firebase Auth for OAuth.

**Cost Impact**: No change - stays within free tier (~$0.14/month)

**Security**: Tokens encrypted with Fernet, deleted after use, never logged

**Backward Compatibility**: Service account fallback remains for testing

---

**Last Updated**: 2025-11-02
**Version**: 1.0.0
**Status**: Ready for implementation
