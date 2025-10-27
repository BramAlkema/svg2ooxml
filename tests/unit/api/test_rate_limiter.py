from __future__ import annotations

from svg2ooxml.api.middleware.rate_limit import RateLimiter


def test_rate_limiter_enforces_limit() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    allowed, _ = limiter.allow("client")
    assert allowed is True
    allowed, _ = limiter.allow("client")
    assert allowed is True
    allowed, retry_after = limiter.allow("client")
    assert allowed is False
    assert retry_after > 0
