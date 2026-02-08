"""Tests for main application.

Note: The main application tests are now in test_app.py with more
comprehensive coverage. This file is kept for backward compatibility
and basic smoke tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src import __version__


class TestRootEndpoint:
    """Tests for the root endpoint."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_root_returns_message(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test that root endpoint returns expected message."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        with TestClient(app) as client:
            response = client.get("/")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Knowledge Store API"
            assert data["version"] == __version__

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_root_returns_json(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test that root endpoint returns JSON content type."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        with TestClient(app) as client:
            response = client.get("/")

            assert response.headers["content-type"] == "application/json"


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_health_returns_healthy(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test that health endpoint returns healthy status."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        with TestClient(app) as client:
            response = client.get("/health")

            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}


class TestAppConfiguration:
    """Tests for FastAPI application configuration."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_app_title(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test that app has correct title."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        assert app.title == "Knowledge Store API"

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_app_version(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test that app has correct version."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        assert app.version == __version__

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_docs_endpoint_available(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test that OpenAPI docs are available."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        with TestClient(app) as client:
            response = client.get("/api/docs")

            assert response.status_code == 200

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_openapi_schema_available(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test that OpenAPI schema is available."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        with TestClient(app) as client:
            response = client.get("/api/openapi.json")

            assert response.status_code == 200
            schema = response.json()
            assert schema["info"]["title"] == "Knowledge Store API"
