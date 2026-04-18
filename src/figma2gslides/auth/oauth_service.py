"""Google OAuth helpers shared by the CLI and API surface."""

from __future__ import annotations

import json
import logging
import secrets
from base64 import urlsafe_b64decode

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "Google authentication libraries are required for OAuth support."
    ) from exc

from .token_store import TokenStore

logger = logging.getLogger(__name__)


class OAuthError(RuntimeError):
    """Raised when the OAuth handshake fails."""


class GoogleOAuthService:
    """Multi-user OAuth service for Google Drive and Slides APIs."""

    SCOPES = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/presentations",
    ]

    def __init__(
        self,
        *,
        token_store: TokenStore,
        client_id: str,
        client_secret: str,
        redirect_uri: str | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("client_id and client_secret are required")

        self.token_store = token_store
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri or "http://localhost:8080/oauth2/callback"
        self._state_store: dict[str, str] = {}

    def _create_flow(self) -> Flow:
        client_config = {
            "web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.redirect_uri],
            }
        }
        flow = Flow.from_client_config(client_config, scopes=self.SCOPES)
        flow.redirect_uri = self.redirect_uri
        return flow

    def start_auth_flow(self, user_id: str, *, is_cli: bool = False) -> str:
        if not user_id or not user_id.strip():
            raise ValueError("user_id cannot be empty")

        flow = self._create_flow()
        state = secrets.token_urlsafe(32)
        self._state_store[state] = user_id

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )

        logger.info("OAuth flow started for user: %s (cli=%s)", user_id, is_cli)
        return auth_url

    def handle_callback(self, *, user_id: str, authorization_response: str) -> Credentials:
        flow = self._create_flow()

        try:
            flow.fetch_token(authorization_response=authorization_response)
            creds = flow.credentials

            state = self._extract_state(authorization_response)
            if state not in self._state_store:
                raise OAuthError("Invalid OAuth state (possible CSRF attempt).")

            stored_user_id = self._state_store.pop(state)
            if stored_user_id != user_id:
                raise OAuthError("OAuth callback user mismatch.")

            id_data = self._parse_id_token(creds.id_token)
            google_sub = id_data.get("sub", "")
            email = id_data.get("email", "")

            if creds.refresh_token:
                self.token_store.save_refresh_token(
                    user_id=user_id,
                    refresh_token=creds.refresh_token,
                    google_sub=google_sub,
                    email=email,
                    scopes=" ".join(self.SCOPES),
                )
                logger.info("Refresh token stored for user %s (%s)", user_id, email)
            else:
                logger.warning("No refresh token returned for user %s", user_id)

            return creds
        except Exception as exc:  # pragma: no cover - defensive path
            logger.error("OAuth callback failed: %s", exc)
            raise OAuthError(f"OAuth callback failed: {exc}") from exc

    def get_credentials(self, user_id: str) -> Credentials:
        refresh_token = self.token_store.get_refresh_token(user_id)
        if not refresh_token:
            raise OAuthError(f"User {user_id} is not authenticated.")

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.SCOPES,
        )

        if not creds.valid:
            try:
                creds.refresh(Request())
                logger.debug("Access token refreshed for user %s", user_id)
            except Exception as exc:  # pragma: no cover - network failure
                if "invalid_grant" in str(exc):
                    logger.error("Refresh token revoked for user %s", user_id)
                    self.token_store.delete_token(user_id)
                    raise OAuthError("Refresh token revoked. Re-authenticate.") from exc
                raise OAuthError(f"Failed to refresh token: {exc}") from exc

        return creds

    def revoke_access(self, user_id: str) -> None:
        self.token_store.delete_token(user_id)
        logger.info("OAuth access revoked for user %s", user_id)

    @staticmethod
    def _extract_state(authorization_response: str) -> str:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(authorization_response)
        params = parse_qs(parsed.query)
        return params.get("state", [None])[0] or ""

    @staticmethod
    def _parse_id_token(id_token: str) -> dict[str, object]:
        parts = id_token.split(".")
        if len(parts) != 3:
            return {}

        payload = parts[1]
        padding = 4 - (len(payload) % 4)
        if padding and padding != 4:
            payload += "=" * padding

        try:
            decoded = urlsafe_b64decode(payload.encode("utf-8"))
            return json.loads(decoded)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to parse ID token: %s", exc)
            return {}
