"""Tests for custom exceptions."""

from __future__ import annotations

import pytest

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


class TestKnowledgeStoreError:
    """Tests for base KnowledgeStoreError."""

    def test_basic_error(self) -> None:
        """Test basic error creation."""
        error = KnowledgeStoreError("Test error")

        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.error_code is None
        assert error.details == {}

    def test_error_with_code(self) -> None:
        """Test error with error code."""
        error = KnowledgeStoreError("Test error", error_code="TEST_ERROR")

        assert error.error_code == "TEST_ERROR"

    def test_error_with_details(self) -> None:
        """Test error with details."""
        details = {"key": "value", "count": 42}
        error = KnowledgeStoreError("Test error", details=details)

        assert error.details == details
        assert error.details["key"] == "value"
        assert error.details["count"] == 42

    def test_full_error(self) -> None:
        """Test error with all parameters."""
        error = KnowledgeStoreError(
            message="Full error",
            error_code="FULL_ERROR",
            details={"info": "test"},
        )

        assert error.message == "Full error"
        assert error.error_code == "FULL_ERROR"
        assert error.details == {"info": "test"}

    def test_is_exception(self) -> None:
        """Test that KnowledgeStoreError is an Exception."""
        error = KnowledgeStoreError("Test")

        assert isinstance(error, Exception)

        with pytest.raises(KnowledgeStoreError):
            raise error


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_basic_not_found(self) -> None:
        """Test basic not found error."""
        error = NotFoundError("Document", "doc-123")

        assert error.message == "Document not found: doc-123"
        assert error.error_code == "NOT_FOUND"
        assert error.resource == "Document"
        assert error.resource_id == "doc-123"

    def test_details(self) -> None:
        """Test not found error details."""
        error = NotFoundError("Chunk", "chunk-456")

        assert error.details["resource"] == "Chunk"
        assert error.details["resource_id"] == "chunk-456"

    def test_inherits_from_base(self) -> None:
        """Test inheritance from KnowledgeStoreError."""
        error = NotFoundError("Test", "test-id")

        assert isinstance(error, KnowledgeStoreError)


class TestAccessDeniedError:
    """Tests for AccessDeniedError."""

    def test_default_message(self) -> None:
        """Test default access denied message."""
        error = AccessDeniedError()

        assert error.message == "Access denied"
        assert error.error_code == "ACCESS_DENIED"
        assert error.details == {}

    def test_custom_message(self) -> None:
        """Test custom access denied message."""
        error = AccessDeniedError(message="You cannot access this resource")

        assert error.message == "You cannot access this resource"

    def test_with_resource(self) -> None:
        """Test access denied with resource."""
        error = AccessDeniedError(
            message="Cannot access document",
            resource="document-123",
        )

        assert error.details["resource"] == "document-123"

    def test_with_required_permission(self) -> None:
        """Test access denied with required permission."""
        error = AccessDeniedError(
            message="Insufficient permissions",
            required_permission="read",
        )

        assert error.details["required_permission"] == "read"

    def test_full_access_denied(self) -> None:
        """Test access denied with all parameters."""
        error = AccessDeniedError(
            message="Cannot edit document",
            resource="doc-123",
            required_permission="write",
        )

        assert error.message == "Cannot edit document"
        assert error.details["resource"] == "doc-123"
        assert error.details["required_permission"] == "write"


class TestValidationError:
    """Tests for ValidationError."""

    def test_basic_validation_error(self) -> None:
        """Test basic validation error."""
        error = ValidationError("Invalid input")

        assert error.message == "Invalid input"
        assert error.error_code == "VALIDATION_ERROR"
        assert error.details == {}

    def test_with_field(self) -> None:
        """Test validation error with field."""
        error = ValidationError("Invalid email format", field="email")

        assert error.details["field"] == "email"

    def test_with_value(self) -> None:
        """Test validation error with value."""
        error = ValidationError("Value too large", field="count", value=1000)

        assert error.details["field"] == "count"
        assert error.details["value"] == "1000"

    def test_value_conversion(self) -> None:
        """Test that value is converted to string."""
        error = ValidationError("Invalid", value=123)

        assert error.details["value"] == "123"


class TestConflictError:
    """Tests for ConflictError."""

    def test_basic_conflict(self) -> None:
        """Test basic conflict error."""
        error = ConflictError("Resource already exists")

        assert error.message == "Resource already exists"
        assert error.error_code == "CONFLICT"

    def test_with_resource(self) -> None:
        """Test conflict with resource."""
        error = ConflictError(
            "Document version conflict",
            resource="Document",
            resource_id="doc-123",
        )

        assert error.details["resource"] == "Document"
        assert error.details["resource_id"] == "doc-123"


class TestServiceUnavailableError:
    """Tests for ServiceUnavailableError."""

    def test_basic_unavailable(self) -> None:
        """Test basic service unavailable error."""
        error = ServiceUnavailableError("Database")

        assert error.message == "Service unavailable: Database"
        assert error.error_code == "SERVICE_UNAVAILABLE"
        assert error.details["service"] == "Database"

    def test_with_reason(self) -> None:
        """Test service unavailable with reason."""
        error = ServiceUnavailableError("Milvus", reason="Connection timeout")

        assert error.details["service"] == "Milvus"
        assert error.details["reason"] == "Connection timeout"


class TestRateLimitError:
    """Tests for RateLimitError."""

    def test_default_message(self) -> None:
        """Test default rate limit message."""
        error = RateLimitError()

        assert error.message == "Rate limit exceeded"
        assert error.error_code == "RATE_LIMIT_EXCEEDED"
        assert error.retry_after is None

    def test_custom_message(self) -> None:
        """Test custom rate limit message."""
        error = RateLimitError("Too many search requests")

        assert error.message == "Too many search requests"

    def test_with_retry_after(self) -> None:
        """Test rate limit with retry after."""
        error = RateLimitError(retry_after=60)

        assert error.retry_after == 60
        assert error.details["retry_after"] == 60


class TestDatabaseError:
    """Tests for DatabaseError."""

    def test_default_message(self) -> None:
        """Test default database error message."""
        error = DatabaseError()

        assert error.message == "Database operation failed"
        assert error.error_code == "DATABASE_ERROR"

    def test_with_database(self) -> None:
        """Test database error with database name."""
        error = DatabaseError(
            "Connection failed",
            database="PostgreSQL",
        )

        assert error.details["database"] == "PostgreSQL"

    def test_with_operation(self) -> None:
        """Test database error with operation."""
        error = DatabaseError(
            "Query timeout",
            database="Milvus",
            operation="vector_search",
        )

        assert error.details["database"] == "Milvus"
        assert error.details["operation"] == "vector_search"


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_all_inherit_from_base(self) -> None:
        """Test all exceptions inherit from KnowledgeStoreError."""
        exceptions = [
            NotFoundError("Test", "id"),
            AccessDeniedError(),
            ValidationError("test"),
            ConflictError("test"),
            ServiceUnavailableError("test"),
            RateLimitError(),
            DatabaseError(),
        ]

        for exc in exceptions:
            assert isinstance(exc, KnowledgeStoreError)
            assert isinstance(exc, Exception)

    def test_can_catch_by_base(self) -> None:
        """Test can catch all exceptions by base class."""
        exceptions = [
            NotFoundError("Test", "id"),
            AccessDeniedError(),
            ValidationError("test"),
        ]

        for exc in exceptions:
            try:
                raise exc
            except KnowledgeStoreError as caught:
                assert caught.message is not None
                assert caught.error_code is not None
