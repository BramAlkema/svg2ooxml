"""Local API server management for testing and development."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LocalAPIConfig:
    """Configuration for local API server."""

    project_id: str = "powerful-layout-467812-p1"
    secret_dir: Path = Path("secrets/local")
    port: int = 8080
    rate_limit: int = 200
    rate_window: int = 60
    disable_quota: bool = True

    @property
    def service_account_path(self) -> Path:
        """Path to Firebase service account JSON."""
        return self.secret_dir / "firebase-service-account.json"

    @property
    def token_key_path(self) -> Path:
        """Path to token encryption key."""
        return self.secret_dir / "token-encryption-key.txt"

    @property
    def web_client_id_path(self) -> Path:
        """Path to Firebase web client ID."""
        return self.secret_dir / "firebase-web-client-id.txt"

    @property
    def web_client_secret_path(self) -> Path:
        """Path to Firebase web client secret."""
        return self.secret_dir / "firebase-web-client-secret.txt"


def fetch_secret_from_gcp(secret_name: str, project_id: str) -> str:
    """
    Fetch a secret from GCP Secret Manager.

    Args:
        secret_name: Name of the secret to fetch
        project_id: GCP project ID

    Returns:
        The secret value as a string

    Raises:
        subprocess.CalledProcessError: If gcloud command fails
    """
    logger.info(f"Fetching secret {secret_name} from project {project_id}")
    result = subprocess.run(
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            "--secret",
            secret_name,
            "--project",
            project_id,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def setup_local_environment(config: LocalAPIConfig | None = None) -> dict[str, str]:
    """
    Set up local environment by fetching secrets and creating environment variables.

    Args:
        config: Configuration for local API server (uses defaults if None)

    Returns:
        Dictionary of environment variables to set

    Raises:
        FileNotFoundError: If required files don't exist after fetching secrets
        subprocess.CalledProcessError: If gcloud command fails
    """
    if config is None:
        config = LocalAPIConfig()

    # Create secret directory
    config.secret_dir.mkdir(parents=True, exist_ok=True)

    # Fetch secrets from GCP
    secrets_to_fetch = {
        "firebase-service-account": config.service_account_path,
        "token-encryption-key": config.token_key_path,
        "firebase-web-client-id": config.web_client_id_path,
        "firebase-web-client-secret": config.web_client_secret_path,
    }

    for secret_name, output_path in secrets_to_fetch.items():
        if not output_path.exists():
            logger.info(f"Fetching {secret_name}")
            secret_value = fetch_secret_from_gcp(secret_name, config.project_id)
            output_path.write_text(secret_value)
            logger.info(f"Saved {secret_name} to {output_path}")
        else:
            logger.info(f"Secret {secret_name} already exists at {output_path}")

    # Read secret values
    token_key = config.token_key_path.read_text().strip()
    web_client_id = config.web_client_id_path.read_text().strip()
    web_client_secret = config.web_client_secret_path.read_text().strip()

    # Build environment variables
    env_vars = {
        "ENVIRONMENT": "development",
        "GCP_PROJECT": config.project_id,
        "GOOGLE_CLOUD_PROJECT": config.project_id,
        "FIREBASE_PROJECT_ID": config.project_id,
        "FIREBASE_SERVICE_ACCOUNT_PATH": str(config.service_account_path.absolute()),
        "GOOGLE_APPLICATION_CREDENTIALS": str(config.service_account_path.absolute()),
        "TOKEN_ENCRYPTION_KEY": token_key,
        "FIREBASE_WEB_CLIENT_ID": web_client_id,
        "FIREBASE_WEB_CLIENT_SECRET": web_client_secret,
        "SVG2OOXML_RATE_LIMIT": str(config.rate_limit),
        "SVG2OOXML_RATE_WINDOW": str(config.rate_window),
        "DISABLE_EXPORT_QUOTA": str(config.disable_quota).lower(),
    }

    logger.info("Local environment setup complete")
    return env_vars


class LocalAPIServer:
    """Manages a local API server instance for testing."""

    def __init__(self, config: LocalAPIConfig | None = None) -> None:
        """
        Initialize local API server manager.

        Args:
            config: Configuration for local API server (uses defaults if None)
        """
        self.config = config or LocalAPIConfig()
        self.process: subprocess.Popen[bytes] | None = None
        self._env_vars: dict[str, str] | None = None

    def setup(self) -> None:
        """Fetch secrets and prepare environment variables."""
        self._env_vars = setup_local_environment(self.config)
        logger.info(f"Environment prepared with {len(self._env_vars)} variables")

    def start(self) -> None:
        """
        Start the local API server.

        Raises:
            RuntimeError: If setup() hasn't been called or server is already running
            FileNotFoundError: If uvicorn is not found
        """
        if self._env_vars is None:
            raise RuntimeError("Must call setup() before start()")

        if self.process is not None and self.process.poll() is None:
            raise RuntimeError("Server is already running")

        # Prepare environment
        env = os.environ.copy()
        env.update(self._env_vars)
        env.pop("SERVICE_URL", None)  # Unset SERVICE_URL if it exists

        # Find uvicorn
        uvicorn_path = self._find_uvicorn()

        logger.info(f"Starting uvicorn on http://127.0.0.1:{self.config.port}")

        # Start server
        self.process = subprocess.Popen(
            [
                uvicorn_path,
                "figma2gslides.app:app",
                "--reload",
                "--host",
                "0.0.0.0",
                "--port",
                str(self.config.port),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        logger.info(f"Server started with PID {self.process.pid}")

    def stop(self) -> None:
        """Stop the local API server if it's running."""
        if self.process is not None and self.process.poll() is None:
            logger.info(f"Stopping server (PID {self.process.pid})")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Server did not stop gracefully, killing")
                self.process.kill()
                self.process.wait()
            self.process = None
            logger.info("Server stopped")

    def _find_uvicorn(self) -> str:
        """
        Find uvicorn executable.

        Returns:
            Path to uvicorn executable

        Raises:
            FileNotFoundError: If uvicorn is not found
        """
        # Try to find uvicorn in virtualenv
        if hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        ):
            # We're in a virtualenv
            venv_bin = Path(sys.prefix) / "bin" / "uvicorn"
            if venv_bin.exists():
                return str(venv_bin)

        # Try system uvicorn
        try:
            result = subprocess.run(
                ["which", "uvicorn"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            raise FileNotFoundError(
                "uvicorn not found. Install it with: pip install uvicorn[standard]"
            ) from None

    def __enter__(self) -> LocalAPIServer:
        """Context manager entry."""
        if self._env_vars is None:
            self.setup()
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.stop()


__all__ = ["LocalAPIConfig", "LocalAPIServer", "setup_local_environment"]
