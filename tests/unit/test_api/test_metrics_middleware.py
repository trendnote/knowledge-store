"""Tests for metrics middleware."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.middleware.metrics import MetricsMiddleware


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app with middleware."""
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)

    @app.get("/api/v1/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/api/v1/health")
    async def health_endpoint():
        return {"status": "healthy"}

    @app.get("/api/v1/health/live")
    async def liveness_endpoint():
        return {"status": "alive"}

    @app.get("/api/v1/metrics")
    async def metrics_endpoint():
        return {"metrics": "data"}

    @app.post("/api/v1/documents")
    async def create_document():
        return {"id": "doc-123"}

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


# =============================================================================
# Test Middleware Recording
# =============================================================================


class TestMiddlewareRecording:
    """Tests for metrics middleware recording."""

    def test_records_get_request(
        self,
        client: TestClient,
    ) -> None:
        """Test middleware records GET request."""
        with patch("src.api.middleware.metrics.record_request") as mock_record:
            client.get("/api/v1/test")

            mock_record.assert_called_once()
            call_args = mock_record.call_args
            assert call_args.kwargs["method"] == "GET"
            assert call_args.kwargs["endpoint"] == "/api/v1/test"
            assert call_args.kwargs["status"] == 200
            assert "duration" in call_args.kwargs

    def test_records_post_request(
        self,
        client: TestClient,
    ) -> None:
        """Test middleware records POST request."""
        with patch("src.api.middleware.metrics.record_request") as mock_record:
            client.post("/api/v1/documents")

            mock_record.assert_called_once()
            call_args = mock_record.call_args
            assert call_args.kwargs["method"] == "POST"
            assert call_args.kwargs["endpoint"] == "/api/v1/documents"
            assert call_args.kwargs["status"] == 200

    def test_records_duration(
        self,
        client: TestClient,
    ) -> None:
        """Test middleware records duration."""
        with patch("src.api.middleware.metrics.record_request") as mock_record:
            client.get("/api/v1/test")

            call_args = mock_record.call_args
            duration = call_args.kwargs["duration"]
            assert isinstance(duration, float)
            assert duration >= 0


# =============================================================================
# Test Excluded Paths
# =============================================================================


class TestExcludedPaths:
    """Tests for excluded paths."""

    def test_excludes_health_endpoint(
        self,
        client: TestClient,
    ) -> None:
        """Test health endpoint is excluded."""
        with patch("src.api.middleware.metrics.record_request") as mock_record:
            client.get("/api/v1/health")

            mock_record.assert_not_called()

    def test_excludes_health_live_endpoint(
        self,
        client: TestClient,
    ) -> None:
        """Test health/live endpoint is excluded."""
        with patch("src.api.middleware.metrics.record_request") as mock_record:
            client.get("/api/v1/health/live")

            mock_record.assert_not_called()

    def test_excludes_metrics_endpoint(
        self,
        client: TestClient,
    ) -> None:
        """Test metrics endpoint is excluded."""
        with patch("src.api.middleware.metrics.record_request") as mock_record:
            client.get("/api/v1/metrics")

            mock_record.assert_not_called()

    def test_does_not_exclude_regular_endpoints(
        self,
        client: TestClient,
    ) -> None:
        """Test regular endpoints are not excluded."""
        with patch("src.api.middleware.metrics.record_request") as mock_record:
            client.get("/api/v1/test")

            mock_record.assert_called_once()


# =============================================================================
# Test Should Exclude Method
# =============================================================================


class TestShouldExclude:
    """Tests for _should_exclude method."""

    def test_should_exclude_health(self) -> None:
        """Test health path is excluded."""
        middleware = MetricsMiddleware(app=FastAPI())
        assert middleware._should_exclude("/api/v1/health") is True

    def test_should_exclude_health_live(self) -> None:
        """Test health/live path is excluded."""
        middleware = MetricsMiddleware(app=FastAPI())
        assert middleware._should_exclude("/api/v1/health/live") is True

    def test_should_exclude_health_ready(self) -> None:
        """Test health/ready path is excluded."""
        middleware = MetricsMiddleware(app=FastAPI())
        assert middleware._should_exclude("/api/v1/health/ready") is True

    def test_should_exclude_metrics(self) -> None:
        """Test metrics path is excluded."""
        middleware = MetricsMiddleware(app=FastAPI())
        assert middleware._should_exclude("/api/v1/metrics") is True

    def test_should_not_exclude_documents(self) -> None:
        """Test documents path is not excluded."""
        middleware = MetricsMiddleware(app=FastAPI())
        assert middleware._should_exclude("/api/v1/documents") is False

    def test_should_not_exclude_search(self) -> None:
        """Test search path is not excluded."""
        middleware = MetricsMiddleware(app=FastAPI())
        assert middleware._should_exclude("/api/v1/search") is False

    def test_should_exclude_health_subpaths(self) -> None:
        """Test health subpaths are excluded."""
        middleware = MetricsMiddleware(app=FastAPI())
        assert middleware._should_exclude("/api/v1/health/any/path") is True

    def test_should_exclude_metrics_subpaths(self) -> None:
        """Test metrics subpaths are excluded."""
        middleware = MetricsMiddleware(app=FastAPI())
        assert middleware._should_exclude("/api/v1/metrics/any/path") is True


# =============================================================================
# Test Response Passthrough
# =============================================================================


class TestResponsePassthrough:
    """Tests for response passthrough."""

    def test_passes_through_response(
        self,
        client: TestClient,
    ) -> None:
        """Test middleware passes through response correctly."""
        response = client.get("/api/v1/test")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_passes_through_post_response(
        self,
        client: TestClient,
    ) -> None:
        """Test middleware passes through POST response."""
        response = client.post("/api/v1/documents")

        assert response.status_code == 200
        assert response.json() == {"id": "doc-123"}

    def test_passes_through_excluded_response(
        self,
        client: TestClient,
    ) -> None:
        """Test middleware passes through excluded endpoint response."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
