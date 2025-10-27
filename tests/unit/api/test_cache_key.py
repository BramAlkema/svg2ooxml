from __future__ import annotations

from svg2ooxml.api.models import RequestedFont, SVGFrame
from svg2ooxml.api.services.export_service import ExportService


class DummyDocument:
    def __init__(self):
        self._data = {}

    def get(self):
        class _Dummy:
            exists = False

        return _Dummy()

    def set(self, *_args, **_kwargs):  # pragma: no cover - not used
        pass

    def delete(self):  # pragma: no cover
        pass


class DummyCollection:
    def document(self, _name):
        return DummyDocument()


class DummyDB:
    def collection(self, _name):
        return DummyCollection()


class DummyBlob:
    def exists(self):
        return False

    def upload_from_filename(self, *args, **kwargs):  # pragma: no cover
        pass


class DummyBucket:
    def exists(self):
        return True

    def add_lifecycle_delete_rule(self, *args, **kwargs):  # pragma: no cover
        pass

    def patch(self):  # pragma: no cover
        pass

    def blob(self, _name):
        return DummyBlob()


class DummyStorageClient:
    def bucket(self, _name):
        return DummyBucket()


def test_cache_key_changes_with_content():
    service = ExportService(db_client=DummyDB(), storage_client=DummyStorageClient())
    frame_a = SVGFrame(name="Page", svg_content="<svg>1</svg>", width=100, height=100)
    frame_b = SVGFrame(name="Page", svg_content="<svg>2</svg>", width=100, height=100)
    font = RequestedFont.model_validate("Inter")

    key_one = service._build_conversion_cache_key([frame_a], [font])
    key_two = service._build_conversion_cache_key([frame_b], [font])

    assert key_one != key_two
