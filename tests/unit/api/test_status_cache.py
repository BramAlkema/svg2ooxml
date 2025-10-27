from __future__ import annotations

import time

from svg2ooxml.api.caching.status import _JobStatusCache


def test_status_cache_stores_and_expires() -> None:
    cache = _JobStatusCache(ttl_seconds=0.1)
    payload = {"status": "queued"}
    cache.set("job-1", payload)
    assert cache.get("job-1") == payload
    time.sleep(0.2)
    assert cache.get("job-1") is None
