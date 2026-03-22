"""API key verification for server-to-server integrations (Apps Script, etc.)."""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request

API_KEY = os.getenv("SVG2OOXML_API_KEY", "")


def verify_api_key(request: Request) -> dict:
    """FastAPI dependency that checks a Bearer token against SVG2OOXML_API_KEY."""
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured on server")

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")

    token = auth[7:]
    if not hmac.compare_digest(token, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return {"auth": "api_key"}


__all__ = ["verify_api_key"]
