"""FastAPI authentication middleware using Firebase tokens."""
import hashlib
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .firebase import get_firestore_client, verify_id_token

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer()


async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict[str, any]:
    """FastAPI dependency to verify Firebase ID token.

    Extracts token from Authorization header, verifies it,
    and returns user information.

    Args:
        credentials: HTTP Bearer credentials from request header

    Returns:
        Dictionary with user info:
        - uid: Firebase user ID
        - email: User email (optional)
        - token: Original ID token (for Drive API calls)
        - token_hash: SHA256 hash of token (for logging)

    Raises:
        HTTPException(401): If token is missing, invalid, or expired

    Usage in endpoint:
        @router.post("/export")
        async def create_export(
            request: ExportRequest,
            user: dict = Depends(verify_firebase_token)
        ):
            # user["token"] contains verified Firebase ID token
            # user["uid"] contains user ID
            pass
    """
    token = credentials.credentials

    try:
        # Verify token with Firebase
        decoded_token = verify_id_token(token)

        # Extract user info
        user_info = {
            "uid": decoded_token["uid"],
            "email": decoded_token.get("email"),
            "token": token,  # Original token for Drive API
            "token_hash": hashlib.sha256(token.encode()).hexdigest()[:16]
        }

        logger.info(
            "User authenticated",
            extra={
                "user_id": user_info["uid"],
                "email": user_info.get("email", "unknown"),
                "token_hash": user_info["token_hash"]
            }
        )

        return user_info

    except Exception as e:
        # Log failure (without full token)
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        logger.warning(
            f"Authentication failed: {type(e).__name__}",
            extra={"token_hash": token_hash, "error": str(e)}
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired authentication token: {type(e).__name__}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# Optional: Require specific scopes
async def verify_firebase_token_with_scopes(
    required_scopes: list[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict[str, any]:
    """Verify token and check for required OAuth scopes.

    Note: Firebase ID tokens don't include OAuth scopes.
    This would require storing scope info separately or
    using Google OAuth tokens directly.

    For now, we assume all authenticated users have the
    required scopes (they granted them during sign-in).
    """
    user_info = await verify_firebase_token(credentials)

    if not required_scopes:
        return user_info

    try:
        db = get_firestore_client()
        doc = db.collection("users").document(user_info["uid"]).get()
    except Exception as e:
        logger.warning("Failed to fetch user scopes: %s", e)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OAuth scopes unavailable for this user",
        ) from e

    if not getattr(doc, "exists", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OAuth scopes not found for this user",
        )

    data = doc.to_dict() or {}
    oauth = data.get("google_oauth") if isinstance(data, dict) else {}
    scopes_raw = oauth.get("scopes") if isinstance(oauth, dict) else None
    if isinstance(scopes_raw, str):
        granted = {scope for scope in scopes_raw.split() if scope}
    elif isinstance(scopes_raw, (list, tuple, set)):
        granted = {str(scope) for scope in scopes_raw if scope}
    else:
        granted = set()

    missing = [scope for scope in (required_scopes or []) if scope not in granted]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing OAuth scopes: {', '.join(missing)}",
        )

    user_info["oauth_scopes"] = sorted(granted)
    return user_info
