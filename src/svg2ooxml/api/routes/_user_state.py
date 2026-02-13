"""User-state lookups shared by export routes."""

from __future__ import annotations

import logging

from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


async def has_unlimited_exports(firebase_uid: str) -> bool:
    """Return whether the user can bypass quota checks."""

    from ..auth.firebase import get_firestore_client

    def check_unlimited_flag() -> bool:
        logger.info("Checking unlimited flag for user %s", firebase_uid)
        firestore_client = get_firestore_client()
        user_doc = firestore_client.collection("users").document(firebase_uid).get()
        logger.info("User doc exists: %s", user_doc.exists)
        if not user_doc.exists:
            return False

        user_data = user_doc.to_dict()
        has_unlimited_exports = bool(user_data.get("unlimited_exports", False))
        has_admin_flag = bool(user_data.get("admin", False))
        logger.info(
            "User %s flags (unlimited_exports=%s admin=%s)",
            firebase_uid,
            has_unlimited_exports,
            has_admin_flag,
        )
        return has_unlimited_exports or has_admin_flag

    return await run_in_threadpool(check_unlimited_flag)


async def fetch_encrypted_google_oauth_token(firebase_uid: str) -> str | None:
    """Return encrypted refresh token stored for the user, if any."""

    from ..auth.firebase import get_firestore_client

    def fetch_token() -> str | None:
        logger.info("Checking OAuth token for user %s", firebase_uid)
        firestore_client = get_firestore_client()
        user_doc = firestore_client.collection("users").document(firebase_uid).get()
        if not user_doc.exists:
            logger.info("User %s document missing or has no OAuth token", firebase_uid)
            return None

        user_data = user_doc.to_dict()
        google_oauth = user_data.get("google_oauth", {})
        encrypted = google_oauth.get("refresh_token_encrypted")
        logger.info("User %s has OAuth token: %s", firebase_uid, bool(encrypted))
        return encrypted

    return await run_in_threadpool(fetch_token)


__all__ = ["fetch_encrypted_google_oauth_token", "has_unlimited_exports"]
