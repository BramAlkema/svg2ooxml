"""Helpers for uploading PPTX artefacts to Google Slides."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logging
import os


logger = logging.getLogger(__name__)


try:  # pragma: no cover - optional dependency
    import google.auth
    from google.oauth2.credentials import Credentials as UserCredentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    _GOOGLE_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without Google client libs
    google = None  # type: ignore[assignment]
    UserCredentials = object  # type: ignore[assignment]
    build = None  # type: ignore[assignment]
    HttpError = Exception  # type: ignore[assignment]
    MediaFileUpload = object  # type: ignore[assignment]
    _GOOGLE_AVAILABLE = False


SLIDES_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/presentations",
)


class SlidesPublishingError(RuntimeError):
    """Raised when publishing to Google Slides fails."""


@dataclass(frozen=True)
class SlidesPublishResult:
    """Details about an uploaded Google Slides presentation."""

    file_id: str
    web_view_link: str
    published_url: str
    embed_url: str
    thumbnail_urls: tuple[str, ...]


def upload_pptx_to_slides(
    pptx_path: Path,
    *,
    presentation_title: str | None = None,
    parent_folder_id: str | None = None,
    user_token: str | None = None,
    user_refresh_token: str | None = None,
    user_uid: str | None = None,
) -> SlidesPublishResult:
    """
    Upload ``pptx_path`` to Google Drive and promote it to Google Slides.

    Args:
        pptx_path: Path to PPTX file to upload
        presentation_title: Optional title for the presentation
        parent_folder_id: Optional Google Drive folder ID
        user_token: Optional Firebase ID token for user authentication
        user_refresh_token: Optional Google OAuth refresh token (stored from OAuth flow)
        user_uid: Optional Firebase user UID (used to fetch stored OAuth token if not provided)

    Returns:
        SlidesPublishResult describing the uploaded presentation.
    """

    if not _GOOGLE_AVAILABLE:
        raise SlidesPublishingError(
            "Google API client libraries are not installed. "
            "Install svg2ooxml[cloud] or svg2ooxml[slides] to enable publishing."
        )

    pptx_path = Path(pptx_path)
    if not pptx_path.exists():
        raise SlidesPublishingError(f"PPTX path does not exist: {pptx_path}")

    # Build credentials: user token required for publishing to user's Drive
    try:
        if user_token:
            oauth_refresh_token = user_refresh_token
            if user_uid:
                latest_token = _get_stored_oauth_token(user_uid)
                if latest_token:
                    if oauth_refresh_token and latest_token != oauth_refresh_token:
                        logger.info(
                            "Using refreshed OAuth token from Firestore for user %s",
                            user_uid,
                        )
                    oauth_refresh_token = latest_token
            elif not oauth_refresh_token:
                logger.warning("No user UID provided; cannot fetch stored OAuth token.")

            credentials = _build_user_credentials(
                user_token,
                oauth_refresh_token,
                user_uid=user_uid,
            )
            logger.info(
                "Using user credentials for Slides upload (has_refresh_token=%s)",
                bool(oauth_refresh_token),
            )
        else:
            # Fallback to service account only if no user token
            credentials, _ = google.auth.default(scopes=SLIDES_SCOPES)  # type: ignore[attr-defined]
            logger.warning("No user token provided - using service account (may hit quota issues)")
    except Exception as exc:  # pragma: no cover - defensive
        raise SlidesPublishingError(f"Failed to obtain Google credentials: {exc}") from exc

    try:
        drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        slides_service = build("slides", "v1", credentials=credentials, cache_discovery=False)
    except Exception as exc:  # pragma: no cover - defensive
        raise SlidesPublishingError(f"Failed to initialise Google API clients: {exc}") from exc

    metadata: dict[str, Any] = {
        "name": presentation_title or pptx_path.stem,
        "mimeType": "application/vnd.google-apps.presentation",
    }
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]

    media = MediaFileUpload(
        str(pptx_path),
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        resumable=False,
    )

    try:
        file = (
            drive_service.files()
            .create(body=metadata, media_body=media, fields="id,name,webViewLink")
            .execute()
        )
    except HttpError as exc:
        error_details = _format_http_error(exc)
        logger.warning(
            "Drive upload failed for user %s (fingerprint=%s): %s",
            user_uid or "unknown",
            _token_fingerprint(oauth_refresh_token) if oauth_refresh_token else "n/a",
            error_details,
        )
        raise SlidesPublishingError(f"Drive upload failed: {error_details}") from exc

    file_id = file.get("id")
    if not file_id:
        raise SlidesPublishingError("Drive upload returned no file ID.")

    # Make the presentation world-readable so clients can view it without auth.
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
    except HttpError as exc:
        logger.warning("Failed to publish Drive permissions for %s: %s", file_id, exc)

    try:
        presentation = slides_service.presentations().get(presentationId=file_id).execute()
    except HttpError as exc:
        error_details = _format_http_error(exc)
        raise SlidesPublishingError(f"Failed to fetch Slides metadata: {error_details}") from exc

    thumbnails: list[str] = []
    for slide in presentation.get("slides", []):
        page_id = slide.get("objectId")
        if not page_id:
            continue
        try:
            thumb = (
                slides_service.presentations()
                .pages()
                .getThumbnail(
                    presentationId=file_id,
                    pageObjectId=page_id,
                    thumbnailProperties={"mimeType": "PNG", "thumbnailSize": "LARGE"},
                )
                .execute()
            )
        except HttpError as exc:
            logger.debug("Thumbnail generation failed for %s/%s: %s", file_id, page_id, exc)
            continue
        content_url = thumb.get("contentUrl")
        if content_url:
            thumbnails.append(content_url)

    published_url = f"https://docs.google.com/presentation/d/{file_id}/pub"
    embed_url = f"https://docs.google.com/presentation/d/{file_id}/embed"
    web_view_link = file.get("webViewLink") or published_url

    return SlidesPublishResult(
        file_id=file_id,
        web_view_link=web_view_link,
        published_url=published_url,
        embed_url=embed_url,
        thumbnail_urls=tuple(thumbnails),
    )


def _token_fingerprint(token: str) -> str:
    """Return a short fingerprint for safe logging."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


def _get_stored_oauth_token(user_uid: str) -> str | None:
    """
    Fetch and decrypt stored Google OAuth refresh token from Firestore.

    Args:
        user_uid: Firebase user UID

    Returns:
        Decrypted OAuth refresh token, or None if not found
    """
    try:
        from ..auth.firebase import get_firestore_client
        from ..auth.encryption import decrypt_token

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

        # Decrypt the token
        decrypted_token = decrypt_token(encrypted_token)
        logger.info(
            "Retrieved OAuth refresh token for user %s (fingerprint=%s)",
            user_uid,
            _token_fingerprint(decrypted_token),
        )
        return decrypted_token

    except Exception as exc:
        logger.error("Failed to fetch stored OAuth token for user %s: %s", user_uid, exc)
        return None


def _clear_stored_oauth_token(user_uid: str) -> None:
    """Remove stored OAuth credentials so the user is prompted to reconnect."""
    try:
        from ..auth.firebase import get_firestore_client

        db = get_firestore_client()
        db.collection("users").document(user_uid).update({"google_oauth": {}})
        logger.warning("Cleared stored OAuth token for user %s", user_uid)
    except Exception as exc:
        logger.error("Failed to clear stored OAuth token for user %s: %s", user_uid, exc)


def _build_user_credentials(
    id_token: str,
    refresh_token: str | None = None,
    *,
    user_uid: str | None = None,
) -> UserCredentials:
    """
    Build user credentials from Firebase ID token and optional refresh token.

    Args:
        id_token: Firebase ID token from authenticated user
        refresh_token: Optional Firebase refresh token for long-lived access

    Returns:
        Google OAuth2 user credentials

    Note:
        If refresh_token is provided, creates credentials with auto-refresh capability.
        This requires FIREBASE_WEB_CLIENT_ID and FIREBASE_WEB_CLIENT_SECRET env vars.
        Without refresh token, credentials expire after 1 hour.
    """
    if not _GOOGLE_AVAILABLE:
        raise SlidesPublishingError("Google API client libraries not available")

    # If we have a refresh token, create OAuth credentials with auto-refresh
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
            # Create OAuth credentials with refresh capability
            # Note: We pass token=None to force Google to fetch a fresh access token
            # using the refresh token. Do NOT pass Firebase ID token here.
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
                _token_fingerprint(refresh_token),
            )
            _ensure_access_token(credentials, refresh_token, user_uid)
    else:
        # Firebase ID tokens are OpenID Connect tokens that work with Google APIs
        # but expire after 1 hour without refresh capability
        credentials = UserCredentials(token=id_token)
        logger.info("Created user credentials with ID token only (1 hour expiry)")

    return credentials


def _ensure_access_token(
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
            _token_fingerprint(refresh_token),
        )
    except RefreshError as exc:
        message = str(exc)
        if "invalid_grant" in message.lower():
            logger.warning(
                "Google refresh token invalid for user %s (fingerprint=%s): %s",
                user_uid or "unknown",
                _token_fingerprint(refresh_token),
                message,
            )
            if user_uid:
                _clear_stored_oauth_token(user_uid)
            raise SlidesPublishingError(
                "Google Drive connection expired. Please reconnect from the plugin."
            ) from exc
        raise SlidesPublishingError(f"Failed to refresh Google OAuth token: {exc}") from exc


def _format_http_error(exc: HttpError) -> str:
    """Return a short string describing an HttpError response."""
    try:
        content = exc.content
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
    "SlidesPublishResult",
    "SlidesPublishingError",
    "upload_pptx_to_slides",
]
