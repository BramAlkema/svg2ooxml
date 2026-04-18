"""Secure storage for OAuth refresh tokens used by the CLI and API."""

from __future__ import annotations

import getpass
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "cryptography is required for Google OAuth token storage."
    ) from exc


@dataclass
class TokenInfo:
    """Metadata describing a stored OAuth token."""

    user_id: str
    google_sub: str
    email: str
    scopes: str
    created_at: datetime
    last_used: datetime


class TokenStore:
    """Environment-backed token store that encrypts refresh tokens."""

    DEFAULT_SCOPES = (
        "openid email profile "
        "https://www.googleapis.com/auth/drive.file "
        "https://www.googleapis.com/auth/presentations"
    )

    def __init__(self, env_path: Path, encryption_key: str | None = None) -> None:
        self.env_path = env_path
        self.encryption_key = encryption_key or self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key.encode())

        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.touch(exist_ok=True)

        if os.name != "nt":
            os.chmod(self.env_path, 0o600)

    def _get_or_create_encryption_key(self) -> str:
        key_path = self.env_path.parent / "encryption.key"
        if key_path.exists():
            return key_path.read_text(encoding="utf-8").strip()

        key = Fernet.generate_key().decode()
        key_path.write_text(key, encoding="utf-8")
        if os.name != "nt":
            os.chmod(key_path, 0o600)
        return key

    def _read_env(self) -> dict[str, str]:
        env_vars: dict[str, str] = {}
        if self.env_path.exists():
            for line in self.env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
        return env_vars

    def _write_env(self, env_vars: dict[str, str]) -> None:
        with self.env_path.open("w", encoding="utf-8") as handle:
            for key, value in sorted(env_vars.items()):
                handle.write(f"{key}={value}\n")
        if os.name != "nt":
            os.chmod(self.env_path, 0o600)

    @staticmethod
    def _prefix_for_user(user_id: str) -> str:
        cleaned = user_id.upper().replace("-", "_")
        return f"SVG2OOXML_TOKEN_{cleaned}"

    def save_refresh_token(
        self,
        *,
        user_id: str,
        refresh_token: str,
        google_sub: str,
        email: str,
        scopes: str | None = None,
    ) -> None:
        if not user_id or not user_id.strip():
            raise ValueError("user_id cannot be empty")

        encrypted = self.cipher.encrypt(refresh_token.encode()).decode()
        env_vars = self._read_env()

        prefix = self._prefix_for_user(user_id)
        env_vars[f"{prefix}_REFRESH_TOKEN"] = encrypted
        env_vars[f"{prefix}_SUB"] = google_sub
        env_vars[f"{prefix}_EMAIL"] = email
        env_vars[f"{prefix}_SCOPES"] = scopes or self.DEFAULT_SCOPES

        now = datetime.now().isoformat()
        env_vars.setdefault(f"{prefix}_CREATED_AT", now)
        env_vars[f"{prefix}_LAST_USED"] = now

        self._write_env(env_vars)

    def get_refresh_token(self, user_id: str) -> str | None:
        env_vars = self._read_env()
        prefix = self._prefix_for_user(user_id)
        encrypted = env_vars.get(f"{prefix}_REFRESH_TOKEN")
        if not encrypted:
            return None

        env_vars[f"{prefix}_LAST_USED"] = datetime.now().isoformat()
        self._write_env(env_vars)

        return self.cipher.decrypt(encrypted.encode()).decode()

    def has_token(self, user_id: str) -> bool:
        env_vars = self._read_env()
        return f"{self._prefix_for_user(user_id)}_REFRESH_TOKEN" in env_vars

    def delete_token(self, user_id: str) -> None:
        env_vars = self._read_env()
        prefix = self._prefix_for_user(user_id)
        keys_to_remove = [key for key in env_vars if key.startswith(prefix)]
        for key in keys_to_remove:
            del env_vars[key]
        self._write_env(env_vars)

    def get_token_info(self, user_id: str) -> TokenInfo | None:
        env_vars = self._read_env()
        prefix = self._prefix_for_user(user_id)
        if f"{prefix}_REFRESH_TOKEN" not in env_vars:
            return None

        created_at_str = env_vars.get(f"{prefix}_CREATED_AT")
        last_used_str = env_vars.get(f"{prefix}_LAST_USED")

        return TokenInfo(
            user_id=user_id,
            google_sub=env_vars.get(f"{prefix}_SUB", ""),
            email=env_vars.get(f"{prefix}_EMAIL", ""),
            scopes=env_vars.get(f"{prefix}_SCOPES", self.DEFAULT_SCOPES),
            created_at=datetime.fromisoformat(created_at_str) if created_at_str else None,
            last_used=datetime.fromisoformat(last_used_str) if last_used_str else None,
        )


def get_cli_token_store() -> TokenStore:
    """Return the token store used by CLI interactions."""

    env_path = Path.home() / ".svg2ooxml" / ".env"
    return TokenStore(env_path)


def get_api_token_store() -> TokenStore:
    """Return the token store for API deployments (project-local .env)."""

    env_path = Path.cwd() / ".env"
    return TokenStore(env_path)


def get_system_username() -> str:
    """Return the current login name for CLI identity separation."""

    return getpass.getuser()
