from __future__ import annotations

import importlib.util
import sys
import types


if importlib.util.find_spec("google.cloud") is None:  # pragma: no cover - used for test isolation
    cloud_pkg = types.ModuleType("google.cloud")
    cloud_pkg.__path__ = []  # type: ignore[attr-defined]

    class _StubClient:  # pragma: no cover - simple stub
        def __init__(self, *args, **kwargs):
            pass

        def collection(self, *_args, **_kwargs):
            raise RuntimeError("Stub Firestore client does not provide collections")

    firestore_mod = types.ModuleType("google.cloud.firestore")
    firestore_mod.Client = _StubClient

    class _StubStorageClient:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            pass

        def bucket(self, *_args, **_kwargs):
            raise RuntimeError("Stub storage client does not provide buckets")

    storage_mod = types.ModuleType("google.cloud.storage")
    storage_mod.Client = _StubStorageClient

    cloud_pkg.firestore = firestore_mod
    cloud_pkg.storage = storage_mod

    sys.modules["google.cloud"] = cloud_pkg
    sys.modules["google.cloud.firestore"] = firestore_mod
    sys.modules["google.cloud.storage"] = storage_mod
