"""Credential and token helpers for Slides publishing."""

from __future__ import annotations

import hashlib
import json
import logging
import os

from .slides_types import SLIDES_SCOPES, SlidesPublishingError

logger = logging.getLogger(__name__)


try:  # pragma: no cover - optional dependency
    from google.oauth2.credentials import Credentials as UserCredentials

    _GOOGLE_CREDENTIALS_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without Google client libs
    UserCredentials = object  # type: ignore[assignment]
    _GOOGLE_CREDENTIALS_AVAILABLE = False


def token_fingerprint(token: str) -> str:
    """Return a short fingerprint for safe logging."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


def get_stored_oauth_token(user_uid: str) -> str | None:
    """Fetch and decrypt stored Google OAuth refresh token from Firestore."""

    try:
        from ..auth.encryption import decrypt_token
        from ..auth.firebase import get_firestore_client

        db = get_firestore_client()
        user_doc = db.collection("users").document(user_uid).get()

        if not user_doc.exists:
            logger.warning("User document not found for uid %s", user_uid)
            return None

        user_data = user_doc.to_dict()
        google_oauth = user_data.get("google_oauth", {})
        encrypted_token = google_oauth.get("refresh_token_encrypted")

        if not encrypted_token:
            logger.info("No stored OAuth refresh token for user %s", user_uid)
            return None

        decrypted_token = decrypt_token(encrypted_token)
        logger.info(
            "Retrieved OAuth refresh token for user %s (fingerprint=%s)",
            user_uid,
            token_fingerprint(decrypted_token),
        )
        return decrypted_token

    except Exception as exc:
        logger.error("Failed to fetch stored OAuth token for user %s: %s", user_uid, exc)
        return None


def clear_stored_oauth_token(user_uid: str) -> None:
    """Remove stored OAuth credentials so the user is prompted to reconnect."""

    try:
        from ..auth.firebase import get_firestore_client

        db = get_firestore_client()
        db.collection("users").document(user_uid).update({"google_oauth": {}})
        logger.warning("Cleared stored OAuth token for user %s", user_uid)
    except Exception as exc:
        logger.error("Failed to clear stored OAuth token for user %s: %s", user_uid, exc)


def build_user_credentials(
    id_token: str,
    refresh_token: str | None = None,
    *,
    user_uid: str | None = None,
) -> UserCredentials:
    """Build user credentials from Firebase ID token and optional refresh token."""

    if not _GOOGLE_CREDENTIALS_AVAILABLE:
        raise SlidesPublishingError("Google API client libraries not available")

    if refresh_token:
        client_id = os.getenv("FIREBASE_WEB_CLIENT_ID")
        client_secret = os.getenv("FIREBASE_WEB_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.warning(
                "Refresh token provided but FIREBASE_WEB_CLIENT_ID or "
                "FIREBASE_WEB_CLIENT_SECRET not set. Using ID token only."
            )
            credentials = UserCredentials(token=id_token)
        else:
            credentials = UserCredentials(
                token=None,  # Let Google fetch access token from refresh token
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=SLIDES_SCOPES,
            )
            logger.info(
                "Created user credentials with refresh token support (fingerprint=%s)",
                token_fingerprint(refresh_token),
            )
            ensure_access_token(credentials, refresh_token, user_uid)
    else:
        credentials = UserCredentials(token=id_token)
        logger.info("Created user credentials with ID token only (1 hour expiry)")

    return credentials


def ensure_access_token(
    credentials: UserCredentials,
    refresh_token: str,
    user_uid: str | None = None,
) -> None:
    """Force-refresh credentials so we detect invalid_grant immediately."""

    try:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request as GoogleAuthRequest

        request = GoogleAuthRequest()
        credentials.refresh(request)
        logger.info(
            "Successfully refreshed Google OAuth credentials (user=%s, fingerprint=%s)",
            user_uid or "unknown",
            token_fingerprint(refresh_token),
        )
    except RefreshError as exc:
        message = str(exc)
        if "invalid_grant" in message.lower():
            logger.warning(
                "Google refresh token invalid for user %s (fingerprint=%s): %s",
                user_uid or "unknown",
                token_fingerprint(refresh_token),
                message,
            )
            if user_uid:
                clear_stored_oauth_token(user_uid)
            raise SlidesPublishingError(
                "Google Drive connection expired. Please reconnect from the plugin."
            ) from exc
        raise SlidesPublishingError(f"Failed to refresh Google OAuth token: {exc}") from exc


def format_http_error(exc: Exception) -> str:
    """Return a short string describing an HttpError-like response."""

    try:
        content = getattr(exc, "content", None)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
    except Exception:
        content = "<unavailable>"
    secondary_message = None
    if content and isinstance(content, str):
        try:
            payload = json.loads(content)
            secondary_message = payload.get("error", {}).get("message")
        except Exception:
            secondary_message = None

    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "resp", None), "status", "?")
    reason = getattr(exc, "reason", None)
    if not reason:
        reason = getattr(getattr(exc, "resp", None), "reason", None)
    if not reason:
        reason = getattr(exc, "error_details", None)

    if secondary_message and secondary_message != reason:
        reason = f"{reason or ''} ({secondary_message})".strip()

    return f"status={status}, reason={reason or 'unknown'}, body={content}"


__all__ = [
    "build_user_credentials",
    "clear_stored_oauth_token",
    "format_http_error",
    "get_stored_oauth_token",
    "token_fingerprint",
]
