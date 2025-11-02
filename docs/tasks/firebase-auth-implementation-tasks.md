# Firebase Auth Implementation - Task Breakdown

**Feature**: Firebase Authentication for Distributed Google Slides Export
**Spec**: [docs/specs/firebase-auth-google-slides-export.md](../specs/firebase-auth-google-slides-export.md)
**Estimated Total Time**: 10-14 hours
**Target Completion**: TBD

---

## Phase 1: Firebase Setup ⏱️ 1-2 hours

### Task 1.1: Create Firebase Project
**Owner**: DevOps/Backend
**Duration**: 30 minutes
**Priority**: P0 (Blocking)

**Steps**:
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Add project"
3. Select existing GCP project: `svg2ooxml`
4. Enable Google Analytics: No (optional)
5. Create project

**Acceptance Criteria**:
- [ ] Firebase project created and linked to GCP project
- [ ] Firebase project ID matches GCP project: `svg2ooxml`
- [ ] Can access project in Firebase Console

**Outputs**:
- Firebase project ID
- Firebase Console URL

---

### Task 1.2: Enable Google Sign-In Provider
**Owner**: DevOps/Backend
**Duration**: 20 minutes
**Priority**: P0 (Blocking)

**Steps**:
1. In Firebase Console → Authentication → Sign-in method
2. Click "Google" provider
3. Enable the provider
4. Set public-facing name: "svg2ooxml"
5. Set support email: (your email)
6. Save

**Acceptance Criteria**:
- [ ] Google Sign-In provider enabled
- [ ] Provider shows as "Enabled" in console

**Outputs**:
- OAuth client ID (auto-generated)

---

### Task 1.3: Configure OAuth Consent Screen
**Owner**: DevOps/Backend
**Duration**: 30 minutes
**Priority**: P0 (Blocking)

**Steps**:
1. Go to [GCP Console → APIs & Services → OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
2. Select user type:
   - Internal: Only for Google Workspace users (NOT RECOMMENDED)
   - External: For all Google users (RECOMMENDED)
3. Fill in application details:
   - App name: "svg2ooxml"
   - User support email: (your email)
   - App logo: (optional)
   - App domain: (Cloud Run URL)
   - Authorized domains: `a.run.app`
   - Developer contact: (your email)
4. Add scopes:
   - `https://www.googleapis.com/auth/drive.file`
   - `https://www.googleapis.com/auth/presentations`
5. Scope explanations:
   - Drive.file: "Create Google Slides presentations in your Drive"
   - Presentations: "Build presentation slides from your design"
6. Test users (for External - Testing mode):
   - Add your email for initial testing
7. Submit for verification (later, for production)

**Acceptance Criteria**:
- [ ] OAuth consent screen configured
- [ ] Required scopes added
- [ ] Test users added (if in Testing mode)

**Outputs**:
- OAuth consent screen URL
- Scope verification status

**Notes**:
- External apps start in "Testing" mode (100 users max)
- For public launch, submit for verification (can take 1-2 weeks)

---

### Task 1.4: Add Authorized Domains
**Owner**: DevOps/Backend
**Duration**: 10 minutes
**Priority**: P0 (Blocking)

**Steps**:
1. Firebase Console → Authentication → Settings
2. Under "Authorized domains", add:
   - `svg2ooxml-export-sghya3t5ya-ew.a.run.app` (Cloud Run)
   - `localhost` (for local development)
   - Figma plugin domain: TBD (ask plugin team)
3. Save

**Acceptance Criteria**:
- [ ] Cloud Run domain added
- [ ] Localhost added for development
- [ ] Figma plugin domain added (once known)

**Outputs**:
- List of authorized domains

---

### Task 1.5: Generate Web App Config
**Owner**: DevOps/Backend
**Duration**: 10 minutes
**Priority**: P0 (Blocking)

**Steps**:
1. Firebase Console → Project settings (gear icon)
2. Scroll to "Your apps"
3. Click "Add app" → Web (</> icon)
4. Register app:
   - App nickname: "svg2ooxml-web"
   - Firebase Hosting: No
5. Copy the Firebase config object:
   ```javascript
   const firebaseConfig = {
     apiKey: "...",
     authDomain: "svg2ooxml.firebaseapp.com",
     projectId: "svg2ooxml",
     storageBucket: "svg2ooxml.appspot.com",
     messagingSenderId: "...",
     appId: "..."
   };
   ```

**Acceptance Criteria**:
- [ ] Web app registered in Firebase
- [ ] Config object copied and saved

**Outputs**:
- `firebase-web-config.json` (save to docs/setup/)

---

### Task 1.6: Create Firebase Service Account
**Owner**: DevOps/Backend
**Duration**: 15 minutes
**Priority**: P0 (Blocking)

**Steps**:
1. Go to [GCP Console → IAM & Admin → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Find or create service account: `firebase-adminsdk-xxxxx@svg2ooxml.iam.gserviceaccount.com`
   - Firebase creates this automatically
3. Click on the service account → Keys tab
4. Add key → Create new key → JSON
5. Download the JSON key file
6. **SECURITY**: Store securely, never commit to git

**Acceptance Criteria**:
- [ ] Service account key downloaded
- [ ] Key file saved to secure location (not in repo)

**Outputs**:
- `firebase-service-account.json` (store in password manager)

---

### Task 1.7: Create Secret Manager Secrets
**Owner**: DevOps/Backend
**Duration**: 15 minutes
**Priority**: P0 (Blocking)

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

# 6. Clean up local key files
rm firebase-service-account.json token-key.txt
```

**Acceptance Criteria**:
- [ ] `firebase-service-account` secret created
- [ ] `token-encryption-key` secret created
- [ ] Service account has `secretAccessor` role on both secrets
- [ ] Local key files deleted

**Outputs**:
- Secret names in GCP Secret Manager

---

## Phase 2: API Authentication ⏱️ 3-4 hours

### Task 2.1: Add Dependencies
**Owner**: Backend
**Duration**: 15 minutes
**Priority**: P0 (Blocking)

**Steps**:
1. Update `requirements.txt`:
   ```txt
   firebase-admin>=6.5.0
   google-auth>=2.28.0
   cryptography>=42.0.0
   ```

2. Update `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   api = [
       "fastapi>=0.104.0",
       "uvicorn[standard]>=0.24.0",
       "firebase-admin>=6.5.0",
       "google-auth>=2.28.0",
       "cryptography>=42.0.0",
   ]
   ```

3. Reinstall dependencies:
   ```bash
   pip install -e .[api,cloud,slides]
   ```

**Acceptance Criteria**:
- [ ] Dependencies added to requirements.txt
- [ ] Dependencies added to pyproject.toml
- [ ] `pip install` succeeds
- [ ] Can import: `import firebase_admin`, `from google.auth import credentials`, `from cryptography.fernet import Fernet`

**Outputs**:
- Updated requirements.txt
- Updated pyproject.toml

---

### Task 2.2: Create Firebase Initialization Module
**Owner**: Backend
**Duration**: 30 minutes
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/api/auth/firebase.py`

**Code**:
```python
"""Firebase Admin SDK initialization and token verification."""
import logging
import os
from typing import Dict

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

logger = logging.getLogger(__name__)


def initialize_firebase() -> None:
    """Initialize Firebase Admin SDK.

    Uses service account credentials from Secret Manager
    (mounted at /secrets/firebase-service-account).
    """
    if firebase_admin._apps:
        logger.info("Firebase already initialized")
        return

    try:
        # Option 1: Use service account key file (from Secret Manager)
        key_path = os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_PATH",
            "/secrets/firebase-service-account"
        )

        if os.path.exists(key_path):
            cred = credentials.Certificate(key_path)
            logger.info(f"Using service account from {key_path}")
        else:
            # Option 2: Application Default Credentials (fallback)
            cred = credentials.ApplicationDefault()
            logger.info("Using Application Default Credentials")

        firebase_admin.initialize_app(cred, {
            'projectId': os.getenv('FIREBASE_PROJECT_ID', 'svg2ooxml'),
        })

        logger.info("Firebase Admin SDK initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        raise


def verify_id_token(id_token: str) -> Dict[str, any]:
    """Verify Firebase ID token and return decoded claims.

    Args:
        id_token: Firebase ID token from client

    Returns:
        Dictionary with user claims:
        - uid: User ID
        - email: User email (if available)
        - email_verified: Whether email is verified
        - auth_time: Authentication timestamp
        - exp: Expiration timestamp

    Raises:
        firebase_admin.auth.InvalidIdTokenError: If token is invalid
        firebase_admin.auth.ExpiredIdTokenError: If token is expired
        firebase_admin.auth.RevokedIdTokenError: If token is revoked
    """
    try:
        # Verify the token (includes signature, expiration, etc.)
        decoded_token = firebase_auth.verify_id_token(id_token)

        logger.info(
            "Token verified successfully",
            extra={
                "user_id": decoded_token["uid"],
                "email": decoded_token.get("email", "unknown")
            }
        )

        return decoded_token

    except firebase_auth.ExpiredIdTokenError:
        logger.warning("Token verification failed: expired")
        raise
    except firebase_auth.InvalidIdTokenError as e:
        logger.warning(f"Token verification failed: invalid - {e}")
        raise
    except firebase_auth.RevokedIdTokenError:
        logger.warning("Token verification failed: revoked")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        raise
```

**Acceptance Criteria**:
- [ ] File created at correct path
- [ ] `initialize_firebase()` function works with service account
- [ ] `verify_id_token()` function validates tokens correctly
- [ ] Appropriate logging for success and failure cases
- [ ] Type hints and docstrings present

**Tests**:
- `tests/unit/api/auth/test_firebase.py`

---

### Task 2.3: Create Token Encryption Module
**Owner**: Backend
**Duration**: 30 minutes
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/api/auth/encryption.py`

**Code**:
```python
"""Token encryption/decryption utilities for secure storage."""
import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """Get encryption key from environment/secret.

    Raises:
        ValueError: If TOKEN_ENCRYPTION_KEY not set
    """
    key_b64 = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key_b64:
        raise ValueError("TOKEN_ENCRYPTION_KEY environment variable not set")

    try:
        return base64.urlsafe_b64decode(key_b64)
    except Exception as e:
        raise ValueError(f"Invalid TOKEN_ENCRYPTION_KEY format: {e}")


def encrypt_token(token: str) -> str:
    """Encrypt OAuth token for secure storage.

    Args:
        token: OAuth token to encrypt

    Returns:
        Base64-encoded encrypted token

    Raises:
        ValueError: If encryption fails
    """
    try:
        fernet = Fernet(_get_encryption_key())
        encrypted = fernet.encrypt(token.encode('utf-8'))
        encrypted_b64 = base64.urlsafe_b64encode(encrypted).decode('utf-8')

        logger.debug("Token encrypted successfully")
        return encrypted_b64

    except Exception as e:
        logger.error(f"Token encryption failed: {e}")
        raise ValueError(f"Failed to encrypt token: {e}")


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt stored OAuth token.

    Args:
        encrypted_token: Base64-encoded encrypted token

    Returns:
        Decrypted OAuth token

    Raises:
        ValueError: If decryption fails
        InvalidToken: If token is corrupted or key is wrong
    """
    try:
        fernet = Fernet(_get_encryption_key())
        encrypted = base64.urlsafe_b64decode(encrypted_token)
        decrypted = fernet.decrypt(encrypted).decode('utf-8')

        logger.debug("Token decrypted successfully")
        return decrypted

    except InvalidToken:
        logger.error("Token decryption failed: invalid token or wrong key")
        raise
    except Exception as e:
        logger.error(f"Token decryption failed: {e}")
        raise ValueError(f"Failed to decrypt token: {e}")


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key.

    Returns:
        Base64-encoded encryption key (for TOKEN_ENCRYPTION_KEY env var)

    Usage:
        >>> key = generate_encryption_key()
        >>> print(f"TOKEN_ENCRYPTION_KEY={key}")
    """
    key = Fernet.generate_key()
    return base64.urlsafe_b64encode(key).decode('utf-8')
```

**Acceptance Criteria**:
- [ ] File created at correct path
- [ ] Encrypt/decrypt roundtrip works correctly
- [ ] Invalid key raises appropriate error
- [ ] Tampering with encrypted token raises InvalidToken
- [ ] Logging for debug and errors

**Tests**:
- `tests/unit/api/auth/test_encryption.py`

---

### Task 2.4: Create Authentication Middleware
**Owner**: Backend
**Duration**: 45 minutes
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/api/auth/middleware.py`

**Code**:
```python
"""FastAPI authentication middleware using Firebase tokens."""
import hashlib
import logging
from typing import Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .firebase import verify_id_token

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer()


async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, any]:
    """FastAPI dependency to verify Firebase ID token.

    Extracts token from Authorization header, verifies it,
    and returns user information.

    Args:
        credentials: HTTP Bearer credentials from request header

    Returns:
        Dictionary with user info:
        - uid: Firebase user ID
        - email: User email (optional)
        - token: Original ID token (for Drive API calls)
        - token_hash: SHA256 hash of token (for logging)

    Raises:
        HTTPException(401): If token is missing, invalid, or expired

    Usage in endpoint:
        @router.post("/export")
        async def create_export(
            request: ExportRequest,
            user: dict = Depends(verify_firebase_token)
        ):
            # user["token"] contains verified Firebase ID token
            # user["uid"] contains user ID
            pass
    """
    token = credentials.credentials

    try:
        # Verify token with Firebase
        decoded_token = verify_id_token(token)

        # Extract user info
        user_info = {
            "uid": decoded_token["uid"],
            "email": decoded_token.get("email"),
            "token": token,  # Original token for Drive API
            "token_hash": hashlib.sha256(token.encode()).hexdigest()[:16]
        }

        logger.info(
            "User authenticated",
            extra={
                "user_id": user_info["uid"],
                "email": user_info.get("email", "unknown"),
                "token_hash": user_info["token_hash"]
            }
        )

        return user_info

    except Exception as e:
        # Log failure (without full token)
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        logger.warning(
            f"Authentication failed: {type(e).__name__}",
            extra={"token_hash": token_hash, "error": str(e)}
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {type(e).__name__}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Optional: Require specific scopes
async def verify_firebase_token_with_scopes(
    required_scopes: list[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, any]:
    """Verify token and check for required OAuth scopes.

    Note: Firebase ID tokens don't include OAuth scopes.
    This would require storing scope info separately or
    using Google OAuth tokens directly.

    For now, we assume all authenticated users have the
    required scopes (they granted them during sign-in).
    """
    user_info = await verify_firebase_token(credentials)

    # TODO: Implement scope checking if needed
    # This requires storing granted scopes with the token

    return user_info
```

**Acceptance Criteria**:
- [ ] File created at correct path
- [ ] `verify_firebase_token` dependency works with FastAPI
- [ ] Returns user info on valid token
- [ ] Raises 401 on invalid token
- [ ] Raises 401 on expired token
- [ ] Logs authentication events appropriately

**Tests**:
- `tests/unit/api/auth/test_middleware.py`

---

### Task 2.5: Update Export Endpoint for Authentication
**Owner**: Backend
**Duration**: 30 minutes
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/api/routes/export.py`

**Changes**:
```python
# Add imports
from ..auth.middleware import verify_firebase_token

# Update endpoint
@router.post(
    "",
    response_model=ExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - Insufficient permissions"},
    }
)
async def create_export(
    request: ExportRequest,
    user: dict = Depends(verify_firebase_token)  # NEW: Require auth
) -> ExportResponse:
    """Create a new export job (requires authentication).

    Authentication:
        Requires Firebase ID token in Authorization header:
        Authorization: Bearer <firebase-id-token>

    The token must include the following OAuth scopes:
        - https://www.googleapis.com/auth/drive.file
        - https://www.googleapis.com/auth/presentations
    """
    logger.info(
        f"Creating export job for user {user['uid']}",
        extra={
            "output_format": request.output_format,
            "frame_count": len(request.frames),
            "user_id": user["uid"]
        }
    )

    # Create export job (passing user info)
    job_id = export_service.create_job(
        frames=request.frames,
        output_format=request.output_format,
        figma_file_id=request.figma_file_id,
        figma_file_name=request.figma_file_name,
        user=user  # NEW: Pass user info to service
    )

    # ... rest of endpoint
```

**Acceptance Criteria**:
- [ ] Endpoint requires Authorization header
- [ ] Returns 401 if no token provided
- [ ] Returns 401 if invalid token provided
- [ ] Returns 202 with valid token
- [ ] User info passed to export service

**Tests**:
- `tests/integration/test_export_auth.py`

---

### Task 2.6: Initialize Firebase on App Startup
**Owner**: Backend
**Duration**: 15 minutes
**Priority**: P0 (Blocking)

**File**: `main.py`

**Changes**:
```python
# Add imports
from src.svg2ooxml.api.auth.firebase import initialize_firebase

# Add startup event
@app.on_event("startup")
async def startup_event():
    """Initialize Firebase Admin SDK on startup."""
    try:
        initialize_firebase()
        logger.info("Application startup complete")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

# ... rest of file
```

**Acceptance Criteria**:
- [ ] Firebase initialized when app starts
- [ ] Startup logs show successful initialization
- [ ] App fails to start if Firebase init fails

**Tests**:
- Manual: Run `uvicorn main:app` and check logs

---

## Phase 3: Drive API Integration ⏱️ 2-3 hours

### Task 3.1: Update Export Service for User Credentials
**Owner**: Backend
**Duration**: 45 minutes
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/api/services/export_service.py`

**Changes**:
```python
def create_job(
    self,
    frames: List[Frame],
    output_format: str,
    figma_file_id: str = None,
    figma_file_name: str = None,
    user: dict = None  # NEW: User info from auth middleware
) -> str:
    """Create a new export job."""
    job_id = str(uuid.uuid4())

    # Create job document
    job_data = {
        "job_id": job_id,
        "status": "queued",
        "created_at": datetime.utcnow(),
        "output_format": output_format,
        "figma_file_id": figma_file_id,
        "figma_file_name": figma_file_name,
        "frame_count": len(frames),
        "progress": 0.0,
    }

    # NEW: Add user info if authenticated
    if user:
        from .auth.encryption import encrypt_token

        job_data["user"] = {
            "uid": user["uid"],
            "email": user.get("email"),
            "token_hash": user["token_hash"]
        }

        # Encrypt and store token for background processing
        job_data["auth_token_encrypted"] = encrypt_token(user["token"])

        logger.info(
            f"Job created with user authentication",
            extra={"job_id": job_id, "user_id": user["uid"]}
        )

    # ... rest of method
```

**Acceptance Criteria**:
- [ ] User info stored in job document
- [ ] Token encrypted before storage
- [ ] Service works with or without user (backward compat)

**Tests**:
- `tests/unit/api/services/test_export_service.py`

---

### Task 3.2: Update Background Tasks for Token Handling
**Owner**: Backend
**Duration**: 30 minutes
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/api/background/tasks.py`

**Changes**:
```python
def enqueue_export_job(job_id: str) -> None:
    """Enqueue export job for background processing."""
    # Fetch job to get encrypted token
    job_doc = db.collection("jobs").document(job_id).get()
    job_data = job_doc.to_dict()

    # Build task payload
    task_data = {"job_id": job_id}

    # Include encrypted token if present
    if "auth_token_encrypted" in job_data:
        task_data["auth_token_encrypted"] = job_data["auth_token_encrypted"]

    # ... create Cloud Task with task_data
```

**File**: `src/svg2ooxml/api/routes/tasks.py`

**Changes**:
```python
@router.post("/process-export")
async def process_export_task(request: TaskRequest):
    """Process export job (called by Cloud Tasks)."""
    job_id = request.job_id
    encrypted_token = request.auth_token_encrypted  # NEW

    # Decrypt token if present
    user_token = None
    if encrypted_token:
        from ..auth.encryption import decrypt_token
        user_token = decrypt_token(encrypted_token)

    # Process job with user token
    export_service.process_job(job_id, user_token=user_token)

    # Delete encrypted token from job after successful processing
    if encrypted_token:
        db.collection("jobs").document(job_id).update({
            "auth_token_encrypted": firestore.DELETE_FIELD
        })

    return {"status": "success", "job_id": job_id}
```

**Acceptance Criteria**:
- [ ] Encrypted token passed to Cloud Tasks
- [ ] Token decrypted before processing
- [ ] Token deleted after successful processing
- [ ] Works without token (backward compat)

**Tests**:
- `tests/integration/test_background_tasks_auth.py`

---

### Task 3.3: Update Slides Publisher for User Credentials
**Owner**: Backend
**Duration**: 1 hour
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/api/services/slides_publisher.py`

**Major Changes**:
```python
from google.oauth2.credentials import Credentials as UserCredentials
from google.auth.credentials import Credentials

def upload_pptx_to_slides(
    pptx_path: str,
    file_name: str,
    user_token: str = None  # NEW: User OAuth token
) -> dict:
    """Upload PPTX to Google Drive and convert to Slides.

    Args:
        pptx_path: Path to PPTX file
        file_name: Name for the presentation
        user_token: Firebase ID token (for user auth) or None (for service account)

    Returns:
        Dict with presentation info
    """
    try:
        # Build credentials
        if user_token:
            # NEW: Use user credentials
            credentials = _build_user_credentials(user_token)
            logger.info("Using user credentials for Slides upload")
        else:
            # Fallback: Use service account (legacy)
            credentials = _get_service_account_credentials()
            logger.info("Using service account credentials for Slides upload")

        # Build Drive and Slides services
        drive_service = build("drive", "v3", credentials=credentials)
        slides_service = build("slides", "v1", credentials=credentials)

        # Upload PPTX to Drive
        file_metadata = {
            "name": file_name,
            "mimeType": "application/vnd.google-apps.presentation"
        }

        media = MediaFileUpload(
            pptx_path,
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            resumable=True
        )

        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,name,webViewLink"
        ).execute()

        logger.info(
            f"Slides created successfully",
            extra={
                "presentation_id": file["id"],
                "auth_type": "user" if user_token else "service_account"
            }
        )

        return {
            "presentation_id": file["id"],
            "name": file["name"],
            "slides_url": file["webViewLink"],
        }

    except Exception as e:
        logger.error(f"Failed to upload to Slides: {e}")
        raise


def _build_user_credentials(id_token: str) -> UserCredentials:
    """Build user credentials from Firebase ID token.

    Args:
        id_token: Firebase ID token

    Returns:
        Google OAuth2 user credentials
    """
    # Firebase ID tokens can be used directly with Google APIs
    # that support OpenID Connect (like Drive/Slides)
    credentials = UserCredentials(token=id_token)

    # Note: These credentials will expire after 1 hour
    # For long-running jobs, consider implementing refresh logic

    return credentials


def _get_service_account_credentials() -> Credentials:
    """Get service account credentials (legacy/fallback)."""
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        scopes=[
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/presentations",
        ]
    )
    return credentials
```

**Acceptance Criteria**:
- [ ] Accepts optional user_token parameter
- [ ] Uses user credentials when token provided
- [ ] Falls back to service account when no token
- [ ] Uploads to user's Drive successfully
- [ ] Proper error handling for expired tokens

**Tests**:
- `tests/integration/test_slides_publisher_user_auth.py`

---

### Task 3.4: Update Export Service Process Job
**Owner**: Backend
**Duration**: 30 minutes
**Priority**: P0 (Blocking)

**File**: `src/svg2ooxml/api/services/export_service.py`

**Changes**:
```python
def process_job(self, job_id: str, user_token: str = None) -> None:
    """Process an export job.

    Args:
        job_id: Job ID to process
        user_token: User OAuth token (if authenticated)
    """
    # ... existing processing logic

    # When uploading to Slides
    if output_format == "slides":
        slides_info = slides_publisher.upload_pptx_to_slides(
            pptx_path=pptx_path,
            file_name=file_name,
            user_token=user_token  # NEW: Pass user token
        )

        # Update job with results
        self.db.collection("jobs").document(job_id).update({
            "status": "completed",
            "slides_url": slides_info["slides_url"],
            "presentation_id": slides_info["presentation_id"],
            # ...
        })
```

**Acceptance Criteria**:
- [ ] User token passed to slides publisher
- [ ] Works with and without token
- [ ] Job metadata updated correctly

**Tests**:
- `tests/integration/test_export_service_user_auth.py`

---

## Phase 4: Deployment Configuration ⏱️ 1 hour

### Task 4.1: Update cloudbuild.yaml
**Owner**: DevOps
**Duration**: 30 minutes
**Priority**: P0 (Blocking)

**File**: `cloudbuild.yaml`

**Changes**:
```yaml
steps:
  # ... existing build steps

  - name: gcr.io/google.com/cloudsdktool/cloud-sdk
    args:
      - gcloud
      - run
      - deploy
      - $_SERVICE
      - --image=$_REGION-docker.pkg.dev/$PROJECT_ID/$_REPOSITORY/$_IMAGE:$COMMIT_SHA
      - --region=$_REGION
      - --platform=managed
      - --service-account=svg2ooxml-runner@$PROJECT_ID.iam.gserviceaccount.com
      - --allow-unauthenticated
      - --set-env-vars=PYTHONPATH=/workspace/src,GCP_PROJECT=$PROJECT_ID,CLOUD_TASKS_LOCATION=$_REGION,CLOUD_TASKS_QUEUE=svg2ooxml-jobs,FIREBASE_PROJECT_ID=svg2ooxml,FIREBASE_SERVICE_ACCOUNT_PATH=/secrets/firebase-service-account
      # NEW: Mount secrets
      - --update-secrets=/secrets/firebase-service-account=firebase-service-account:latest,TOKEN_ENCRYPTION_KEY=token-encryption-key:latest

  # ... rest of file
```

**Acceptance Criteria**:
- [ ] Secrets mounted in Cloud Run
- [ ] Environment variables set correctly
- [ ] Build succeeds

**Tests**:
- Deploy and check Cloud Run environment

---

### Task 4.2: Update GitHub Actions Workflow
**Owner**: DevOps
**Duration**: 15 minutes
**Priority**: P1 (Important)

**File**: `.github/workflows/test-suite.yml`

**Changes**:
```yaml
- name: Run test suite
  env:
    # Mock Firebase for tests
    FIREBASE_AUTH_EMULATOR_HOST: localhost:9099
    TOKEN_ENCRYPTION_KEY: dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcwo=  # Test key
  run: |
    python -m pytest -m "not visual" --maxfail=1 --disable-warnings
```

**Acceptance Criteria**:
- [ ] Tests run successfully in CI
- [ ] Firebase emulator configured (optional)
- [ ] Test encryption key provided

**Tests**:
- Push to trigger GitHub Actions

---

## Phase 5: Testing & Documentation ⏱️ 2-3 hours

### Task 5.1: Write Unit Tests for Auth Modules
**Owner**: Backend
**Duration**: 1 hour
**Priority**: P0 (Blocking)

**Files to Create**:

1. `tests/unit/api/auth/test_firebase.py`
2. `tests/unit/api/auth/test_encryption.py`
3. `tests/unit/api/auth/test_middleware.py`

**Coverage Requirements**:
- [ ] Token verification: valid, expired, invalid signature
- [ ] Encryption: roundtrip, invalid key, tampered ciphertext
- [ ] Middleware: valid token, missing token, invalid token

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] Code coverage > 80% for auth modules
- [ ] Tests run in CI

---

### Task 5.2: Write Integration Tests
**Owner**: Backend
**Duration**: 1 hour
**Priority**: P1 (Important)

**Files to Create**:

1. `tests/integration/test_export_auth.py`
   - Test export endpoint with valid token
   - Test export endpoint without token (401)
   - Test export endpoint with invalid token (401)

2. `tests/integration/test_slides_user_auth.py`
   - Test Slides upload with user credentials
   - Verify presentation created in test user's Drive
   - Cleanup: Delete presentation after test

**Acceptance Criteria**:
- [ ] All integration tests pass
- [ ] Tests use real Firebase Auth (or emulator)
- [ ] Tests clean up created resources

---

### Task 5.3: Update test_slides_api.py
**Owner**: Backend
**Duration**: 30 minutes
**Priority**: P1 (Important)

**File**: `test_slides_api.py`

**Changes**:
```python
import firebase_admin
from firebase_admin import auth as firebase_auth

def get_test_user_token() -> str:
    """Get Firebase ID token for test user.

    For manual testing:
    1. Go to https://svg2ooxml.firebaseapp.com/__/auth/handler
    2. Sign in with test Google account
    3. Copy ID token from browser console

    Or use Firebase Auth REST API:
    https://firebase.google.com/docs/reference/rest/auth
    """
    # Option 1: Hardcode token for manual testing (expires in 1 hour)
    # return "eyJhbGciOiJSUzI1NiIsImtpZCI6..."

    # Option 2: Use Firebase Admin SDK to create custom token
    initialize_firebase()
    custom_token = firebase_auth.create_custom_token("test-user-123")
    # ... exchange for ID token via Auth REST API

    # For now, prompt user to provide token
    return input("Enter Firebase ID token: ")

def create_slides_export_job(base_url: str) -> str:
    """Create a test export job with authentication."""
    print("Creating Google Slides export job...")

    # Get test user token
    id_token = get_test_user_token()

    # ... existing request_data

    response = requests.post(
        f"{base_url}/api/v1/export",
        json=request_data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {id_token}"  # NEW: Add auth header
        }
    )
    # ... rest of function
```

**Acceptance Criteria**:
- [ ] Script prompts for Firebase ID token
- [ ] Script includes Authorization header
- [ ] Script works end-to-end with user auth

---

### Task 5.4: Create Figma Plugin Integration Guide
**Owner**: Backend
**Duration**: 30 minutes
**Priority**: P1 (Important)

**File**: `docs/guides/figma-plugin-firebase-auth.md`

**Content** (see next task output)

**Acceptance Criteria**:
- [ ] Guide includes Firebase setup steps
- [ ] Guide includes code examples
- [ ] Guide explains OAuth scopes
- [ ] Guide includes troubleshooting section

---

### Task 5.5: Create Firebase Setup Guide
**Owner**: Backend
**Duration**: 30 minutes
**Priority**: P1 (Important)

**File**: `docs/guides/firebase-setup.md`

**Content**:
- Firebase Console setup steps
- OAuth consent screen configuration
- Authorized domains setup
- Secret Manager configuration
- Deployment checklist

**Acceptance Criteria**:
- [ ] Guide follows setup tasks from Phase 1
- [ ] Includes screenshots (optional)
- [ ] Includes troubleshooting section

---

## Testing Checklist

### Local Testing
- [ ] Firebase Admin SDK initializes successfully
- [ ] Token verification works with valid token
- [ ] Token verification rejects expired token
- [ ] Token verification rejects invalid token
- [ ] Encryption/decryption roundtrip works
- [ ] Export endpoint returns 401 without token
- [ ] Export endpoint returns 202 with valid token
- [ ] Slides upload uses user credentials
- [ ] Background tasks decrypt token correctly
- [ ] Encrypted token deleted after job completion

### Cloud Run Testing
- [ ] Secrets mounted correctly (`/secrets/firebase-service-account`)
- [ ] Environment variables set correctly
- [ ] Firebase initializes on startup
- [ ] API health check passes
- [ ] Export endpoint requires authentication
- [ ] End-to-end test with real Google account succeeds
- [ ] Slides presentation appears in test user's Drive
- [ ] Temporary files cleaned up after 1 day

### Integration Testing
- [ ] Figma plugin can authenticate users
- [ ] Plugin receives Firebase ID token
- [ ] Plugin includes token in API requests
- [ ] API validates token and creates job
- [ ] Background processing completes
- [ ] Slides created in user's Drive
- [ ] User can view/edit presentation

---

## Deployment Plan

### Pre-Deployment
1. [ ] All unit tests passing
2. [ ] All integration tests passing
3. [ ] Firebase project configured
4. [ ] Secrets created in Secret Manager
5. [ ] OAuth consent screen approved (or in Testing mode)
6. [ ] Code reviewed and approved

### Deployment Steps
1. [ ] Merge to main branch
2. [ ] Trigger Cloud Build (automatic or manual)
3. [ ] Monitor build logs for errors
4. [ ] Verify Cloud Run deployment succeeds
5. [ ] Check Cloud Run logs for Firebase initialization
6. [ ] Run manual test with `test_slides_api.py`
7. [ ] Verify Slides created in test account
8. [ ] Monitor Cloud Tasks queue processing
9. [ ] Check for any errors in logs

### Post-Deployment
1. [ ] Verify API responds to health checks
2. [ ] Test authenticated endpoint with curl
3. [ ] Run end-to-end test with real account
4. [ ] Check temporary file cleanup (next day)
5. [ ] Monitor Firebase Auth usage (MAU)
6. [ ] Set up alerts for auth failures
7. [ ] Document any issues encountered

### Rollback Plan
If deployment fails:
1. [ ] Revert to previous Cloud Run revision
2. [ ] Investigate failure in logs
3. [ ] Fix issues locally
4. [ ] Re-test before re-deploying

---

## Success Criteria

### Functional
- [ ] Users can authenticate with Google account
- [ ] Users can export SVG to their own Google Slides
- [ ] Service stays within free tier (<1,000 MAU)
- [ ] No security vulnerabilities introduced

### Performance
- [ ] Token verification < 100ms (p95)
- [ ] End-to-end export time < 10s (p95)
- [ ] Background task processing < 5s (p95)

### Quality
- [ ] Code coverage > 80%
- [ ] All tests passing
- [ ] No linting errors
- [ ] Documentation complete

### Security
- [ ] Tokens encrypted in storage
- [ ] Tokens deleted after use
- [ ] No tokens in logs
- [ ] Secrets managed via Secret Manager

---

## Risk Mitigation

### High Priority Risks

**Risk**: Token expiration during long jobs
- **Mitigation**: Keep jobs short (<5 min), use fresh tokens
- **Monitoring**: Track job duration, alert if >10 min

**Risk**: OAuth scope denial by users
- **Mitigation**: Clear explanation of why scopes needed
- **Fallback**: Offer PPTX download instead

**Risk**: Firebase quota exceeded
- **Mitigation**: Monitor MAU, set alerts at 40K
- **Plan**: Upgrade to Blaze plan if needed

### Medium Priority Risks

**Risk**: Service account fallback fails
- **Mitigation**: Keep service account logic for testing
- **Monitoring**: Track auth_type in logs

**Risk**: Encrypted token compromise
- **Mitigation**: Strong encryption, immediate deletion
- **Plan**: Rotate encryption keys quarterly

---

## Open Questions

1. **Figma plugin domain**: What domain will the plugin use?
   - Needed for Firebase authorized domains

2. **Privacy policy**: Where should we host privacy policy?
   - Required for OAuth consent screen

3. **Rate limiting**: Should we limit exports per user?
   - Recommendation: 10 exports/hour per user

4. **Token refresh**: Should we support refresh tokens for long jobs?
   - Recommendation: No, keep jobs short

5. **Multi-account**: Should users be able to switch Google accounts?
   - Current design: Yes, re-authenticate

---

## Next Steps After Implementation

1. [ ] Submit OAuth consent screen for verification (for public launch)
2. [ ] Add rate limiting per user
3. [ ] Add analytics for export usage
4. [ ] Consider Cloud KMS for encryption (if scaling beyond free tier)
5. [ ] Add user management UI (view export history, etc.)
6. [ ] Implement token refresh for long jobs (if needed)
7. [ ] Add support for team/workspace exports (future feature)

---

**Total Estimated Time**: 10-14 hours
**Recommended Sprint**: 2 weeks (allows time for testing and iteration)
