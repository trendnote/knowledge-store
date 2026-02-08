"""Tests for FastAPI application."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestAppCreation:
    """Tests for application creation."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_app_creation(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test application creation."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        assert app.title == "Knowledge Store API"
        assert app.version is not None
        assert app.docs_url == "/api/docs"
        assert app.redoc_url == "/api/redoc"
        assert app.openapi_url == "/api/openapi.json"


class TestAppLifespan:
    """Tests for application lifespan events."""

    def test_startup_calls_init(self) -> None:
        """Test startup initializes clients and services."""
        with (
            patch("src.main.init_clients", new_callable=AsyncMock) as mock_init_clients,
            patch("src.main.init_services", new_callable=AsyncMock) as mock_init_services,
            patch("src.main.close_clients", new_callable=AsyncMock),
            patch("src.main.set_health_clients"),
            patch("src.main.get_clients_for_health", return_value={
                "postgres": None,
                "milvus": None,
                "neo4j": None,
                "kafka": None,
            }),
        ):
            from src.main import create_app

            app = create_app()

            with TestClient(app):
                mock_init_clients.assert_called_once()
                mock_init_services.assert_called_once()

    def test_shutdown_calls_close(self) -> None:
        """Test shutdown closes clients."""
        with (
            patch("src.main.init_clients", new_callable=AsyncMock),
            patch("src.main.init_services", new_callable=AsyncMock),
            patch("src.main.close_clients", new_callable=AsyncMock) as mock_close,
            patch("src.main.set_health_clients"),
            patch("src.main.get_clients_for_health", return_value={
                "postgres": None,
                "milvus": None,
                "neo4j": None,
                "kafka": None,
            }),
        ):
            from src.main import create_app

            app = create_app()

            with TestClient(app):
                pass

            mock_close.assert_called_once()


class TestRootEndpoints:
    """Tests for root endpoints."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_root_endpoint(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test root endpoint returns API info."""
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
            assert "version" in data
            assert data["docs"] == "/api/docs"
            assert data["health"] == "/api/v1/health"

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_root_health_endpoint(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test root health endpoint returns simple status."""
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
            assert response.json()["status"] == "healthy"


class TestRouterRegistration:
    """Tests for router registration."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_all_routers_registered(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test all routers are registered."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        routes = [route.path for route in app.routes]

        # Check that expected routes exist
        assert any("/documents" in r for r in routes)
        assert any("/search" in r for r in routes)
        assert any("/health" in r for r in routes)
        assert any("/metrics" in r for r in routes)


class TestOpenAPI:
    """Tests for OpenAPI documentation."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_openapi_available(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test OpenAPI documentation is available."""
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
            data = response.json()
            assert "openapi" in data
            assert data["info"]["title"] == "Knowledge Store API"

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_swagger_docs_available(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test Swagger UI is available."""
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
            assert "swagger" in response.text.lower() or "html" in response.headers.get(
                "content-type", ""
            )


class TestCORS:
    """Tests for CORS configuration."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_cors_headers_present(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test CORS headers are present in response."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        with TestClient(app) as client:
            response = client.options(
                "/",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )

            # CORS preflight should succeed
            assert response.status_code == 200


class TestMiddleware:
    """Tests for middleware configuration."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_middleware_registered(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test middleware is registered."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        # Check middleware stack includes our middleware
        middleware_names = [m.cls.__name__ for m in app.user_middleware]

        assert "MetricsMiddleware" in middleware_names
        assert "AuditContextMiddleware" in middleware_names


class TestExceptionHandlerRegistration:
    """Tests for exception handler registration."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    @patch("src.api.routers.health.set_clients")
    @patch("src.api.dependencies.get_clients_for_health")
    def test_exception_handlers_registered(
        self,
        mock_get_clients: MagicMock,
        mock_set_clients: MagicMock,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test exception handlers are registered."""
        mock_get_clients.return_value = {
            "postgres": None,
            "milvus": None,
            "neo4j": None,
            "kafka": None,
        }

        from src.main import create_app

        app = create_app()

        # Check that exception handlers are registered
        from src.api.exceptions import (
            NotFoundError,
            AccessDeniedError,
            KnowledgeStoreError,
        )

        assert NotFoundError in app.exception_handlers
        assert AccessDeniedError in app.exception_handlers
        assert KnowledgeStoreError in app.exception_handlers


class TestDevelopmentServer:
    """Tests for development server configuration."""

    def test_main_module_runnable(self) -> None:
        """Test that main module can be imported."""
        from src import main

        assert hasattr(main, "app")
        assert hasattr(main, "create_app")
