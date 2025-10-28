from __future__ import annotations

from svg2ooxml.api.models import RequestedFont, SVGFrame
from svg2ooxml.api.services.dependencies import ExportServiceDependencies
from svg2ooxml.api.services.export_service import ExportService
from svg2ooxml.api.services.fakes import (
    FakeFirestoreClient,
    FakeStorageClient,
    OfflineFontFetcher,
)


def test_cache_key_changes_with_content():
    dependencies = ExportServiceDependencies(
        firestore_client=FakeFirestoreClient(project="test"),
        storage_client=FakeStorageClient(project="test"),
        font_fetcher=OfflineFontFetcher(),
    )
    service = ExportService(dependencies=dependencies)
    frame_a = SVGFrame(name="Page", svg_content="<svg>1</svg>", width=100, height=100)
    frame_b = SVGFrame(name="Page", svg_content="<svg>2</svg>", width=100, height=100)
    font = RequestedFont.model_validate("Inter")

    key_one = service._build_conversion_cache_key([frame_a], [font])
    key_two = service._build_conversion_cache_key([frame_b], [font])

    assert key_one != key_two
