"""Firebase Admin SDK initialization and token verification."""
import logging
import os
from typing import Dict

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

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


def verify_id_token(id_token: str) -> Dict[str, any]:
    """Verify Firebase ID token and return decoded claims.

    Args:
        id_token: Firebase ID token from client

    Returns:
        Dictionary with user claims:
        - uid: User ID
        - email: User email (if available)
        - email_verified: Whether email is verified
        - auth_time: Authentication timestamp
        - exp: Expiration timestamp

    Raises:
        firebase_admin.auth.InvalidIdTokenError: If token is invalid
        firebase_admin.auth.ExpiredIdTokenError: If token is expired
        firebase_admin.auth.RevokedIdTokenError: If token is revoked
    """
    try:
        # Verify the token (includes signature, expiration, etc.)
        decoded_token = firebase_auth.verify_id_token(id_token)

        logger.info(
            "Token verified successfully",
            extra={
                "user_id": decoded_token["uid"],
                "email": decoded_token.get("email", "unknown")
            }
        )

        return decoded_token

    except firebase_auth.ExpiredIdTokenError:
        logger.warning("Token verification failed: expired")
        raise
    except firebase_auth.InvalidIdTokenError as e:
        logger.warning(f"Token verification failed: invalid - {e}")
        raise
    except firebase_auth.RevokedIdTokenError:
        logger.warning("Token verification failed: revoked")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        raise
