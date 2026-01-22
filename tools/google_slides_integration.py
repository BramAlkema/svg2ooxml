"""Helpers for uploading PPTX artifacts to Google Slides for visual review."""

from __future__ import annotations

import io
import os
import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:  # pragma: no cover - optional dependency
    from google.auth.transport.requests import Request
    from google.auth import default as google_auth_default
    from google.auth.exceptions import DefaultCredentialsError
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

if not GOOGLE_AVAILABLE:  # pragma: no cover - optional dependency message
    print(
        "⚠️  Google API libraries not available. "
        "Install with: pip install 'svg2ooxml[slides]'"
    )

# Required scopes
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/presentations.readonly",
]


@dataclass
class SlidesInfo:
    """Information about an uploaded Google Slides presentation."""

    file_id: str
    name: str
    web_view_link: str
    published_url: str
    embed_url: str
    thumbnail_link: Optional[str] = None
    slide_count: int = 0


class GoogleSlidesUploader:
    """Upload PPTX files to Google Drive and convert them to Google Slides."""

    def __init__(self, credentials_path: Optional[Path] = None) -> None:
        if not GOOGLE_AVAILABLE:  # pragma: no cover - optional dependency
            raise ImportError(
                "Google API libraries not available. "
                "Install svg2ooxml[slides] to enable Slides integration."
            )

        base_dir = Path.home() / ".svg2ooxml"
        self.credentials_path = credentials_path or (base_dir / "credentials.json")
        self.token_path = base_dir / "token.pickle"
        self.creds: Optional[Credentials] = None
        self.drive_service = None
        self.slides_service = None

    def authenticate(self) -> bool:
        """Authenticate with Google APIs (Drive + Slides)."""

        print("🔐 Authenticating with Google APIs...")

        if self.token_path.exists():
            with self.token_path.open("rb") as token_file:
                self.creds = pickle.load(token_file)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                print("🔄 Refreshing expired credentials...")
                self.creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    try:
                        self.creds, _ = google_auth_default(scopes=SCOPES)
                    except DefaultCredentialsError:
                        self._print_credentials_instructions()
                        return False
                    print("✅ Using application default credentials.")
                    self.drive_service = build("drive", "v3", credentials=self.creds)
                    self.slides_service = build("slides", "v1", credentials=self.creds)
                    return True

                print("🌐 Opening browser for authentication...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with self.token_path.open("wb") as token_file:
                pickle.dump(self.creds, token_file)

        self.drive_service = build("drive", "v3", credentials=self.creds)
        self.slides_service = build("slides", "v1", credentials=self.creds)

        print("✅ Authentication successful")
        return True

    def upload_and_convert(
        self,
        pptx_path: Path,
        folder_id: Optional[str] = None,
    ) -> Optional[SlidesInfo]:
        """Upload a PPTX file and convert it to a Google Slides presentation."""

        if not self.drive_service:
            if not self.authenticate():
                return None

        print(f"📤 Uploading {pptx_path.name} to Google Drive...")

        try:
            metadata: Dict[str, Any] = {
                "name": pptx_path.stem,
                "mimeType": "application/vnd.google-apps.presentation",
            }
            if folder_id:
                metadata["parents"] = [folder_id]

            media = MediaFileUpload(
                str(pptx_path),
                mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                resumable=True,
            )

            file = (
                self.drive_service.files()
                .create(body=metadata, media_body=media, fields="id,name,webViewLink,thumbnailLink")
                .execute()
            )

            file_id = file.get("id")
            print(f"✅ Uploaded as Google Slides: {file_id}")

            print("🌐 Publishing presentation...")
            self.drive_service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()

            presentation = self.slides_service.presentations().get(
                presentationId=file_id
            ).execute()
            slide_count = len(presentation.get("slides", []))

            info = SlidesInfo(
                file_id=file_id,
                name=file.get("name"),
                web_view_link=file.get("webViewLink"),
                published_url=f"https://docs.google.com/presentation/d/{file_id}/pub",
                embed_url=f"https://docs.google.com/presentation/d/{file_id}/embed",
                thumbnail_link=file.get("thumbnailLink"),
                slide_count=slide_count,
            )

            print(f"✅ Published presentation with {slide_count} slides")
            print(f"🔗 View: {info.web_view_link}")
            print(f"📊 Embed: {info.embed_url}")
            return info

        except HttpError as error:  # pragma: no cover - network failure
            print(f"❌ Upload failed: {error}")
            return None

    def download_presentation(self, file_id: str, destination: Path) -> bool:
        """Download a Google Slides presentation as PPTX."""

        if not self.drive_service:
            if not self.authenticate():
                return False

        try:
            request = self.drive_service.files().export_media(
                fileId=file_id,
                mimeType="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()
                time.sleep(0.1)

            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(fh.getvalue())
            print(f"✅ Downloaded PPTX to {destination}")
            return True
        except HttpError as error:  # pragma: no cover - network failure
            print(f"❌ Download failed: {error}")
            return False

    def upload_service_account(
        self,
        pptx_path: Path,
        *,
        service_account_file: Path,
        presentation_title: Optional[str] = None,
    ) -> Optional[SlidesInfo]:
        """Upload using a service account credentials file."""

        credentials = service_account.Credentials.from_service_account_file(
            str(service_account_file),
            scopes=SCOPES,
        )
        delegated = credentials.with_subject(credentials.service_account_email)

        drive_service = build("drive", "v3", credentials=delegated)
        slides_service = build("slides", "v1", credentials=delegated)

        metadata = {
            "name": presentation_title or pptx_path.stem,
            "mimeType": "application/vnd.google-apps.presentation",
        }

        media = MediaFileUpload(
            str(pptx_path),
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            resumable=True,
        )

        file = (
            drive_service.files()
            .create(body=metadata, media_body=media, fields="id,name,webViewLink")
            .execute()
        )

        file_id = file.get("id")
        presentation = slides_service.presentations().get(presentationId=file_id).execute()

        return SlidesInfo(
            file_id=file_id,
            name=file.get("name"),
            web_view_link=file.get("webViewLink"),
            published_url=f"https://docs.google.com/presentation/d/{file_id}/pub",
            embed_url=f"https://docs.google.com/presentation/d/{file_id}/embed",
            slide_count=len(presentation.get("slides", [])),
        )

    @staticmethod
    def _print_credentials_instructions() -> None:
        print(f"❌ Credentials file not found.")
        print("\n📝 To enable Google Slides integration:")
        print("1. Visit https://console.cloud.google.com/")
        print("2. Create a project and enable Drive & Slides APIs")
        print("3. Create OAuth 2.0 desktop credentials")
        print("4. Download credentials.json and save it to ~/.svg2ooxml/credentials.json")
        print("\nOr, with gcloud:")
        print(
            "gcloud auth application-default login "
            "--scopes=https://www.googleapis.com/auth/drive.file,"
            "https://www.googleapis.com/auth/drive,"
            "https://www.googleapis.com/auth/presentations.readonly"
        )


__all__ = ["GoogleSlidesUploader", "SlidesInfo"]
