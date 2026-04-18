"""Google Drive helpers used for Google Slides export."""

from __future__ import annotations

import io
import logging

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "Google API client libraries are required for Slides publishing."
    ) from exc

logger = logging.getLogger(__name__)


class DriveError(RuntimeError):
    """Raised when Google Drive operations fail."""


class GoogleDriveService:
    """Minimal Drive client that uploads PPTX files and converts them to Slides."""

    def __init__(self, credentials: Credentials) -> None:
        if credentials is None:
            raise ValueError("credentials are required")
        if not credentials.valid or credentials.expired:
            raise DriveError("Invalid or expired Google credentials.")

        self.credentials = credentials
        self.service = build("drive", "v3", credentials=credentials)

    def upload_and_convert_to_slides(
        self,
        *,
        pptx_bytes: bytes,
        title: str,
        parent_folder_id: str | None = None,
    ) -> dict[str, str]:
        if not pptx_bytes:
            raise ValueError("pptx_bytes cannot be empty")
        if not title or not title.strip():
            raise ValueError("title cannot be empty")

        try:
            media = MediaIoBaseUpload(
                io.BytesIO(pptx_bytes),
                mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                resumable=True,
            )

            body: dict[str, object] = {
                "name": title,
                "mimeType": "application/vnd.google-apps.presentation",
            }
            if parent_folder_id:
                body["parents"] = [parent_folder_id]

            result = (
                self.service.files()
                .create(body=body, media_body=media, fields="id,webViewLink")
                .execute()
            )

            slides_id = result["id"]
            logger.info("Uploaded presentation %s (%s)", title, slides_id)

            return {
                "slides_id": slides_id,
                "slides_url": f"https://docs.google.com/presentation/d/{slides_id}/edit",
                "web_view_link": result.get("webViewLink", ""),
            }
        except Exception as exc:  # pragma: no cover - network failure
            logger.error("Drive upload failed: %s", exc)
            raise DriveError(f"Upload failed: {exc}") from exc
