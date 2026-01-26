"""Tests for main application."""

from fastapi.testclient import TestClient

from src import __version__
from src.main import app


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_returns_message(self, client: TestClient) -> None:
        """Test that root endpoint returns expected message."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Knowledge Store API"
        assert data["version"] == __version__

    def test_root_returns_json(self, client: TestClient) -> None:
        """Test that root endpoint returns JSON content type."""
        response = client.get("/")
        assert response.headers["content-type"] == "application/json"


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_healthy(self, client: TestClient) -> None:
        """Test that health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestAppConfiguration:
    """Tests for FastAPI application configuration."""

    def test_app_title(self) -> None:
        """Test that app has correct title."""
        assert app.title == "Knowledge Store"

    def test_app_version(self) -> None:
        """Test that app has correct version."""
        assert app.version == __version__

    def test_docs_endpoint_available(self, client: TestClient) -> None:
        """Test that OpenAPI docs are available."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema_available(self, client: TestClient) -> None:
        """Test that OpenAPI schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "Knowledge Store"
