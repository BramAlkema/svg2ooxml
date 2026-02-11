"""Firebase Admin SDK initialization and token verification."""
import logging
import os
from typing import Any

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, firestore
from google.auth.transport import requests
from google.oauth2 import id_token

logger = logging.getLogger(__name__)


def initialize_firebase() -> None:
    """Initialize Firebase Admin SDK.

    Uses service account credentials from Secret Manager
    (mounted at /secrets/firebase-service-account).
    """
    if firebase_admin._apps:
        logger.info("Firebase already initialized")
        return

    try:
        # Option 1: Use service account key file (from Secret Manager)
        key_path = os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_PATH",
            "/secrets/firebase-service-account"
        )

        if os.path.exists(key_path):
            cred = credentials.Certificate(key_path)
            logger.info(f"Using service account from {key_path}")
        else:
            # Option 2: Application Default Credentials (fallback)
            cred = credentials.ApplicationDefault()
            logger.info("Using Application Default Credentials")

        firebase_admin.initialize_app(cred, {
            'projectId': os.getenv('FIREBASE_PROJECT_ID', 'svg2ooxml'),
        })

        logger.info("Firebase Admin SDK initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        raise


def get_firestore_client():
    """Get Firestore client from Firebase Admin SDK.

    Returns:
        Firestore client instance

    Raises:
        RuntimeError: If Firebase is not initialized
    """
    if not firebase_admin._apps:
        logger.warning("Firebase not initialized, initializing now...")
        initialize_firebase()

    return firestore.client()


def verify_google_identity_token(token: str) -> dict[str, Any]:
    """Verify Google Identity token (from gcloud auth print-identity-token).

    This is used for internal testing/development with gcloud CLI.

    Args:
        token: Google Identity token

    Returns:
        Dictionary with user claims:
        - uid: User ID (from 'sub' claim)
        - email: User email
        - email_verified: Whether email is verified

    Raises:
        ValueError: If token is invalid or expired
    """
    try:
        # Verify token signature and claims
        # This accepts Google Identity tokens with various audiences
        request = requests.Request()
        claims = id_token.verify_oauth2_token(token, request)

        # Extract user info in Firebase-compatible format
        user_info = {
            "uid": claims["sub"],  # Subject claim = user ID
            "email": claims.get("email"),
            "email_verified": claims.get("email_verified", False),
            "aud": claims.get("aud"),
            "iss": claims.get("iss"),
        }

        logger.info(
            "Google Identity token verified successfully",
            extra={
                "user_id": user_info["uid"],
                "email": user_info.get("email", "unknown"),
                "token_type": "google_identity"
            }
        )

        return user_info

    except Exception as e:
        logger.warning(f"Google Identity token verification failed: {e}")
        raise ValueError(f"Invalid Google Identity token: {e}") from e


def verify_id_token(token_str: str) -> dict[str, Any]:
    """Verify ID token - supports both Firebase and Google Identity tokens.

    Args:
        token_str: Firebase ID token OR Google Identity token (from gcloud)

    Returns:
        Dictionary with user claims:
        - uid: User ID
        - email: User email (if available)
        - email_verified: Whether email is verified
        - auth_time: Authentication timestamp (Firebase tokens only)
        - exp: Expiration timestamp

    Raises:
        firebase_admin.auth.InvalidIdTokenError: If token is invalid
        firebase_admin.auth.ExpiredIdTokenError: If token is expired
        firebase_admin.auth.RevokedIdTokenError: If token is revoked
        ValueError: If Google Identity token is invalid
    """
    try:
        # First try Firebase token verification (for production Figma plugin users)
        decoded_token = firebase_auth.verify_id_token(token_str)

        logger.info(
            "Firebase token verified successfully",
            extra={
                "user_id": decoded_token["uid"],
                "email": decoded_token.get("email", "unknown"),
                "token_type": "firebase"
            }
        )

        return decoded_token

    except firebase_auth.InvalidIdTokenError as e:
        # If Firebase verification fails due to audience mismatch,
        # try Google Identity token (for gcloud development/testing)
        error_msg = str(e)
        if "incorrect \"aud\"" in error_msg or "audience" in error_msg.lower():
            logger.info("Attempting Google Identity token verification (gcloud fallback)")
            try:
                return verify_google_identity_token(token_str)
            except ValueError as google_error:
                # Both verification methods failed
                logger.warning(
                    f"Token verification failed for both Firebase and Google Identity: "
                    f"Firebase error: {e}, Google error: {google_error}"
                )
                raise firebase_auth.InvalidIdTokenError(
                    "Token verification failed. Not a valid Firebase or Google Identity token."
                ) from e
        else:
            # Firebase error for a different reason (expired, revoked, etc.)
            logger.warning(f"Firebase token verification failed: {e}")
            raise

    except firebase_auth.ExpiredIdTokenError:
        logger.warning("Token verification failed: expired")
        raise
    except firebase_auth.RevokedIdTokenError:
        logger.warning("Token verification failed: revoked")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        raise
