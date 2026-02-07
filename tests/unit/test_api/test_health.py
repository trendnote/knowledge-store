"""Tests for health check router."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.health import (
    CheckResult,
    HealthResponse,
    get_clients,
    reset_clients,
    router,
    set_clients,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def healthy_clients() -> dict[str, Any]:
    """Create healthy mock clients."""
    return {
        "postgres": MagicMock(ping=AsyncMock(return_value=True)),
        "milvus": MagicMock(ping=AsyncMock(return_value=True)),
        "neo4j": MagicMock(ping=AsyncMock(return_value=True)),
        "kafka": MagicMock(ping=AsyncMock(return_value=True)),
    }


@pytest.fixture
def unhealthy_milvus_clients() -> dict[str, Any]:
    """Create clients with Milvus down."""
    return {
        "postgres": MagicMock(ping=AsyncMock(return_value=True)),
        "milvus": MagicMock(ping=AsyncMock(return_value=False)),
        "neo4j": MagicMock(ping=AsyncMock(return_value=True)),
        "kafka": MagicMock(ping=AsyncMock(return_value=True)),
    }


@pytest.fixture
def error_clients() -> dict[str, Any]:
    """Create clients that raise errors."""
    return {
        "postgres": MagicMock(ping=AsyncMock(return_value=True)),
        "milvus": MagicMock(ping=AsyncMock(side_effect=Exception("Connection refused"))),
        "neo4j": MagicMock(ping=AsyncMock(return_value=True)),
        "kafka": MagicMock(ping=AsyncMock(return_value=True)),
    }


@pytest.fixture(autouse=True)
def cleanup_clients():
    """Reset clients after each test."""
    yield
    reset_clients()


# =============================================================================
# Test Models
# =============================================================================


class TestCheckResult:
    """Tests for CheckResult model."""

    def test_create_up_result(self) -> None:
        """Test creating an up result."""
        result = CheckResult(status="up", latency_ms=5.5)
        assert result.status == "up"
        assert result.latency_ms == 5.5
        assert result.error is None

    def test_create_down_result(self) -> None:
        """Test creating a down result with error."""
        result = CheckResult(status="down", error="Connection refused")
        assert result.status == "down"
        assert result.error == "Connection refused"
        assert result.latency_ms is None

    def test_default_values(self) -> None:
        """Test default values."""
        result = CheckResult(status="up")
        assert result.latency_ms is None
        assert result.error is None


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_create_healthy_response(self) -> None:
        """Test creating a healthy response."""
        from datetime import datetime

        response = HealthResponse(
            status="healthy",
            timestamp=datetime.utcnow(),
            checks={
                "postgres": CheckResult(status="up", latency_ms=5.0),
            },
        )
        assert response.status == "healthy"
        assert "postgres" in response.checks

    def test_create_unhealthy_response(self) -> None:
        """Test creating an unhealthy response."""
        from datetime import datetime

        response = HealthResponse(
            status="unhealthy",
            timestamp=datetime.utcnow(),
            checks={
                "postgres": CheckResult(status="down", error="Timeout"),
            },
        )
        assert response.status == "unhealthy"


# =============================================================================
# Test Client Management
# =============================================================================


class TestClientManagement:
    """Tests for client management functions."""

    def test_set_clients(self) -> None:
        """Test setting clients."""
        mock_postgres = MagicMock()
        mock_milvus = MagicMock()

        set_clients(postgres=mock_postgres, milvus=mock_milvus)

        clients = get_clients()
        assert clients["postgres"] is mock_postgres
        assert clients["milvus"] is mock_milvus
        assert clients["neo4j"] is None
        assert clients["kafka"] is None

    def test_reset_clients(self) -> None:
        """Test resetting clients."""
        set_clients(postgres=MagicMock())
        reset_clients()

        clients = get_clients()
        assert all(v is None for v in clients.values())

    def test_set_all_clients(self) -> None:
        """Test setting all clients."""
        mocks = {
            "postgres": MagicMock(),
            "milvus": MagicMock(),
            "neo4j": MagicMock(),
            "kafka": MagicMock(),
        }
        set_clients(**mocks)

        clients = get_clients()
        assert clients["postgres"] is mocks["postgres"]
        assert clients["milvus"] is mocks["milvus"]
        assert clients["neo4j"] is mocks["neo4j"]
        assert clients["kafka"] is mocks["kafka"]


# =============================================================================
# Test Health Check Endpoint
# =============================================================================


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_all_up(
        self,
        client: TestClient,
        healthy_clients: dict[str, Any],
    ) -> None:
        """Test health when all services are up."""
        set_clients(**healthy_clients)

        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert all(c["status"] == "up" for c in data["checks"].values())
        assert "timestamp" in data

    def test_health_one_down(
        self,
        client: TestClient,
        unhealthy_milvus_clients: dict[str, Any],
    ) -> None:
        """Test health when one service is down."""
        set_clients(**unhealthy_milvus_clients)

        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["milvus"]["status"] == "down"
        assert data["checks"]["postgres"]["status"] == "up"

    def test_health_with_error(
        self,
        client: TestClient,
        error_clients: dict[str, Any],
    ) -> None:
        """Test health when a service throws error."""
        set_clients(**error_clients)

        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["milvus"]["status"] == "down"
        assert "Connection refused" in data["checks"]["milvus"]["error"]

    def test_health_no_clients(
        self,
        client: TestClient,
    ) -> None:
        """Test health when no clients configured."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        for check in data["checks"].values():
            assert check["status"] == "down"
            assert check["error"] == "Client not configured"

    def test_health_includes_latency(
        self,
        client: TestClient,
        healthy_clients: dict[str, Any],
    ) -> None:
        """Test health check includes latency."""
        set_clients(**healthy_clients)

        response = client.get("/api/v1/health")

        data = response.json()
        for check in data["checks"].values():
            if check["status"] == "up":
                assert "latency_ms" in check
                assert check["latency_ms"] is not None


# =============================================================================
# Test Liveness Endpoint
# =============================================================================


class TestLivenessEndpoint:
    """Tests for /health/live endpoint."""

    def test_liveness(self, client: TestClient) -> None:
        """Test liveness probe returns alive."""
        response = client.get("/api/v1/health/live")

        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_liveness_no_clients_needed(self, client: TestClient) -> None:
        """Test liveness doesn't need clients."""
        # No clients configured
        response = client.get("/api/v1/health/live")

        assert response.status_code == 200
        assert response.json()["status"] == "alive"


# =============================================================================
# Test Readiness Endpoint
# =============================================================================


class TestReadinessEndpoint:
    """Tests for /health/ready endpoint."""

    def test_readiness_healthy(
        self,
        client: TestClient,
        healthy_clients: dict[str, Any],
    ) -> None:
        """Test readiness when healthy."""
        set_clients(**healthy_clients)

        response = client.get("/api/v1/health/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_readiness_unhealthy(
        self,
        client: TestClient,
        unhealthy_milvus_clients: dict[str, Any],
    ) -> None:
        """Test readiness when unhealthy returns 503."""
        set_clients(**unhealthy_milvus_clients)

        response = client.get("/api/v1/health/ready")

        assert response.status_code == 503
        assert "not ready" in response.json()["detail"].lower()

    def test_readiness_no_clients(
        self,
        client: TestClient,
    ) -> None:
        """Test readiness when no clients configured."""
        response = client.get("/api/v1/health/ready")

        assert response.status_code == 503

    def test_readiness_with_error(
        self,
        client: TestClient,
        error_clients: dict[str, Any],
    ) -> None:
        """Test readiness when a service errors."""
        set_clients(**error_clients)

        response = client.get("/api/v1/health/ready")

        assert response.status_code == 503


# =============================================================================
# Test Parallel Execution
# =============================================================================


class TestParallelExecution:
    """Tests for parallel health check execution."""

    def test_checks_run_in_parallel(
        self,
        client: TestClient,
    ) -> None:
        """Test that health checks run in parallel."""
        import asyncio

        call_times: list[float] = []

        async def slow_ping() -> bool:
            import time
            call_times.append(time.time())
            await asyncio.sleep(0.1)
            return True

        slow_clients = {
            "postgres": MagicMock(ping=slow_ping),
            "milvus": MagicMock(ping=slow_ping),
            "neo4j": MagicMock(ping=slow_ping),
            "kafka": MagicMock(ping=slow_ping),
        }
        set_clients(**slow_clients)

        response = client.get("/api/v1/health")

        assert response.status_code == 200
        # If running in parallel, all calls should start around the same time
        # (within 0.05 seconds of each other)
        if len(call_times) >= 2:
            time_spread = max(call_times) - min(call_times)
            assert time_spread < 0.05, "Health checks should run in parallel"
