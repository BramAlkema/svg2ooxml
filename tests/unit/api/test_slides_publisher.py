from __future__ import annotations

import pytest

from svg2ooxml.api.services import slides_publisher as sp


class _FakeCredentials:  # minimal shim for google auth default output
    def __init__(self) -> None:
        self.valid = True


class _FakeExecute:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


def test_upload_pptx_to_slides(tmp_path, monkeypatch):
    pptx_path = tmp_path / "deck.pptx"
    pptx_path.write_bytes(b"pptx")

    def fake_default(scopes):  # noqa: ARG001
        return _FakeCredentials(), "test-project"

    drive_calls = {}

    class FakeDriveFiles:
        def create(self, body, media_body, fields):  # noqa: ARG002
            drive_calls["metadata"] = body
            return _FakeExecute({"id": "file123", "name": "Deck", "webViewLink": "https://drive/view"})

    class FakeDrivePermissions:
        def create(self, fileId, body):  # noqa: ARG002
            drive_calls["permissions"] = fileId
            return _FakeExecute(None)

    class FakeDriveService:
        def files(self):
            return FakeDriveFiles()

        def permissions(self):
            return FakeDrivePermissions()

    class FakeSlidesPresentations:
        def get(self, presentationId):  # noqa: ARG002
            return _FakeExecute({"slides": [{"objectId": "slide1"}]})

        def pages(self):
            return FakeSlidesPages()

    class FakeSlidesPages:
        def getThumbnail(self, presentationId, pageObjectId, thumbnailProperties):  # noqa: ARG002
            return _FakeExecute({"contentUrl": "https://thumb"})

    class FakeSlidesService:
        def presentations(self):
            return FakeSlidesPresentations()

    def fake_build(name, version, **kwargs):  # noqa: ARG001
        if name == "drive":
            return FakeDriveService()
        if name == "slides":
            return FakeSlidesService()
        raise AssertionError("Unexpected service")

    if sp.google is None:  # pragma: no cover - happens when google libs missing
        class _FakeGoogle:
            pass

        sp.google = _FakeGoogle()  # type: ignore[assignment]
        sp.google.auth = type("auth", (), {})()

    monkeypatch.setattr(sp, "_GOOGLE_AVAILABLE", True, raising=False)
    monkeypatch.setattr(sp.google.auth, "default", fake_default)
    monkeypatch.setattr(sp, "build", fake_build)
    monkeypatch.setattr(sp, "MediaFileUpload", lambda *args, **kwargs: object())

    result = sp.upload_pptx_to_slides(pptx_path, presentation_title="Test deck")

    assert result.file_id == "file123"
    assert result.web_view_link == "https://drive/view"
    assert result.embed_url == "https://docs.google.com/presentation/d/file123/embed"
    assert result.thumbnail_urls == ("https://thumb",)
    assert drive_calls["metadata"]["name"] == "Test deck"


def test_upload_pptx_to_slides_requires_google_clients(tmp_path, monkeypatch):
    pptx_path = tmp_path / "deck.pptx"
    pptx_path.write_bytes(b"pptx")

    monkeypatch.setattr(sp, "_GOOGLE_AVAILABLE", False, raising=False)

    with pytest.raises(sp.SlidesPublishingError):
        sp.upload_pptx_to_slides(pptx_path)
