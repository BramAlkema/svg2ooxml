"""Helpers for uploading PPTX artefacts to Google Slides."""

from __future__ import annotations

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
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/presentations.readonly",
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
) -> SlidesPublishResult:
    """
    Upload ``pptx_path`` to Google Drive and promote it to Google Slides.

    Args:
        pptx_path: Path to PPTX file to upload
        presentation_title: Optional title for the presentation
        parent_folder_id: Optional Google Drive folder ID
        user_token: Optional Firebase ID token for user authentication

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

    # Build credentials: user token if provided, otherwise service account
    try:
        if user_token:
            credentials = _build_user_credentials(user_token)
            logger.info("Using user credentials for Slides upload")
        else:
            credentials, _ = google.auth.default(scopes=SLIDES_SCOPES)  # type: ignore[attr-defined]
            logger.info("Using service account credentials for Slides upload (fallback)")
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
        raise SlidesPublishingError(f"Drive upload failed: {exc}") from exc

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
        raise SlidesPublishingError(f"Failed to fetch Slides metadata: {exc}") from exc

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


def _build_user_credentials(id_token: str) -> UserCredentials:
    """
    Build user credentials from Firebase ID token.

    Args:
        id_token: Firebase ID token from authenticated user

    Returns:
        Google OAuth2 user credentials

    Note:
        Firebase ID tokens can be used directly with Google APIs that support
        OpenID Connect (like Drive/Slides). These credentials will expire after
        1 hour. For long-running jobs, consider implementing refresh logic.
    """
    if not _GOOGLE_AVAILABLE:
        raise SlidesPublishingError("Google API client libraries not available")

    # Firebase ID tokens are OpenID Connect tokens that work with Google APIs
    credentials = UserCredentials(token=id_token)

    return credentials


__all__ = ["SlidesPublishResult", "SlidesPublishingError", "upload_pptx_to_slides"]
