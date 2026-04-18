"""Supabase JWT verification using PyJWT (HS256)."""

import logging
import os

import jwt
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


def verify_supabase_token(request: Request) -> dict:
    """FastAPI dependency that verifies a Supabase JWT and returns uid + email."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = auth[7:]
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return {"uid": payload["sub"], "email": payload.get("email")}
    except jwt.InvalidTokenError as exc:
        logger.warning("Supabase token verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token") from exc


__all__ = ["verify_supabase_token"]
