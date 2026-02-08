"""Tests for exception handlers."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request, status
from fastapi.testclient import TestClient

from src.api.exception_handlers import (
    ErrorResponse,
    access_denied_handler,
    conflict_handler,
    create_error_response,
    database_error_handler,
    generic_error_handler,
    not_found_handler,
    rate_limit_handler,
    register_exception_handlers,
    request_validation_handler,
    service_unavailable_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from src.api.exceptions import (
    AccessDeniedError,
    ConflictError,
    DatabaseError,
    KnowledgeStoreError,
    NotFoundError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)


class TestErrorResponse:
    """Tests for ErrorResponse schema."""

    def test_basic_error_response(self) -> None:
        """Test basic error response."""
        response = ErrorResponse(
            error="Not Found",
            message="Resource not found",
        )

        assert response.error == "Not Found"
        assert response.message == "Resource not found"
        assert response.error_code is None
        assert response.details == {}

    def test_full_error_response(self) -> None:
        """Test error response with all fields."""
        response = ErrorResponse(
            error="Bad Request",
            message="Invalid input",
            error_code="VALIDATION_ERROR",
            details={"field": "email"},
        )

        assert response.error_code == "VALIDATION_ERROR"
        assert response.details["field"] == "email"

    def test_model_dump(self) -> None:
        """Test error response serialization."""
        response = ErrorResponse(
            error="Error",
            message="Test",
            error_code="TEST",
            details={"key": "value"},
        )

        data = response.model_dump()

        assert data["error"] == "Error"
        assert data["message"] == "Test"
        assert data["error_code"] == "TEST"
        assert data["details"]["key"] == "value"


class TestCreateErrorResponse:
    """Tests for create_error_response function."""

    def test_basic_response(self) -> None:
        """Test basic error response creation."""
        response = create_error_response(
            status_code=404,
            error="Not Found",
            message="Resource not found",
        )

        assert response.status_code == 404
        data = response.body.decode()
        assert "Not Found" in data
        assert "Resource not found" in data

    def test_response_with_all_fields(self) -> None:
        """Test error response with all fields."""
        response = create_error_response(
            status_code=400,
            error="Bad Request",
            message="Validation failed",
            error_code="VALIDATION_ERROR",
            details={"field": "email"},
        )

        assert response.status_code == 400

    def test_response_with_headers(self) -> None:
        """Test error response with custom headers."""
        response = create_error_response(
            status_code=429,
            error="Too Many Requests",
            message="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )

        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "60"


class TestExceptionHandlers:
    """Tests for individual exception handlers."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app."""
        app = FastAPI()
        register_exception_handlers(app)
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_not_found_handler(self, app: FastAPI, client: TestClient) -> None:
        """Test NotFoundError handler."""

        @app.get("/test")
        def test_route() -> None:
            raise NotFoundError("Document", "doc-123")

        response = client.get("/test")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "Not Found"
        assert "Document not found" in data["message"]
        assert data["error_code"] == "NOT_FOUND"

    def test_access_denied_handler(self, app: FastAPI, client: TestClient) -> None:
        """Test AccessDeniedError handler."""

        @app.get("/test")
        def test_route() -> None:
            raise AccessDeniedError("You cannot access this")

        response = client.get("/test")

        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "Forbidden"
        assert data["error_code"] == "ACCESS_DENIED"

    def test_validation_error_handler(self, app: FastAPI, client: TestClient) -> None:
        """Test ValidationError handler."""

        @app.get("/test")
        def test_route() -> None:
            raise ValidationError("Invalid email", field="email")

        response = client.get("/test")

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Bad Request"
        assert data["error_code"] == "VALIDATION_ERROR"

    def test_conflict_handler(self, app: FastAPI, client: TestClient) -> None:
        """Test ConflictError handler."""

        @app.get("/test")
        def test_route() -> None:
            raise ConflictError("Resource already exists")

        response = client.get("/test")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "Conflict"
        assert data["error_code"] == "CONFLICT"

    def test_service_unavailable_handler(
        self, app: FastAPI, client: TestClient
    ) -> None:
        """Test ServiceUnavailableError handler."""

        @app.get("/test")
        def test_route() -> None:
            raise ServiceUnavailableError("Database")

        response = client.get("/test")

        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "Service Unavailable"
        assert data["error_code"] == "SERVICE_UNAVAILABLE"

    def test_rate_limit_handler(self, app: FastAPI, client: TestClient) -> None:
        """Test RateLimitError handler."""

        @app.get("/test")
        def test_route() -> None:
            raise RateLimitError(retry_after=60)

        response = client.get("/test")

        assert response.status_code == 429
        data = response.json()
        assert data["error"] == "Too Many Requests"
        assert data["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert response.headers.get("Retry-After") == "60"

    def test_rate_limit_handler_no_retry_after(
        self, app: FastAPI, client: TestClient
    ) -> None:
        """Test RateLimitError handler without retry after."""

        @app.get("/test")
        def test_route() -> None:
            raise RateLimitError()

        response = client.get("/test")

        assert response.status_code == 429
        assert "Retry-After" not in response.headers

    def test_database_error_handler(self, app: FastAPI, client: TestClient) -> None:
        """Test DatabaseError handler."""

        @app.get("/test")
        def test_route() -> None:
            raise DatabaseError("Connection failed", database="PostgreSQL")

        response = client.get("/test")

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "Internal Server Error"
        # Should not expose internal database details
        assert data["message"] == "A database error occurred"
        assert data["details"] == {}

    def test_generic_error_handler(self, app: FastAPI, client: TestClient) -> None:
        """Test generic KnowledgeStoreError handler."""

        @app.get("/test")
        def test_route() -> None:
            raise KnowledgeStoreError("Something went wrong")

        response = client.get("/test")

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "Internal Server Error"
        assert data["message"] == "Something went wrong"

    def test_unhandled_exception_handler(
        self, app: FastAPI, client: TestClient
    ) -> None:
        """Test unhandled exception handler."""

        @app.get("/test")
        def test_route() -> None:
            raise ValueError("Unexpected error")

        response = client.get("/test")

        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "Internal Server Error"
        assert data["message"] == "An unexpected error occurred"


class TestRequestValidationHandler:
    """Tests for FastAPI request validation handler."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/test")
        def test_route(count: int) -> dict:
            return {"count": count}

        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_validation_error_response(self, client: TestClient) -> None:
        """Test validation error response format."""
        response = client.get("/test?count=not-a-number")

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Unprocessable Entity"
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "errors" in data["details"]

    def test_missing_required_param(self, client: TestClient) -> None:
        """Test missing required parameter."""
        response = client.get("/test")

        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Unprocessable Entity"


class TestRegisterExceptionHandlers:
    """Tests for register_exception_handlers function."""

    def test_registers_all_handlers(self) -> None:
        """Test that all handlers are registered."""
        app = FastAPI()

        register_exception_handlers(app)

        # Check that handlers are registered
        handlers = app.exception_handlers

        assert NotFoundError in handlers
        assert AccessDeniedError in handlers
        assert ValidationError in handlers
        assert ConflictError in handlers
        assert ServiceUnavailableError in handlers
        assert RateLimitError in handlers
        assert DatabaseError in handlers
        assert KnowledgeStoreError in handlers
        assert Exception in handlers

    def test_handler_priority(self) -> None:
        """Test that specific handlers take priority over generic ones."""
        app = FastAPI()
        register_exception_handlers(app)
        client = TestClient(app, raise_server_exceptions=False)

        @app.get("/not-found")
        def not_found_route() -> None:
            raise NotFoundError("Test", "123")

        @app.get("/generic")
        def generic_route() -> None:
            raise KnowledgeStoreError("Generic error")

        # NotFoundError should use 404 handler, not 500
        response = client.get("/not-found")
        assert response.status_code == 404

        # Generic should use 500
        response = client.get("/generic")
        assert response.status_code == 500


class TestExceptionHandlerIntegration:
    """Integration tests for exception handling."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with various routes."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/document/{doc_id}")
        def get_document(doc_id: str) -> dict:
            if doc_id == "not-found":
                raise NotFoundError("Document", doc_id)
            if doc_id == "forbidden":
                raise AccessDeniedError("Cannot access this document")
            return {"id": doc_id}

        @app.post("/validate")
        def validate(data: dict) -> dict:
            if "email" not in data:
                raise ValidationError("Email is required", field="email")
            return data

        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_successful_request(self, client: TestClient) -> None:
        """Test successful request returns normal response."""
        response = client.get("/document/valid-id")

        assert response.status_code == 200
        assert response.json()["id"] == "valid-id"

    def test_not_found_exception(self, client: TestClient) -> None:
        """Test not found exception is handled."""
        response = client.get("/document/not-found")

        assert response.status_code == 404
        assert response.json()["error_code"] == "NOT_FOUND"

    def test_access_denied_exception(self, client: TestClient) -> None:
        """Test access denied exception is handled."""
        response = client.get("/document/forbidden")

        assert response.status_code == 403
        assert response.json()["error_code"] == "ACCESS_DENIED"

    def test_error_response_format(self, client: TestClient) -> None:
        """Test error response follows consistent format."""
        response = client.get("/document/not-found")

        data = response.json()

        # All error responses should have these fields
        assert "error" in data
        assert "message" in data
        assert "error_code" in data
        assert "details" in data
