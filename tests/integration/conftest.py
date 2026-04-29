from __future__ import annotations

import os
from collections.abc import Generator

import pytest

from figma2gslides.api.testing import LocalAPIConfig, LocalAPIServer

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def local_api_config() -> LocalAPIConfig:
    """
    Provide configuration for local API server.

    Override port from environment if SVG2OOXML_TEST_PORT is set.
    """
    port = int(os.environ.get("SVG2OOXML_TEST_PORT", "8081"))
    return LocalAPIConfig(port=port)


@pytest.fixture(scope="session")
def local_api_server(local_api_config: LocalAPIConfig) -> Generator[LocalAPIServer]:
    """
    Start a local API server for integration tests.

    This fixture:
    - Sets up environment with secrets from GCP
    - Starts uvicorn server
    - Yields the server instance
    - Stops the server on teardown

    Example:
        def test_export_endpoint(local_api_server):
            import requests
            response = requests.get(f"http://127.0.0.1:{local_api_server.config.port}/")
            assert response.status_code == 200
    """
    server = LocalAPIServer(local_api_config)

    # Setup and start
    server.setup()
    server.start()

    yield server

    # Teardown
    server.stop()


@pytest.fixture
def api_base_url(local_api_server: LocalAPIServer) -> str:
    """Provide base URL for the local API server."""
    return f"http://127.0.0.1:{local_api_server.config.port}"

