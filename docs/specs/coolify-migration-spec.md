# Coolify Migration Spec: svg2ooxml Figma Plugin Backend

## Goal

Replace the defunct Firebase/GCP backend with a self-hosted stack on Coolify,
restoring the Figma plugin's ability to convert SVG frames to Google Slides.

## Infrastructure (already provisioned)

| Component | URL | Status |
|-----------|-----|--------|
| Supabase Auth (GoTrue) | `https://auth.supabase.tactcheck.com` | Running, Google OAuth enabled |
| Supabase REST (PostgREST) | `https://supabase.tactcheck.com` | Running |
| Supabase DB (Postgres) | Internal (`supabase-db:5432`) | Running |
| svg2ooxml API | `https://svg2ooxml.tactcheck.com` | Coolify app created, not deployed |
| Google OAuth Client | `129309161606-18ktjcgn1809hq5ibuu8d092nqqqsmkp` | Web type, redirect to GoTrue |
| GCP Project | `do-this-484623` | Active, Drive + Slides APIs enabled |

### Credentials Reference

| Secret | Source |
|--------|--------|
| `SUPABASE_JWT_SECRET` | `JEuPG2LNzcchgyymftOos3fp6Cv8D7DR` |
| `SUPABASE_URL` | `https://supabase.tactcheck.com` |
| `SUPABASE_AUTH_URL` | `https://auth.supabase.tactcheck.com` |
| `GOOGLE_CLIENT_ID` | `129309161606-18ktjcgn1809hq5ibuu8d092nqqqsmkp.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Stored in GoTrue env (not in repo) |

---

## Architecture

```
Figma Plugin (browser sandbox)
  │
  ├─ Auth: Opens popup → GoTrue Google OAuth
  │        ← Returns: supabase_jwt + google_access_token
  │
  └─ Export: POST /api/v1/export
             Headers: Authorization: Bearer <supabase_jwt>
             Body: { frames: [...], google_access_token: "...", output_format: "slides" }
                │
                ▼
svg2ooxml API (FastAPI on Coolify)
  │
  ├─ Verify supabase_jwt (HS256 with SUPABASE_JWT_SECRET)
  ├─ Convert SVG → PPTX (synchronous, in-process)
  ├─ Upload PPTX → Google Slides (using user's google_access_token)
  └─ Return { slides_url: "https://docs.google.com/presentation/d/..." }
```

### What's Removed (vs. old architecture)

- Firebase Auth → Supabase GoTrue
- Firebase Realtime DB (auth polling) → GoTrue handles full flow
- Firestore (jobs, users, tokens, cache) → Not needed (synchronous)
- Cloud Storage (PPTX staging) → Not needed (direct upload)
- Huey/Redis queue → Not needed (synchronous conversion)
- Cloud Tasks → Not needed
- Stripe subscriptions → Dropped for now

---

## Backend Changes

### 1. New: `src/svg2ooxml/api/auth/supabase.py`

Supabase JWT verification using PyJWT:

```python
import jwt
from fastapi import Depends, HTTPException, Request

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

def verify_supabase_token(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = auth[7:]
    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"],
                             audience="authenticated")
        return {"uid": payload["sub"], "email": payload.get("email")}
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
```

### 2. Rewrite: `src/svg2ooxml/api/routes/export.py`

Synchronous endpoint. No job queue, no polling.

```python
@router.post("/export")
async def export_frames(request: ExportRequest, user=Depends(verify_supabase_token)):
    # 1. Convert SVG frames → PPTX (in-process)
    pptx_bytes = render_pptx_for_frames(request.frames)

    # 2. If slides output requested, upload to Google Slides
    if request.output_format == "slides":
        slides_url = upload_to_google_slides(
            pptx_bytes, request.google_access_token,
            title=request.figma_file_name
        )
        return {"slides_url": slides_url}

    # 3. Otherwise return PPTX as download
    return StreamingResponse(io.BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename={request.figma_file_name}.pptx"})
```

**Request model:**
```python
class ExportFrame(BaseModel):
    name: str
    svg_content: str
    width: float
    height: float

class ExportRequest(BaseModel):
    frames: list[ExportFrame]
    figma_file_name: str = "Untitled"
    output_format: str = "slides"  # "slides" or "pptx"
    google_access_token: str | None = None  # required if output_format == "slides"
```

### 3. Simplify: `src/svg2ooxml/api/services/slides_publisher.py`

Remove Firestore token lookup. Accept Google access token directly:

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def upload_to_google_slides(pptx_bytes: bytes, access_token: str, title: str) -> str:
    creds = Credentials(token=access_token)

    # Upload PPTX to Drive
    drive = build("drive", "v3", credentials=creds)
    file_metadata = {"name": title, "mimeType": "application/vnd.google-apps.presentation"}
    media = MediaIoBaseUpload(io.BytesIO(pptx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    file = drive.files().create(body=file_metadata, media_body=media, fields="id").execute()

    return f"https://docs.google.com/presentation/d/{file['id']}/edit"
```

### 4. Rewrite: `main.py`

Strip to essentials:

```python
app = FastAPI(title="svg2ooxml Export API", version="0.3.2")

app.add_middleware(CORSMiddleware,
    allow_origins=["https://www.figma.com", "https://figma.com", "null"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"])

app.include_router(export_router, prefix="/api/v1")
# Health check at / and /health
```

No Firebase init, no subscription/tasks/webhooks/oauth routers.

### 5. Delete these modules

```
src/svg2ooxml/api/auth/firebase.py
src/svg2ooxml/api/auth/cloud_tasks.py
src/svg2ooxml/api/auth/encryption.py
src/svg2ooxml/api/background/
src/svg2ooxml/api/caching/
src/svg2ooxml/api/routes/tasks.py
src/svg2ooxml/api/routes/subscription.py
src/svg2ooxml/api/routes/webhooks.py
src/svg2ooxml/api/routes/oauth.py
src/svg2ooxml/api/routes/_user_state.py
src/svg2ooxml/api/routes/_job_access.py
src/svg2ooxml/api/services/stripe_service.py
src/svg2ooxml/api/services/subscription_repo*.py
src/svg2ooxml/api/services/export_service_storage.py
```

### 6. Update: `pyproject.toml` dependencies

```toml
api = [
  "fastapi>=0.109.0",
  "uvicorn[standard]>=0.27.0",
  "pydantic>=2.5.3",
  "python-multipart>=0.0.6",
  "PyJWT>=2.8.0",
]
```

Remove from `api`: `firebase-admin`, `huey`.
Keep `cloud` extra for `google-api-python-client`, `google-auth` (Slides upload).

---

## Dockerfile (new: `Dockerfile.api`)

```dockerfile
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt1-dev zlib1g-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -e .[api,cloud,color,slides]

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Point Coolify to use `Dockerfile.api` as the build file.

---

## Figma Plugin Changes

### `manifest.json`

```json
{
  "networkAccess": {
    "allowedDomains": [
      "https://svg2ooxml.tactcheck.com",
      "https://auth.supabase.tactcheck.com",
      "https://*.googleapis.com",
      "https://*.google.com"
    ]
  }
}
```

### `ui-v2.html` — Auth Flow

Replace Firebase popup + RTDB polling with Supabase GoTrue:

1. User clicks "Sign in with Google"
2. Plugin opens popup to:
   ```
   https://auth.supabase.tactcheck.com/authorize?provider=google
     &redirect_to=https://svg2ooxml.tactcheck.com/auth/callback
     &scopes=https://www.googleapis.com/auth/drive.file+https://www.googleapis.com/auth/presentations
     &access_type=offline
     &prompt=consent
   ```
3. User completes Google consent
4. GoTrue redirects to callback page with tokens in URL fragment
5. Callback page (`/auth/callback` served by FastAPI) extracts tokens and
   stores them, then posts to parent window or the plugin polls for them
6. Plugin stores: `supabase_jwt`, `google_access_token`, `email`

### `ui-v2.html` — Export Flow

Replace async job polling with synchronous call:

```javascript
const response = await fetch(`${API_URL}/api/v1/export`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${supabaseJwt}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    frames: svgFrames,
    figma_file_name: figmaFileName,
    output_format: 'slides',
    google_access_token: googleAccessToken
  })
});
const result = await response.json();
// result.slides_url → open in new tab
```

No polling loop. Single request, single response.

### `ui-v2.html` — Remove

- Subscription/tier UI (free/pro badges, upgrade button, usage bar)
- Job polling logic
- Firebase RTDB polling
- Token refresh via `securetoken.googleapis.com`

### `code.js` — Session Storage

Update keys:
```javascript
// Store
await figma.clientStorage.setAsync('supabase_jwt', jwt);
await figma.clientStorage.setAsync('google_access_token', googleToken);
await figma.clientStorage.setAsync('email', email);

// Restore on plugin reload
const jwt = await figma.clientStorage.getAsync('supabase_jwt');
```

---

## Coolify App Configuration

### Environment Variables for `svg2ooxml-api`

| Key | Value |
|-----|-------|
| `SUPABASE_JWT_SECRET` | `JEuPG2LNzcchgyymftOos3fp6Cv8D7DR` |
| `GOOGLE_CLIENT_ID` | `129309161606-18ktjcgn1809hq5ibuu8d092nqqqsmkp.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | (from GoTrue config) |
| `ENVIRONMENT` | `production` |
| `PORT` | `8080` |

### Coolify Build Settings

- Source: `https://github.com/BramAlkema/svg2ooxml` (public)
- Branch: `main`
- Dockerfile: `Dockerfile.api`
- Port: `8080`
- Domain: `https://svg2ooxml.tactcheck.com`

---

## Auth Callback Page

FastAPI serves a minimal static HTML page at `/auth/callback` that:

1. Extracts `access_token` and `provider_token` from URL fragment
2. Stores them in a short-lived server-side dict keyed by a random `auth_key`
3. The Figma plugin polls `GET /api/v1/auth/poll?key=<auth_key>` to retrieve tokens
4. Tokens are deleted after retrieval (single-use)

This mirrors the existing Firebase RTDB polling pattern that works in Figma's
sandboxed iframe environment.

```python
# In-memory token store (TTL 2 minutes)
_pending_auth: dict[str, dict] = {}

@app.get("/auth/callback")
async def auth_callback():
    return HTMLResponse(AUTH_CALLBACK_HTML)

@app.post("/api/v1/auth/store")
async def store_auth(key: str, data: dict):
    _pending_auth[key] = {**data, "expires": time.time() + 120}
    return {"ok": True}

@app.get("/api/v1/auth/poll")
async def poll_auth(key: str):
    entry = _pending_auth.pop(key, None)
    if not entry or entry["expires"] < time.time():
        return {"status": "pending"}
    return {"status": "complete", **entry}
```

---

## Token Refresh Strategy

Google access tokens expire after 1 hour. For the Figma plugin:

1. The plugin always requests `prompt=consent` + `access_type=offline` to get
   a refresh token on sign-in
2. Before each export, the plugin checks if the token is expired
3. If expired, calls `POST /api/v1/auth/refresh` with the refresh token
4. The backend uses `google.auth.transport.requests.Request()` to refresh and
   returns a new access token
5. If refresh fails, the plugin shows "Sign in again"

```python
@app.post("/api/v1/auth/refresh")
async def refresh_google_token(refresh_token: str):
    creds = Credentials(token=None, refresh_token=refresh_token,
        client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token")
    creds.refresh(google.auth.transport.requests.Request())
    return {"access_token": creds.token, "expires_in": 3600}
```

---

## Implementation Order

1. **Backend auth + export** — `supabase.py`, rewrite `export.py`, simplify `slides_publisher.py`
2. **main.py + Dockerfile.api** — strip down, create lean Dockerfile
3. **Delete dead modules** — Firebase, Stripe, Huey, Firestore
4. **Auth callback page** — static HTML + poll endpoints
5. **Deploy to Coolify** — set env vars, first deploy
6. **Figma plugin** — rewrite auth + export flow in `ui-v2.html`
7. **Test end-to-end** — sign in → export → Google Slides link

---

## Risks

1. **Conversion timeout** — Large multi-frame exports could take 30+ seconds.
   Configure Coolify/Traefik proxy timeout to 180s.

2. **Google consent screen** — GCP project `do-this-484623` consent screen must
   be configured for external users with Drive/Slides scopes. Currently may be
   in "Testing" mode (limited to 100 test users).

3. **Token in request body** — The Google access token is sent in the POST body,
   not stored server-side. This is acceptable because the token is short-lived
   (1 hour) and the connection is HTTPS.

4. **No persistent storage** — Auth polling uses in-memory dict. If the API
   restarts during auth flow, user must sign in again. Acceptable for MVP.
