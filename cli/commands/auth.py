"""Google authentication commands used by the CLI."""

from __future__ import annotations

import logging
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import click

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from svg2ooxml.core.auth import GoogleOAuthService

logger = logging.getLogger(__name__)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler used for the OAuth redirect."""

    oauth_service: "GoogleOAuthService | None" = None
    user_id: str | None = None
    success = False
    _lock = threading.Lock()

    def do_GET(self) -> None:  # noqa: N802 - HTTPServer interface
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            if "error" in params:
                self._send_error_response(f"OAuth error: {params['error'][0]}")
                return
            if "code" not in params or "state" not in params:
                self._send_error_response("Missing code or state parameter.")
                return

            service = self.oauth_service
            user_id = self.user_id
            if service is None or user_id is None:
                self._send_error_response("OAuth service not initialised.")
                return

            callback_url = f"http://localhost:8080{self.path}"
            service.handle_callback(user_id=user_id, authorization_response=callback_url)

            with self._lock:
                OAuthCallbackHandler.success = True

            self._send_html_response(
                status=200,
                body=(
                    "<html><body style='text-align:center;padding:48px;font-family:Arial;'>"
                    "<h1 style='color:green;'>✅ Authentication Successful</h1>"
                    "<p>You can close this window and return to the terminal.</p>"
                    "</body></html>"
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("OAuth callback error: %s", exc)
            self._send_error_response(str(exc))

    def log_message(self, *_args, **_kwargs) -> None:  # noqa: D401 - silence default logging
        """Suppress default HTTP server logging."""

    def _send_html_response(self, *, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_error_response(self, message: str) -> None:
        self._send_html_response(
            status=400,
            body=(
                "<html><body style='text-align:center;padding:48px;font-family:Arial;'>"
                "<h1 style='color:red;'>❌ Authentication Failed</h1>"
                f"<p>{message}</p>"
                "<p>Please return to the terminal and try again.</p>"
                "</body></html>"
            ),
        )


@click.group()
def auth() -> None:
    """Manage Google OAuth credentials."""


@auth.command()
@click.option("--status", is_flag=True, help="Display authentication status.")
@click.option("--revoke", is_flag=True, help="Revoke stored credentials.")
def google(status: bool, revoke: bool) -> None:
    """Authenticate with Google Drive/Slides for PPTX export."""

    try:
        from svg2ooxml.core.auth import (  # noqa: WPS433 - optional dependency import
            GoogleOAuthService,
            OAuthError,
            get_cli_token_store,
            get_system_username,
        )
    except ImportError as exc:
        click.echo(
            "❌ Google integrations require optional dependencies. "
            "Install with: pip install 'svg2ooxml[slides]'",
            err=True,
        )
        logger.debug("Missing Google dependencies: %s", exc)
        return

    user_id = get_system_username()
    token_store = get_cli_token_store()

    if status:
        info = token_store.get_token_info(user_id)
        if info is None:
            click.echo("❌ Not authenticated. Run `svg2ooxml auth google` to connect.")
        else:
            click.echo(f"✅ Authenticated as: {info.email}")
            click.echo(f"   Google Sub: {info.google_sub}")
            click.echo(f"   Created: {info.created_at}")
            click.echo(f"   Last used: {info.last_used}")
        return

    if revoke:
        if not token_store.has_token(user_id):
            click.echo("❌ No stored credentials found.")
            return
        if click.confirm("Revoke Google access for this user?"):
            token_store.delete_token(user_id)
            click.echo("✅ Google access revoked.")
        return

    if token_store.has_token(user_id):
        info = token_store.get_token_info(user_id)
        if info and not click.confirm(f"Already authenticated as {info.email}. Re-authenticate?"):
            return

    client_id, client_secret = _fetch_oauth_credentials()
    if not client_id or not client_secret:
        return

    oauth_service = GoogleOAuthService(
        token_store=token_store,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost:8080/oauth2/callback",
    )

    auth_url = oauth_service.start_auth_flow(user_id, is_cli=True)

    OAuthCallbackHandler.oauth_service = oauth_service
    OAuthCallbackHandler.user_id = user_id
    OAuthCallbackHandler.success = False

    click.echo("🌐 Opening browser for authentication...")
    click.echo(f"   If the browser does not open, visit: {auth_url}")
    webbrowser.open(auth_url, new=1, autoraise=True)

    click.echo("⏳ Waiting for authentication on http://localhost:8080 ...")
    server = HTTPServer(("localhost", 8080), OAuthCallbackHandler)
    server.timeout = 300  # five minutes
    server.handle_request()

    if OAuthCallbackHandler.success:
        click.echo("✅ Google authentication completed successfully.")
    else:
        click.echo("❌ Authentication failed. Check the browser for details.")


def _fetch_oauth_credentials() -> tuple[str | None, str | None]:
    import os

    client_id = os.getenv("GOOGLE_DRIVE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET")
    if not client_id or not client_secret:
        click.echo("❌ OAuth client configuration missing.")
        click.echo("   Please set GOOGLE_DRIVE_CLIENT_ID and GOOGLE_DRIVE_CLIENT_SECRET.")
        return None, None
    return client_id, client_secret


__all__ = ["auth"]
