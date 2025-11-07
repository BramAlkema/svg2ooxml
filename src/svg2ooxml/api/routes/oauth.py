"""OAuth routes for connecting user's Google Drive."""

from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.middleware import verify_firebase_token
from ..auth.encryption import decrypt_token, encrypt_token
from ..auth.firebase import get_firestore_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/oauth", tags=["oauth"])

# OAuth configuration
GOOGLE_CLIENT_ID = os.getenv("FIREBASE_WEB_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("FIREBASE_WEB_CLIENT_SECRET")
REDIRECT_URI = "https://powerful-layout-467812-p1.web.app/oauth-callback"


class ExchangePayload(BaseModel):
    """Payload for exchanging authorization code for tokens."""

    code: str
    state: str  # one-time authKey


class AuthKeyResponse(BaseModel):
    """Response containing auth key and connect URL."""

    auth_key: str
    connect_url: str


@router.post("/key", response_model=AuthKeyResponse)
async def create_auth_key(user: dict[str, Any] = Depends(verify_firebase_token)) -> dict[str, str]:
    """
    Create a one-time auth key for OAuth flow.

    The user calls this to get a connect URL that opens the OAuth consent screen.
    The key is stored temporarily and linked to the user's UID.
    """
    uid = user["uid"]

    # Generate secure random key
    key = secrets.token_hex(16)

    # Store in Firestore with expiration
    db = get_firestore_client()
    db.collection("oauth_authkeys").document(key).set(
        {
            "uid": uid,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + 600,  # 10 minutes
        }
    )

    connect_url = f"https://powerful-layout-467812-p1.web.app/oauth-direct.html?key={key}"

    logger.info(f"Created OAuth auth key for user {uid}")

    return {"auth_key": key, "connect_url": connect_url}


@router.post("/exchange")
async def exchange_tokens(payload: ExchangePayload) -> dict[str, bool]:
    """
    Exchange authorization code for OAuth tokens.

    This is called by the oauth-callback.html page after user grants consent.
    It exchanges the authorization code for an access token and refresh token,
    then stores the encrypted refresh token in the user's Firestore document.
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        logger.error("OAuth credentials not configured")
        raise HTTPException(
            status_code=500,
            detail="OAuth not configured. Missing FIREBASE_WEB_CLIENT_ID or FIREBASE_WEB_CLIENT_SECRET",
        )

    db = get_firestore_client()

    # 1) Resolve authKey -> uid
    doc = db.collection("oauth_authkeys").document(payload.state).get()
    if not doc.exists:
        logger.warning(f"Invalid or expired OAuth state: {payload.state}")
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    data = doc.to_dict()
    uid = data["uid"]

    # Check expiration
    if int(time.time()) > data.get("expires_at", 0):
        logger.warning(f"Expired OAuth state for user {uid}")
        doc.reference.delete()
        raise HTTPException(status_code=400, detail="Expired state")

    # 2) Exchange code -> tokens
    logger.info(f"Exchanging OAuth code for user {uid}")

    try:
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": payload.code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
    except Exception as e:
        logger.error(f"OAuth token exchange request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Token exchange request failed: {e}")

    if token_resp.status_code != 200:
        error_text = token_resp.text
        logger.error(f"OAuth token exchange failed for user {uid}: {error_text}")
        raise HTTPException(
            status_code=400, detail=f"Token exchange failed: {error_text}"
        )

    token_json = token_resp.json()
    refresh_token = token_json.get("refresh_token")

    if not refresh_token:
        # This can happen if user previously granted access and Google doesn't
        # return a new refresh token. Solution: revoke at myaccount.google.com/permissions
        # or we already include prompt=consent in oauth-direct.html
        logger.warning(f"No refresh_token returned for user {uid}. User may need to re-consent.")
        raise HTTPException(
            status_code=400,
            detail="No refresh_token returned. Please revoke previous access at "
            "https://myaccount.google.com/permissions and try again",
        )

    # 3) Encrypt and store refresh token
    try:
        encrypted = encrypt_token(refresh_token)
    except Exception as e:
        logger.error(f"Failed to encrypt refresh token: {e}")
        raise HTTPException(status_code=500, detail="Failed to encrypt token")

    user_ref = db.collection("users").document(uid)
    user_ref.set(
        {
            "google_oauth": {
                "refresh_token_encrypted": encrypted,
                "scopes": token_json.get("scope", ""),
                "updated_at": int(time.time()),
            }
        },
        merge=True,
    )

    logger.info(f"Stored Google OAuth refresh token for user {uid}")

    # 4) Mark the authKey as consumed
    doc.reference.delete()

    return {"ok": True}


@router.delete("/revoke")
async def revoke_oauth(user: dict[str, Any] = Depends(verify_firebase_token)) -> dict[str, bool]:
    """
    Revoke stored OAuth refresh token.

    This removes the stored refresh token from Firestore. The user will need
    to reconnect their Google Drive account.
    """
    uid = user["uid"]

    db = get_firestore_client()
    user_ref = db.collection("users").document(uid)

    user_ref.update({"google_oauth": {}})

    logger.info(f"Revoked Google OAuth for user {uid}")

    return {"ok": True}
