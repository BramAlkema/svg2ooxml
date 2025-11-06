from __future__ import annotations

import pytest

from svg2ooxml.api.models import SVGFrame
from svg2ooxml.api.services import export_service as export_service_module
from svg2ooxml.api.services.converter import ConversionArtifacts, FontDiagnostics
from svg2ooxml.api.services.dependencies import ExportServiceDependencies
from svg2ooxml.api.services.export_service import ExportService, ExportStatus
from svg2ooxml.api.services.fakes import FakeFirestoreClient, FakeStorageClient, OfflineFontFetcher
from svg2ooxml.api.services.slides_publisher import SlidesPublishResult, SlidesPublishingError


@pytest.fixture()
def export_service(monkeypatch: pytest.MonkeyPatch) -> ExportService:
    dependencies = ExportServiceDependencies(
        firestore_client=FakeFirestoreClient(project="test"),
        storage_client=FakeStorageClient(project="test"),
        font_fetcher=OfflineFontFetcher(),
    )
    service = ExportService(dependencies=dependencies)

    def fake_render(frames, output_path, **kwargs):
        output_path.write_bytes(b"PPTX")
        return ConversionArtifacts(
            pptx_path=output_path,
            slide_count=len(frames),
            aggregated_trace={"stage_totals": {}, "geometry_totals": {}, "paint_totals": {}},
            packaging_report={"stage_totals": {}},
            page_titles=[frame.name or "Slide 1" for frame in frames],
            font_diagnostics=FontDiagnostics(embedded_fonts=[], missing_fonts=[]),
        )

    monkeypatch.setattr(export_service_module, "render_pptx_for_frames", fake_render)
    monkeypatch.setattr(ExportService, "_upload_pptx", lambda self, job_id, pptx_path: "https://example.com/pptx")
    return service


def _create_slides_job(service: ExportService) -> str:
    frame = SVGFrame(
        name="Struct use",
        svg_content="<svg width='1' height='1'></svg>",
        width=1.0,
        height=1.0,
    )
    return service.create_job(
        frames=[frame],
        figma_file_id="file-123",
        figma_file_name="Example Deck",
        output_format="slides",
        fonts=[],
    )


def test_process_job_publishes_slides(monkeypatch: pytest.MonkeyPatch, export_service: ExportService) -> None:
    captured: dict[str, SlidesPublishResult] = {}

    def fake_publish(self, pptx_path, *, job_id, job_data, cache_key, user_token=None, user_refresh_token=None):
        result = SlidesPublishResult(
            file_id="slides-file",
            web_view_link="https://slides.example/view",
            published_url="https://slides.example/pub",
            embed_url="https://slides.example/embed",
            thumbnail_urls=("https://slides.example/thumb1.png",),
        )
        captured["result"] = result
        return result

    monkeypatch.setattr(ExportService, "_publish_to_slides", fake_publish)

    job_id = _create_slides_job(export_service)
    export_service.process_job(job_id)

    status = export_service.get_job_status(job_id)

    assert status["status"] == ExportStatus.COMPLETED.value
    assert status["slides_url"] == "https://slides.example/view"
    assert status["slides_embed_url"] == "https://slides.example/embed"
    assert status["thumbnail_urls"] == ["https://slides.example/thumb1.png"]
    assert status["slides_presentation_id"] == "slides-file"
    assert status.get("slides_error") is None
    assert status["conversion_summary"].get("resvg_metrics", {}) == {}
    assert "result" in captured


def test_process_job_failure_when_slides_publish_errors(
    monkeypatch: pytest.MonkeyPatch,
    export_service: ExportService,
) -> None:
    def fake_publish(self, pptx_path, *, job_id, job_data, cache_key, user_token=None, user_refresh_token=None):
        raise SlidesPublishingError("Slides upload failed")

    monkeypatch.setattr(ExportService, "_publish_to_slides", fake_publish)

    job_id = _create_slides_job(export_service)
    export_service.process_job(job_id)

    status = export_service.get_job_status(job_id)
    assert status["status"] == ExportStatus.COMPLETED.value
    assert status["slides_url"] is None
    assert status["slides_error"] == "Slides upload failed"
