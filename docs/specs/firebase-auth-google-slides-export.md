# Feature Specification: Firebase Auth for Distributed Google Slides Export

## Overview

**Feature Name**: Firebase Authentication Integration for Google Slides Export
**Status**: Design Phase
**Created**: 2025-11-02
**Owner**: svg2ooxml Team

### Purpose

Enable distributed Google Slides export functionality by implementing Firebase Authentication with Google OAuth. This allows end users to export SVG content to their own Google Slides workspaces, replacing the current service account approach which is limited by 0-byte Drive storage quota for new service accounts.

### Problem Statement

Currently, the svg2ooxml service uses a service account to create Google Slides presentations. This approach has critical limitations:

1. **Service Account Quota**: New Google Cloud service accounts (2024+) have 0 bytes Drive storage quota
2. **Not Distributable**: Service accounts cannot upload to arbitrary users' Google Drives (by design, for security)
3. **Workspace-Only Alternative**: Domain-wide delegation only works within a single Google Workspace
4. **User Intent**: The service is designed to be distributed to external users, not just internal workspace users

### Success Criteria

- [ ] Users can authenticate with their Google account via Firebase Auth
- [ ] Users can export SVG content to their own Google Slides workspace
- [ ] API validates user OAuth tokens before processing requests
- [ ] Figma plugin can integrate Firebase Auth with minimal code changes
- [ ] Solution stays within GCP free tier limits
- [ ] No sensitive data stored beyond temporary files (1-day lifecycle)
- [ ] Authentication flow completes in < 5 seconds
- [ ] Token validation adds < 100ms latency to API requests

---

## Technical Architecture

### High-Level Flow

```
┌─────────────────┐
│  Figma Plugin   │
│                 │
│ 1. User clicks  │
│    "Export to   │
│    Slides"      │
└────────┬────────┘
         │
         │ 2. Firebase Auth
         │    Google Sign-In
         ↓
┌─────────────────┐
│ Firebase Auth   │
│                 │
│ 3. Returns      │
│    OAuth token  │
└────────┬────────┘
         │
         │ 4. POST /api/v1/export
         │    Authorization: Bearer <token>
         ↓
┌─────────────────┐
│  Cloud Run API  │
│                 │
│ 5. Verify token │
│ 6. Process SVG  │
│ 7. Upload with  │
│    user's token │
└────────┬────────┘
         │
         │ 8. Drive API call
         │    with user credentials
         ↓
┌─────────────────┐
│ User's Google   │
│ Drive/Slides    │
│                 │
│ ✅ Presentation │
│    created      │
└─────────────────┘
```

### Component Changes

#### 1. Firebase Project (NEW)

**Setup Requirements**:
- Create Firebase project linked to existing GCP project
- Enable Firebase Authentication
- Configure Google Sign-In provider
- Add authorized domains (Cloud Run URL, Figma plugin domain)

**Configuration**:
```json
{
  "projectId": "svg2ooxml",
  "appId": "<generated-by-firebase>",
  "apiKey": "<generated-by-firebase>",
  "authDomain": "svg2ooxml.firebaseapp.com"
}
```

#### 2. Cloud Run API Updates

**New Dependencies**:
```python
firebase-admin>=6.5.0  # For token verification
google-auth>=2.28.0    # For user credential creation
```

**New Modules**:

**`src/svg2ooxml/api/auth/firebase.py`** (NEW)
- Initialize Firebase Admin SDK
- Verify ID tokens from client
- Extract user information

**`src/svg2ooxml/api/auth/middleware.py`** (NEW)
- FastAPI dependency for protected routes
- Token extraction from Authorization header
- Token validation and user context injection

**Modified Modules**:

**`src/svg2ooxml/api/routes/export.py`**
- Add auth dependency to `/api/v1/export` endpoint
- Pass user token to export service
- Return 401 for invalid/missing tokens

**`src/svg2ooxml/api/services/export_service.py`**
- Accept user credentials parameter
- Store user token with job metadata
- Pass credentials to background task

**`src/svg2ooxml/api/services/slides_publisher.py`**
- Replace service account credentials with user credentials
- Use OAuth token for Drive/Slides API calls
- Handle token refresh if needed

**`src/svg2ooxml/api/background/tasks.py`**
- Include user token in Cloud Tasks payload
- Decrypt/validate token before processing

#### 3. Figma Plugin Integration

**New Firebase SDK Integration**:
```typescript
// Firebase initialization
import { initializeApp } from 'firebase/app';
import { getAuth, signInWithPopup, GoogleAuthProvider } from 'firebase/auth';

const firebaseConfig = {
  apiKey: "...",
  authDomain: "svg2ooxml.firebaseapp.com",
  projectId: "svg2ooxml"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
```

**Authentication Flow**:
```typescript
async function exportToSlides() {
  // 1. Sign in with Google
  const provider = new GoogleAuthProvider();
  provider.addScope('https://www.googleapis.com/auth/drive.file');
  provider.addScope('https://www.googleapis.com/auth/presentations');

  const result = await signInWithPopup(auth, provider);
  const idToken = await result.user.getIdToken();

  // 2. Call API with token
  const response = await fetch('https://svg2ooxml-export.../api/v1/export', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      frames: [...],
      output_format: 'slides'
    })
  });
}
```

---

## API Specification

### Authentication Endpoint Changes

#### POST /api/v1/export

**Before**:
```http
POST /api/v1/export
Content-Type: application/json

{
  "frames": [...],
  "output_format": "slides"
}
```

**After**:
```http
POST /api/v1/export
Authorization: Bearer <firebase-id-token>
Content-Type: application/json

{
  "frames": [...],
  "output_format": "slides"
}
```

**New Response Codes**:
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: Token valid but missing required scopes

**Error Response Format**:
```json
{
  "error": "unauthorized",
  "message": "Missing or invalid authentication token",
  "details": "Authorization header required with Firebase ID token"
}
```

### Token Validation Flow

```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth as firebase_auth

security = HTTPBearer()

async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """Verify Firebase ID token and return user info."""
    try:
        # Verify the token
        decoded_token = firebase_auth.verify_id_token(credentials.credentials)

        # Extract user info
        return {
            "uid": decoded_token["uid"],
            "email": decoded_token.get("email"),
            "token": credentials.credentials
        }
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid authentication token: {str(e)}"
        )

# Usage in endpoint
@router.post("/export")
async def create_export(
    request: ExportRequest,
    user: dict = Depends(verify_firebase_token)
):
    # user["token"] contains the Firebase ID token
    # Use this to create user credentials for Drive API
    pass
```

---

## Data Model Changes

### Job Metadata Extension

**Firestore Document**: `jobs/{job_id}`

**New Fields**:
```python
{
    # Existing fields
    "job_id": str,
    "status": str,
    "created_at": datetime,
    "output_format": str,

    # NEW: User authentication
    "user": {
        "uid": str,              # Firebase user ID
        "email": str,            # User email (optional)
        "token_hash": str        # SHA256 hash of token (for audit)
    },

    # NEW: Token storage for background processing
    "auth_token_encrypted": str  # Encrypted ID token for Cloud Tasks
}
```

**Security Considerations**:
- Store only necessary user info (uid, email)
- Never log full tokens
- Encrypt tokens before storing for background tasks
- Delete encrypted tokens after job completion

---

## Security & Privacy

### Token Handling

**Client-Side**:
- Tokens obtained via Firebase Auth popup flow
- Tokens stored in memory only (no localStorage)
- Tokens included in Authorization header for each API request

**Server-Side**:
- Verify token signature using Firebase Admin SDK
- Check token expiration (1 hour default)
- Validate required scopes for Slides export
- Encrypt tokens before queuing background tasks
- Delete encrypted tokens after job completion

**Token Encryption**:
```python
from google.cloud import kms_v1
from cryptography.fernet import Fernet

def encrypt_token(token: str) -> str:
    """Encrypt OAuth token for storage in Cloud Tasks."""
    # Option 1: Cloud KMS (production)
    # kms_client = kms_v1.KeyManagementServiceClient()
    # encrypted = kms_client.encrypt(...)

    # Option 2: Environment-based key (simpler, free tier)
    key = os.getenv("TOKEN_ENCRYPTION_KEY")  # 32-byte base64
    fernet = Fernet(key)
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted: str) -> str:
    """Decrypt OAuth token for use in background task."""
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    fernet = Fernet(key)
    return fernet.decrypt(encrypted.encode()).decode()
```

### OAuth Scopes Required

**Minimum Scopes**:
```typescript
const scopes = [
  'https://www.googleapis.com/auth/drive.file',        // Create files in Drive
  'https://www.googleapis.com/auth/presentations'      // Create/edit Slides
];
```

**Scope Justification**:
- `drive.file`: Allows creating new files (not accessing existing files)
- `presentations`: Required for Slides API operations

### Data Retention

**Temporary Files**:
- PPTX files: 1-day lifecycle (existing policy)
- Consider: Delete immediately after Slides upload (optimization)

**Job Metadata**:
- Retain for 7 days for status checking
- Encrypted tokens deleted after job completion
- User email/uid retained for audit trail

**User Data**:
- No user data stored beyond job context
- No analytics or tracking
- OAuth tokens never logged

### Compliance

**GDPR Considerations**:
- User email stored with consent (part of auth flow)
- Data deletion: Auto-purge after 7 days
- User can request job data deletion via API (future)

**Google OAuth Policy**:
- Must display Google branding on sign-in button
- Must provide privacy policy URL
- Must explain why scopes are requested

---

## Implementation Plan

### Phase 1: Firebase Setup (1-2 hours)

**Tasks**:
1. Create Firebase project in console
2. Link to existing GCP project `svg2ooxml`
3. Enable Google Sign-In provider
4. Configure OAuth consent screen
5. Add authorized domains:
   - `svg2ooxml-export-sghya3t5ya-ew.a.run.app` (Cloud Run)
   - Figma plugin domain (TBD)
6. Generate Firebase config for web clients
7. Create service account key for Firebase Admin SDK

**Deliverables**:
- Firebase project ID
- Web app config JSON
- Service account key file
- Setup documentation

### Phase 2: API Authentication (3-4 hours)

**Tasks**:
1. Add dependencies: `firebase-admin`, `google-auth`, `cryptography`
2. Create `src/svg2ooxml/api/auth/firebase.py`:
   - Initialize Firebase Admin SDK
   - Token verification function
3. Create `src/svg2ooxml/api/auth/middleware.py`:
   - FastAPI security dependency
   - Extract and verify token from header
4. Update `src/svg2ooxml/api/routes/export.py`:
   - Add auth dependency to POST /api/v1/export
   - Handle 401/403 responses
5. Create token encryption utilities
6. Update Cloud Run environment variables:
   - `FIREBASE_PROJECT_ID`
   - `TOKEN_ENCRYPTION_KEY`
7. Mount Firebase service account key in Cloud Run

**Deliverables**:
- Authentication middleware
- Protected export endpoint
- Token encryption/decryption utilities
- Updated deployment config

### Phase 3: Drive API Integration (2-3 hours)

**Tasks**:
1. Update `src/svg2ooxml/api/services/export_service.py`:
   - Accept user credentials parameter
   - Store encrypted token in job metadata
   - Pass token to background tasks
2. Update `src/svg2ooxml/api/background/tasks.py`:
   - Include encrypted token in Cloud Tasks payload
   - Decrypt token before processing
   - Delete token after job completion
3. Update `src/svg2ooxml/api/services/slides_publisher.py`:
   - Replace `service_account.Credentials` with user credentials
   - Create credentials from OAuth token
   - Handle token expiration gracefully

**Deliverables**:
- User credential flow in slides publisher
- Background task token handling
- Error handling for expired tokens

### Phase 4: Testing & Documentation (2-3 hours)

**Tasks**:
1. Create test OAuth token generator (for local testing)
2. Update `test_slides_api.py` to use Firebase Auth
3. Test complete flow:
   - Authenticate with Google
   - Create export job
   - Verify Slides upload to user's Drive
4. Create Figma plugin integration guide
5. Document Firebase setup process
6. Update API documentation with auth requirements

**Deliverables**:
- Updated test scripts
- Figma plugin integration guide
- API documentation
- Troubleshooting guide

### Phase 5: Figma Plugin Updates (handled by plugin team)

**Tasks** (for plugin developers):
1. Install Firebase SDK: `npm install firebase`
2. Initialize Firebase with provided config
3. Add "Sign in with Google" button
4. Implement sign-in flow with required scopes
5. Update API calls to include Authorization header
6. Handle auth errors (show re-auth prompt)
7. Test end-to-end flow

**Deliverables**:
- Updated Figma plugin with Firebase Auth
- User-facing documentation

---

## Testing Strategy

### Unit Tests

**`tests/unit/api/auth/test_firebase.py`** (NEW)
```python
def test_verify_valid_token():
    """Test token verification with valid Firebase token."""
    # Mock Firebase Admin SDK
    # Verify token validation succeeds

def test_verify_expired_token():
    """Test token verification with expired token."""
    # Verify 401 error raised

def test_verify_invalid_signature():
    """Test token verification with tampered token."""
    # Verify 401 error raised
```

**`tests/unit/api/auth/test_encryption.py`** (NEW)
```python
def test_encrypt_decrypt_roundtrip():
    """Test token encryption/decryption."""
    token = "test-token-123"
    encrypted = encrypt_token(token)
    decrypted = decrypt_token(encrypted)
    assert decrypted == token
```

### Integration Tests

**`tests/integration/test_auth_flow.py`** (NEW)
```python
async def test_export_with_valid_token():
    """Test export endpoint with valid Firebase token."""
    # Create mock Firebase token
    # POST /api/v1/export with Authorization header
    # Verify 202 response and job created

async def test_export_without_token():
    """Test export endpoint without token."""
    # POST /api/v1/export without Authorization header
    # Verify 401 response

async def test_export_with_invalid_token():
    """Test export endpoint with invalid token."""
    # POST /api/v1/export with malformed token
    # Verify 401 response
```

**`tests/integration/test_slides_with_user_auth.py`** (NEW)
```python
async def test_slides_upload_with_user_credentials():
    """Test Slides upload using user OAuth token."""
    # Create export job with user token
    # Process job
    # Verify Slides created in user's Drive (use test account)
    # Cleanup: Delete created presentation
```

### Manual Testing Checklist

- [ ] Firebase Auth popup appears in Figma plugin
- [ ] User can sign in with Google account
- [ ] Required scopes displayed correctly
- [ ] Token included in API request header
- [ ] Export job created successfully
- [ ] Background processing completes
- [ ] Slides presentation appears in user's Drive
- [ ] Presentation has correct content/formatting
- [ ] Error handling: Expired token shows re-auth prompt
- [ ] Error handling: Network failure shows retry option

---

## Deployment Checklist

### Pre-Deployment

- [ ] Firebase project created and configured
- [ ] OAuth consent screen approved (if using external users)
- [ ] Service account key generated for Firebase Admin
- [ ] Token encryption key generated (32-byte base64)
- [ ] All unit tests passing
- [ ] Integration tests passing with test user account

### Cloud Run Deployment

**Environment Variables**:
```yaml
- FIREBASE_PROJECT_ID=svg2ooxml
- TOKEN_ENCRYPTION_KEY=<base64-encoded-32-bytes>
- GCP_PROJECT=$PROJECT_ID
- CLOUD_TASKS_LOCATION=europe-west1
- CLOUD_TASKS_QUEUE=svg2ooxml-jobs
- SERVICE_URL=<auto-generated>
- PYTHONPATH=/workspace/src
```

**Secrets** (recommended alternative to env vars):
```bash
# Create secret for Firebase service account
gcloud secrets create firebase-service-account \
  --data-file=firebase-service-account.json \
  --replication-policy=automatic

# Create secret for encryption key
echo -n "<base64-key>" | gcloud secrets create token-encryption-key \
  --data-file=-

# Grant Cloud Run access
gcloud secrets add-iam-policy-binding firebase-service-account \
  --member="serviceAccount:svg2ooxml-runner@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

**Updated `cloudbuild.yaml`**:
```yaml
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
    - --set-env-vars=PYTHONPATH=/workspace/src,GCP_PROJECT=$PROJECT_ID,CLOUD_TASKS_LOCATION=$_REGION,CLOUD_TASKS_QUEUE=svg2ooxml-jobs,FIREBASE_PROJECT_ID=svg2ooxml
    - --set-secrets=FIREBASE_SERVICE_ACCOUNT=firebase-service-account:latest,TOKEN_ENCRYPTION_KEY=token-encryption-key:latest
```

### Post-Deployment

- [ ] Verify API health check passes
- [ ] Test authenticated endpoint with curl + token
- [ ] Run end-to-end test with real Google account
- [ ] Verify Slides created in test account
- [ ] Check Cloud Run logs for errors
- [ ] Monitor Cloud Tasks queue processing
- [ ] Verify temporary file cleanup (1-day lifecycle)

---

## Monitoring & Observability

### Metrics to Track

**Authentication Metrics**:
- Token verification success rate
- Token verification latency (p50, p95, p99)
- Authentication errors by type (expired, invalid, missing)

**Conversion Metrics**:
- Slides export success rate (with user auth vs service account)
- Background task processing time
- Drive API error rates

**Cost Metrics**:
- Firebase Auth MAU (Monthly Active Users)
- Cloud Tasks execution count
- Cloud Run request count

### Logging Strategy

**Log Events**:
```python
import logging

logger = logging.getLogger(__name__)

# Auth success
logger.info("Token verified", extra={
    "user_id": user["uid"],
    "token_hash": hashlib.sha256(token.encode()).hexdigest()[:8]
})

# Auth failure
logger.warning("Token verification failed", extra={
    "error": str(e),
    "token_hash": hashlib.sha256(token.encode()).hexdigest()[:8]
})

# Slides upload success
logger.info("Slides created", extra={
    "job_id": job_id,
    "user_id": user["uid"],
    "presentation_id": presentation_id
})
```

**Never Log**:
- Full OAuth tokens
- User email addresses (use hashed user_id instead)
- Any PII beyond what's necessary for debugging

### Alerting

**Alert Conditions**:
- Token verification error rate > 10% (5-minute window)
- Slides upload failure rate > 20% (15-minute window)
- Background task queue depth > 100 jobs
- Firebase Auth quota approaching limit (45K MAU)

---

## Cost Estimation

### Firebase Services

**Firebase Authentication**:
- Free tier: 50,000 MAU (Monthly Active Users)
- Cost above free tier: $0.0055/MAU
- Estimated usage: < 1,000 MAU
- **Cost: $0.00/month**

**Firebase Admin SDK**:
- No additional cost (uses existing GCP project)

### Existing GCP Services (No Change)

- Cloud Run: ~$0.08/month (free tier covers most usage)
- Cloud Storage: ~$0.02/month (1-day lifecycle)
- Firestore: ~$0.01/month (minimal reads/writes)
- Cloud Tasks: ~$0.03/month (background jobs)

**Total Estimated Cost: ~$0.14/month** (no change from current)

---

## Risks & Mitigations

### Risk 1: Token Expiration During Long Jobs

**Risk**: Firebase ID tokens expire after 1 hour. Long export jobs may fail if token expires mid-processing.

**Likelihood**: Medium
**Impact**: High

**Mitigation**:
- Store refresh token (if available) for long jobs
- Implement token refresh logic in background tasks
- Alternative: Require fresh token for each API call (simpler, recommended)

### Risk 2: Firebase Auth Quota Limits

**Risk**: Free tier supports 50K MAU. Growth beyond this requires paid plan.

**Likelihood**: Low (for initial launch)
**Impact**: Medium (service degradation)

**Mitigation**:
- Monitor MAU usage in Firebase console
- Set up alerts at 40K MAU (80% threshold)
- Plan for upgrade to Blaze plan if needed ($0.0055/MAU above 50K)

### Risk 3: OAuth Scope Creep

**Risk**: Users may deny required scopes, causing auth to fail.

**Likelihood**: Low
**Impact**: High (can't export to Slides)

**Mitigation**:
- Request minimal scopes (`drive.file` + `presentations`)
- Clearly explain why each scope is needed
- Graceful error handling: "Slides export requires Drive access"
- Fallback: Offer PPTX download instead

### Risk 4: Firebase Service Retirement

**Risk**: Firebase could be deprecated (user expressed concern).

**Likelihood**: Very Low
**Impact**: Very High

**Mitigation**:
- Firebase Auth is a core Google product (stable, widely used)
- Alternative: Direct Google Identity Services integration (more complex)
- Abstraction layer: Keep auth logic modular for easy replacement

### Risk 5: Token Storage Security

**Risk**: Encrypted tokens stored in Firestore/Cloud Tasks could be compromised.

**Likelihood**: Very Low
**Impact**: High

**Mitigation**:
- Use strong encryption (AES-256 via Fernet)
- Rotate encryption keys quarterly
- Delete tokens immediately after job completion
- Alternative: Use Cloud KMS for encryption (more secure, ~$0.03/month)

---

## Success Metrics

### Launch Metrics (Week 1)

- [ ] 0 authentication errors (excluding user denials)
- [ ] > 95% Slides upload success rate
- [ ] < 200ms token verification latency (p95)
- [ ] 0 production incidents

### Growth Metrics (Month 1)

- [ ] > 100 successful Slides exports
- [ ] > 90% user authentication success rate
- [ ] < 5% token expiration errors
- [ ] Stay within free tier (< 1,000 MAU)

### Quality Metrics (Ongoing)

- [ ] > 99% API uptime
- [ ] < 5s end-to-end export time (95th percentile)
- [ ] 0 data retention policy violations
- [ ] 0 security incidents

---

## Open Questions

1. **Figma Plugin Hosting**: Where will the Figma plugin be hosted to add to Firebase authorized domains?

2. **Refresh Tokens**: Should we store refresh tokens for long-running jobs, or require fresh tokens per request?
   - Recommendation: Require fresh tokens (simpler, more secure)

3. **Privacy Policy**: Do we need a dedicated privacy policy page, or can we use inline explanation?
   - Required for OAuth consent screen

4. **Token Cleanup**: Delete immediately after Slides upload, or keep for retry logic?
   - Recommendation: Delete after successful upload (minimize exposure)

5. **Rate Limiting**: Should we implement per-user rate limits to prevent abuse?
   - Recommendation: Yes, use fastapi-limiter (e.g., 10 exports/hour/user)

6. **Multi-Account**: Should users be able to export to different Google accounts?
   - Current design: Yes, re-auth for different account
   - Alternative: Store multiple tokens per user (more complex)

---

## References

### Documentation

- [Firebase Authentication Docs](https://firebase.google.com/docs/auth)
- [Firebase Admin SDK (Python)](https://firebase.google.com/docs/admin/setup)
- [Google Drive API - User Authentication](https://developers.google.com/drive/api/guides/about-auth)
- [Google Slides API](https://developers.google.com/slides/api/guides/overview)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)

### Code Examples

- [Firebase Auth with FastAPI](https://github.com/Tanu-N-Prabhu/Python/blob/master/Firebase_Authentication.py)
- [Google OAuth 2.0 for Web Apps](https://developers.google.com/identity/protocols/oauth2/web-server)

### Related ADRs

- ADR-017: resvg Rendering Strategy (filter handling)
- Future: ADR-018: Firebase Authentication for Distributed Access

---

## Appendix A: Alternative Approaches Considered

### Alternative 1: Domain-Wide Delegation

**Description**: Configure service account with domain-wide delegation in Google Workspace.

**Pros**:
- No Firebase dependency
- Simpler architecture (no token handling)
- Direct service account usage

**Cons**:
- Only works within a single Google Workspace
- Requires Workspace admin setup
- Not suitable for distribution to external users
- **Rejected**: User wants to distribute to others, not just internal workspace

### Alternative 2: Google Identity Services (GIS)

**Description**: Use Google's newer Identity Services library directly instead of Firebase.

**Pros**:
- Direct Google integration (no Firebase)
- More control over OAuth flow
- Latest Google auth technology

**Cons**:
- More complex client-side integration
- No token verification SDK (must implement manually)
- Less documentation/examples
- **Rejected**: Firebase Auth provides simpler integration with proven SDK

### Alternative 3: Self-Hosted OAuth Server

**Description**: Build custom OAuth 2.0 server to manage Google tokens.

**Pros**:
- Full control over auth flow
- No third-party dependencies
- Custom token management

**Cons**:
- Significant development effort
- Security complexity (token storage, refresh, etc.)
- Must implement token verification from scratch
- Maintenance overhead
- **Rejected**: Overkill for this use case, Firebase Auth is purpose-built

---

## Appendix B: Firebase Config Example

### Web Client Config

```javascript
// src/figma-plugin/firebase-config.js
export const firebaseConfig = {
  apiKey: "AIzaSyD...",
  authDomain: "svg2ooxml.firebaseapp.com",
  projectId: "svg2ooxml",
  storageBucket: "svg2ooxml.appspot.com",
  messagingSenderId: "123456789",
  appId: "1:123456789:web:abc123"
};
```

### Server Config

```python
# src/svg2ooxml/api/auth/firebase.py
import firebase_admin
from firebase_admin import credentials, auth

def initialize_firebase():
    """Initialize Firebase Admin SDK."""
    if not firebase_admin._apps:
        # Option 1: Service account key file
        cred = credentials.Certificate("/secrets/firebase-service-account.json")

        # Option 2: Application Default Credentials (if on GCP)
        # cred = credentials.ApplicationDefault()

        firebase_admin.initialize_app(cred, {
            'projectId': 'svg2ooxml',
        })
```

---

## Appendix C: OAuth Scopes Explanation

### For Users (Consent Screen)

**"Why does this app need access to my Google Drive?"**

> svg2ooxml creates a Google Slides presentation from your design and saves it to your Google Drive. We only create new files—we never access your existing files.

**Scopes Requested**:
- ✅ **Create files in your Google Drive** (`drive.file`)
  _Required to save the generated Slides presentation_

- ✅ **Create and edit Google Slides** (`presentations`)
  _Required to build the presentation from your design_

**What We Don't Access**:
- ❌ Your existing Drive files
- ❌ Your Gmail or other Google services
- ❌ Files shared with you

### For Developers

**`https://www.googleapis.com/auth/drive.file`**:
- Grants access only to files created by the app
- Does NOT grant access to user's existing files
- Most restrictive Drive scope available
- Recommended for apps that only create new files

**`https://www.googleapis.com/auth/presentations`**:
- Grants full access to Google Slides API
- Required for creating and updating presentations
- Does NOT grant access to Drive (must be combined with drive scope)

**Alternative Scopes (NOT USED)**:
- `drive`: Full Drive access (too broad)
- `drive.readonly`: Read-only (insufficient for creating files)
- `drive.appdata`: Only app-specific folder (too restrictive)

---

## Appendix D: Token Encryption Implementation

### Using Fernet (Recommended for Free Tier)

```python
# src/svg2ooxml/api/auth/encryption.py
import os
import base64
from cryptography.fernet import Fernet

def get_encryption_key() -> bytes:
    """Get or generate encryption key from environment."""
    key_b64 = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key_b64:
        raise ValueError("TOKEN_ENCRYPTION_KEY not set")
    return base64.urlsafe_b64decode(key_b64)

def encrypt_token(token: str) -> str:
    """Encrypt OAuth token for storage."""
    fernet = Fernet(get_encryption_key())
    encrypted = fernet.encrypt(token.encode('utf-8'))
    return base64.urlsafe_b64encode(encrypted).decode('utf-8')

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt stored OAuth token."""
    fernet = Fernet(get_encryption_key())
    encrypted = base64.urlsafe_b64decode(encrypted_token)
    return fernet.decrypt(encrypted).decode('utf-8')

# Generate key (run once, store in secret)
# key = Fernet.generate_key()
# print(base64.urlsafe_b64encode(key).decode())
```

### Using Cloud KMS (Alternative for Production)

```python
# src/svg2ooxml/api/auth/kms_encryption.py
from google.cloud import kms_v1

def encrypt_token_kms(token: str) -> str:
    """Encrypt token using Cloud KMS."""
    client = kms_v1.KeyManagementServiceClient()

    key_name = client.crypto_key_path(
        project='svg2ooxml',
        location='europe-west1',
        key_ring='svg2ooxml-keys',
        crypto_key='token-encryption'
    )

    response = client.encrypt(
        request={'name': key_name, 'plaintext': token.encode('utf-8')}
    )

    return base64.urlsafe_b64encode(response.ciphertext).decode('utf-8')

# Cost: ~$0.03/month for 10,000 operations
# Setup: Create KMS key ring and key in GCP console
```

**Recommendation**: Use Fernet for free tier, migrate to KMS if scaling beyond 10K MAU.

---

**END OF SPECIFICATION**
