"""Helpers for uploading PPTX artefacts to Google Slides."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .slides_auth import (
    build_user_credentials,
    format_http_error,
    get_stored_oauth_token,
    token_fingerprint,
)
from .slides_types import SLIDES_SCOPES, SlidesPublishingError, SlidesPublishResult

logger = logging.getLogger(__name__)


try:  # pragma: no cover - optional dependency
    import google.auth
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    _GOOGLE_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without Google client libs
    google = None  # type: ignore[assignment]
    build = None  # type: ignore[assignment]
    HttpError = Exception  # type: ignore[assignment]
    MediaFileUpload = object  # type: ignore[assignment]
    _GOOGLE_AVAILABLE = False


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

    # Build credentials: user token required for publishing to user's Drive.
    try:
        if user_token:
            oauth_refresh_token = user_refresh_token
            if user_uid:
                latest_token = get_stored_oauth_token(user_uid)
                if latest_token:
                    if oauth_refresh_token and latest_token != oauth_refresh_token:
                        logger.info(
                            "Using refreshed OAuth token from Firestore for user %s",
                            user_uid,
                        )
                    oauth_refresh_token = latest_token
            elif not oauth_refresh_token:
                logger.warning("No user UID provided; cannot fetch stored OAuth token.")

            credentials = build_user_credentials(
                user_token,
                oauth_refresh_token,
                user_uid=user_uid,
            )
            logger.info(
                "Using user credentials for Slides upload (has_refresh_token=%s)",
                bool(oauth_refresh_token),
            )
        else:
            # Fallback to service account only if no user token.
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
        error_details = format_http_error(exc)
        logger.warning(
            "Drive upload failed for user %s (fingerprint=%s): %s",
            user_uid or "unknown",
            token_fingerprint(oauth_refresh_token) if oauth_refresh_token else "n/a",
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
        error_details = format_http_error(exc)
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


__all__ = [
    "SlidesPublishResult",
    "SlidesPublishingError",
    "upload_pptx_to_slides",
]
