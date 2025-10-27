"""Test doubles for Firestore, Cloud Storage, and font services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any, Dict, Iterable, Iterator

from svg2ooxml.services.fonts import FontFetcher, FontSource


# ---------------------------------------------------------------------------
# Firestore fakes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _StoredDocument:
    data: dict[str, Any]


class FakeDocumentSnapshot:
    """Minimal Firestore snapshot exposing ``exists`` and ``to_dict``."""

    def __init__(self, data: dict[str, Any] | None, reference: "FakeDocumentReference") -> None:
        self._data = data
        self.reference = reference

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data or {})


class FakeDocumentReference:
    """In-memory document reference."""

    def __init__(self, store: "FakeFirestoreClient", path: tuple[str, ...]) -> None:
        self._store = store
        self._path = path

    def set(self, data: dict[str, Any]) -> None:
        self._store._documents[self._path] = _StoredDocument(dict(data))

    def update(self, data: dict[str, Any]) -> None:
        entry = self._store._documents.get(self._path)
        if entry is None:
            entry = _StoredDocument({})
            self._store._documents[self._path] = entry
        entry.data.update(data)

    def get(self) -> FakeDocumentSnapshot:
        entry = self._store._documents.get(self._path)
        payload = entry.data if entry is not None else None
        return FakeDocumentSnapshot(payload, self)

    def delete(self) -> None:
        self._store._documents.pop(self._path, None)

    def collection(self, name: str) -> "FakeCollectionReference":
        return FakeCollectionReference(self._store, self._path + (name,))


class FakeCollectionReference:
    """Collection reference supporting ``document`` and ``stream``."""

    def __init__(self, store: "FakeFirestoreClient", path: tuple[str, ...]) -> None:
        self._store = store
        self._path = path

    def document(self, doc_id: str) -> FakeDocumentReference:
        return FakeDocumentReference(self._store, self._path + (doc_id,))

    def stream(self) -> Iterator[FakeDocumentSnapshot]:
        prefix = self._path
        prefix_len = len(prefix)
        for path, entry in list(self._store._documents.items()):
            if len(path) == prefix_len + 1 and path[:prefix_len] == prefix:
                reference = FakeDocumentReference(self._store, path)
                yield FakeDocumentSnapshot(entry.data, reference)


class FakeFirestoreClient:
    """Very small subset of Firestore used by ``ExportService``."""

    def __init__(self, *, project: str | None = None) -> None:
        self.project = project
        self._documents: Dict[tuple[str, ...], _StoredDocument] = {}

    def collection(self, name: str) -> FakeCollectionReference:
        return FakeCollectionReference(self, (name,))


# ---------------------------------------------------------------------------
# Cloud Storage fakes
# ---------------------------------------------------------------------------


class FakeBlob:
    """In-memory blob backing onto a ``FakeBucket`` store."""

    def __init__(self, bucket: "FakeBucket", name: str) -> None:
        self._bucket = bucket
        self.name = name

    def exists(self) -> bool:
        return self.name in self._bucket._objects

    def upload_from_filename(self, filename: str, content_type: str | None = None) -> None:  # noqa: ARG002
        path = Path(filename)
        self._bucket._objects[self.name] = path.read_bytes()

    def download_to_filename(self, filename: str) -> None:
        target = Path(filename)
        data = self._bucket._objects.get(self.name)
        if data is None:
            raise FileNotFoundError(self.name)
        target.write_bytes(data)

    def delete(self) -> None:
        self._bucket._objects.pop(self.name, None)

    def generate_signed_url(self, *, version: str, expiration: int, method: str) -> str:  # noqa: ARG002
        return f"fake://{self._bucket.name}/{self.name}"


class FakeBucket:
    """Subset of the Cloud Storage bucket API."""

    def __init__(self, client: "FakeStorageClient", name: str) -> None:
        self._client = client
        self.name = name
        self._objects: Dict[str, bytes] = client._objects.setdefault(name, {})

    def exists(self) -> bool:
        return self.name in self._client._created

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)

    def add_lifecycle_delete_rule(self, **_: Any) -> None:
        return None

    def patch(self) -> None:
        return None

    def list_blobs(self, prefix: str = "") -> Iterator[FakeBlob]:
        for name in list(self._objects.keys()):
            if name.startswith(prefix):
                yield FakeBlob(self, name)


class FakeStorageClient:
    """In-memory Cloud Storage client."""

    def __init__(self, *, project: str | None = None) -> None:
        self.project = project
        self._buckets: Dict[str, FakeBucket] = {}
        self._created: set[str] = set()
        self._objects: Dict[str, Dict[str, bytes]] = {}

    def bucket(self, name: str) -> FakeBucket:
        bucket = self._buckets.get(name)
        if bucket is None:
            bucket = FakeBucket(self, name)
            self._buckets[name] = bucket
        return bucket

    def create_bucket(self, name: str, location: str | None = None) -> FakeBucket:  # noqa: ARG002
        bucket = FakeBucket(self, name)
        self._buckets[name] = bucket
        self._created.add(name)
        return bucket


# ---------------------------------------------------------------------------
# Font helper
# ---------------------------------------------------------------------------


class OfflineFontFetcher(FontFetcher):
    """FontFetcher that never touches the network and can be pre-seeded."""

    def __init__(self, registry: dict[str, Path] | None = None) -> None:
        cache_dir = Path(tempfile.gettempdir()) / "svg2ooxml-offline-fonts"
        super().__init__(cache_directory=cache_dir, allow_network=False)
        self._registry: Dict[str, Path] = {url: Path(path) for url, path in (registry or {}).items()}
        self.requests: list[FontSource] = []

    def register(self, url: str, path: Path | str) -> None:
        self._registry[url] = Path(path)

    def fetch(self, source: FontSource) -> Path | None:
        self.requests.append(source)
        return self._registry.get(source.url)

    def fetch_sources(self, sources: Iterable[FontSource]) -> list[tuple[FontSource, Path]]:
        results: list[tuple[FontSource, Path]] = []
        for source in sources:
            path = self.fetch(source)
            if path is not None:
                results.append((source, path))
        return results


__all__ = [
    "FakeFirestoreClient",
    "FakeStorageClient",
    "FakeCollectionReference",
    "FakeDocumentReference",
    "FakeDocumentSnapshot",
    "OfflineFontFetcher",
]
