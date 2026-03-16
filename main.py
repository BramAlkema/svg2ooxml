"""FastAPI entry point for svg2ooxml export service (Coolify deployment)."""

from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.svg2ooxml.api.routes.export import router as export_router
from src.svg2ooxml.api.middleware import RateLimiter, RateLimitMiddleware

RATE_LIMIT = int(os.getenv("SVG2OOXML_RATE_LIMIT", "60"))
RATE_WINDOW_SECONDS = int(os.getenv("SVG2OOXML_RATE_WINDOW", "60"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="svg2ooxml Export API", version="0.3.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.figma.com",
        "https://figma.com",
        "null",  # Figma plugin sandbox
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600,
)

rate_limiter = RateLimiter(limit=RATE_LIMIT, window_seconds=RATE_WINDOW_SECONDS)
app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)

app.include_router(export_router, prefix="/api/v1", tags=["export"])


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"service": "svg2ooxml-export", "status": "healthy", "version": "0.3.2"}


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "healthy"}, status_code=200)


# ---------------------------------------------------------------------------
# Auth callback + token polling (Step 4)
# ---------------------------------------------------------------------------

# In-memory pending auth store (TTL 2 minutes).
_pending_auth: dict[str, dict] = {}
_AUTH_TTL = 120  # seconds


def _cleanup_expired() -> None:
    """Remove expired entries from the pending auth store."""
    now = time.time()
    expired = [k for k, v in _pending_auth.items() if v.get("expires", 0) < now]
    for k in expired:
        _pending_auth.pop(k, None)


AUTH_CALLBACK_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Sign-in complete</title></head>
<body>
<p>Signing you in&hellip;</p>
<script>
(function() {
    // Tokens are in the URL fragment (#access_token=...&provider_token=...)
    const params = new URLSearchParams(window.location.hash.substring(1));
    const access_token = params.get('access_token');          // Supabase JWT
    const provider_token = params.get('provider_token');      // Google access token
    const provider_refresh_token = params.get('provider_refresh_token');
    const email = '';  // extracted from JWT if needed

    if (!access_token) {
        document.body.innerHTML = '<p>Authentication failed &mdash; no token received.</p>';
        return;
    }

    // Generate a random key to store tokens server-side
    const authKey = crypto.randomUUID();

    fetch('/api/v1/auth/store', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            key: authKey,
            access_token: access_token,
            provider_token: provider_token || '',
            provider_refresh_token: provider_refresh_token || ''
        })
    }).then(function(r) {
        if (!r.ok) throw new Error('store failed');
        // Show the key so the plugin can poll for it
        document.body.innerHTML =
            '<p>Sign-in complete! You can close this window.</p>' +
            '<p style="font-size:11px;color:#888">auth_key: ' + authKey + '</p>';
        // Post to opener if available (popup flow)
        if (window.opener) {
            window.opener.postMessage({type: 'svg2ooxml_auth', auth_key: authKey}, '*');
        }
    }).catch(function(err) {
        document.body.innerHTML = '<p>Something went wrong: ' + err.message + '</p>';
    });
})();
</script>
</body>
</html>
"""


@app.get("/auth/callback")
async def auth_callback():
    """Serve static HTML that extracts tokens from the URL fragment."""
    return HTMLResponse(AUTH_CALLBACK_HTML)


class AuthStorePayload(BaseModel):
    key: str
    access_token: str
    provider_token: str = ""
    provider_refresh_token: str = ""


@app.post("/api/v1/auth/store")
async def store_auth(payload: AuthStorePayload):
    """Store auth tokens temporarily, keyed by auth_key (2-min TTL)."""
    _cleanup_expired()
    _pending_auth[payload.key] = {
        "access_token": payload.access_token,
        "provider_token": payload.provider_token,
        "provider_refresh_token": payload.provider_refresh_token,
        "expires": time.time() + _AUTH_TTL,
    }
    return {"ok": True}


@app.get("/api/v1/auth/poll")
async def poll_auth(key: str):
    """Plugin polls this to retrieve tokens. Single-use: deleted after retrieval."""
    _cleanup_expired()
    entry = _pending_auth.pop(key, None)
    if not entry or entry.get("expires", 0) < time.time():
        return {"status": "pending"}
    return {
        "status": "complete",
        "access_token": entry["access_token"],
        "provider_token": entry["provider_token"],
        "provider_refresh_token": entry.get("provider_refresh_token", ""),
    }


class RefreshRequest(BaseModel):
    refresh_token: str


@app.post("/api/v1/auth/refresh")
async def refresh_google_token(payload: RefreshRequest):
    """Refresh an expired Google access token using a refresh token."""
    try:
        from google.oauth2.credentials import Credentials
        import google.auth.transport.requests

        creds = Credentials(
            token=None,
            refresh_token=payload.refresh_token,
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
        )
        creds.refresh(google.auth.transport.requests.Request())
        return {"access_token": creds.token, "expires_in": 3600}
    except Exception as exc:
        logger.warning("Token refresh failed: %s", exc)
        return JSONResponse(
            status_code=401,
            content={"detail": f"Token refresh failed: {exc}"},
        )


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
