"""Upload PPTX bytes to Google Drive as a Google Slides presentation."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    _GOOGLE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _GOOGLE_AVAILABLE = False


def upload_to_google_slides(
    pptx_bytes: bytes,
    access_token: str,
    *,
    title: str = "Untitled",
) -> str:
    """Upload *pptx_bytes* to Google Drive, converting to Google Slides.

    Returns the URL of the created presentation.
    """
    if not _GOOGLE_AVAILABLE:
        raise RuntimeError(
            "Google API client libraries are not installed. "
            "Install svg2ooxml[cloud] to enable Slides publishing."
        )

    creds = Credentials(token=access_token)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.presentation",
    }
    media = MediaIoBaseUpload(
        io.BytesIO(pptx_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    file = (
        drive.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )
    file_id = file["id"]

    logger.info("Uploaded presentation %s as Google Slides (%s)", title, file_id)
    return f"https://docs.google.com/presentation/d/{file_id}/edit"


__all__ = ["upload_to_google_slides"]
