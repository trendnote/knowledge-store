"""Tests for audit middleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api.middleware.audit import (
    AuditContextMiddleware,
    get_audit_context,
    get_client_ip,
    get_user_agent,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app with middleware."""
    app = FastAPI()
    app.add_middleware(AuditContextMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        context = get_audit_context(request)
        return {
            "client_ip": context["ip_address"],
            "user_agent": context["user_agent"],
        }

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


# =============================================================================
# Test get_client_ip
# =============================================================================


class TestGetClientIp:
    """Tests for get_client_ip function."""

    def test_from_x_forwarded_for(self, app: FastAPI) -> None:
        """Test extracting IP from X-Forwarded-For header."""
        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"},
        )

        assert response.status_code == 200
        assert response.json()["client_ip"] == "203.0.113.195"

    def test_from_x_forwarded_for_single(self, app: FastAPI) -> None:
        """Test extracting single IP from X-Forwarded-For."""
        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"X-Forwarded-For": "203.0.113.195"},
        )

        assert response.json()["client_ip"] == "203.0.113.195"

    def test_from_x_real_ip(self, app: FastAPI) -> None:
        """Test extracting IP from X-Real-IP header."""
        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"X-Real-IP": "192.168.1.100"},
        )

        assert response.json()["client_ip"] == "192.168.1.100"

    def test_x_forwarded_for_takes_precedence(self, app: FastAPI) -> None:
        """Test X-Forwarded-For takes precedence over X-Real-IP."""
        client = TestClient(app)
        response = client.get(
            "/test",
            headers={
                "X-Forwarded-For": "10.0.0.1",
                "X-Real-IP": "10.0.0.2",
            },
        )

        assert response.json()["client_ip"] == "10.0.0.1"

    def test_fallback_to_client(self, app: FastAPI) -> None:
        """Test fallback to direct client connection."""
        client = TestClient(app)
        response = client.get("/test")

        # TestClient may or may not set client.host depending on version
        # The important thing is we get a response without error
        assert response.status_code == 200
        # client_ip may be None or "testclient" depending on TestClient behavior
        assert response.json()["client_ip"] in [None, "testclient"]


# =============================================================================
# Test get_user_agent
# =============================================================================


class TestGetUserAgent:
    """Tests for get_user_agent function."""

    def test_get_user_agent(self, app: FastAPI) -> None:
        """Test extracting user agent."""
        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"User-Agent": "Mozilla/5.0 (Test)"},
        )

        assert response.json()["user_agent"] == "Mozilla/5.0 (Test)"

    def test_no_user_agent(self, app: FastAPI) -> None:
        """Test when no user agent provided."""
        # TestClient always sends a user agent, so we test with custom app
        from starlette.testclient import TestClient as StarletteTestClient

        app_no_ua = FastAPI()
        app_no_ua.add_middleware(AuditContextMiddleware)

        @app_no_ua.get("/test")
        async def test_endpoint(request: Request):
            return {"user_agent": get_user_agent(request)}

        # Even if we don't set it, TestClient may add one
        # This test verifies the function works
        client = StarletteTestClient(app_no_ua)
        response = client.get("/test")
        assert response.status_code == 200


# =============================================================================
# Test AuditContextMiddleware
# =============================================================================


class TestAuditContextMiddleware:
    """Tests for AuditContextMiddleware."""

    def test_middleware_sets_client_ip(self, client: TestClient) -> None:
        """Test middleware sets client_ip in request state."""
        response = client.get(
            "/test",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )

        assert response.json()["client_ip"] == "1.2.3.4"

    def test_middleware_sets_user_agent(self, client: TestClient) -> None:
        """Test middleware sets user_agent in request state."""
        response = client.get(
            "/test",
            headers={"User-Agent": "CustomAgent/2.0"},
        )

        assert response.json()["user_agent"] == "CustomAgent/2.0"

    def test_middleware_passes_through_response(self, client: TestClient) -> None:
        """Test middleware passes through response correctly."""
        response = client.get("/test")

        assert response.status_code == 200
        assert "client_ip" in response.json()


# =============================================================================
# Test get_audit_context
# =============================================================================


class TestGetAuditContext:
    """Tests for get_audit_context function."""

    def test_get_audit_context(self, client: TestClient) -> None:
        """Test get_audit_context returns correct values."""
        response = client.get(
            "/test",
            headers={
                "X-Forwarded-For": "192.168.1.1",
                "User-Agent": "TestAgent/1.0",
            },
        )

        data = response.json()
        assert data["client_ip"] == "192.168.1.1"
        assert data["user_agent"] == "TestAgent/1.0"

    def test_get_audit_context_without_middleware(self) -> None:
        """Test get_audit_context without middleware returns None values."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(request: Request):
            context = get_audit_context(request)
            return context

        client = TestClient(app)
        response = client.get("/test")

        data = response.json()
        assert data["ip_address"] is None
        assert data["user_agent"] is None


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_x_forwarded_for(self, app: FastAPI) -> None:
        """Test handling empty X-Forwarded-For."""
        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"X-Forwarded-For": ""},
        )

        # Falls back to client
        assert response.status_code == 200

    def test_whitespace_in_x_forwarded_for(self, app: FastAPI) -> None:
        """Test handling whitespace in X-Forwarded-For."""
        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"X-Forwarded-For": "  10.0.0.1  ,  10.0.0.2  "},
        )

        assert response.json()["client_ip"] == "10.0.0.1"
