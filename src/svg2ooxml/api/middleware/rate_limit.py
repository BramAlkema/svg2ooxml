"""Basic in-process rate limiter middleware."""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._store: dict[str, tuple[int, float]] = {}

    def _now(self) -> float:
        return time.monotonic()

    def allow(self, key: str) -> tuple[bool, float]:
        now = self._now()
        count, reset = self._store.get(key, (0, now + self.window))
        if now >= reset:
            count = 0
            reset = now + self.window
        if count >= self.limit:
            self._store[key] = (count, reset)
            return False, reset - now
        count += 1
        self._store[key] = (count, reset)
        return True, reset - now


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: RateLimiter, header_name: str = "X-Forwarded-For") -> None:
        super().__init__(app)
        self.limiter = limiter
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        # Skip rate limiting for OPTIONS and webhook endpoints
        if request.method == "OPTIONS" or request.url.path.startswith("/api/webhook"):
            return await call_next(request)

        ip = request.headers.get(self.header_name)
        if ip:
            client_id = ip.split(",", 1)[0].strip()
        else:
            client = request.client[0] if request.client else "unknown"
            client_id = client

        allowed, retry_after = self.limiter.allow(client_id)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={"Retry-After": f"{int(retry_after)}"},
            )

        return await call_next(request)


__all__ = ["RateLimiter", "RateLimitMiddleware"]
