"""Custom exceptions for Knowledge Store API.

This module defines application-specific exceptions that are mapped
to HTTP error responses by the exception handlers.
"""

from __future__ import annotations

from typing import Any


class KnowledgeStoreError(Exception):
    """Base exception for Knowledge Store.

    All custom exceptions should inherit from this class.

    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code
        details: Additional error context
    """

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize exception.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code
            details: Additional error context
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


class NotFoundError(KnowledgeStoreError):
    """Resource not found.

    Raised when a requested resource does not exist.
    Maps to HTTP 404.
    """

    def __init__(self, resource: str, resource_id: str) -> None:
        """Initialize not found error.

        Args:
            resource: Type of resource (e.g., "Document", "Chunk")
            resource_id: ID of the resource
        """
        super().__init__(
            message=f"{resource} not found: {resource_id}",
            error_code="NOT_FOUND",
            details={"resource": resource, "resource_id": resource_id},
        )
        self.resource = resource
        self.resource_id = resource_id


class AccessDeniedError(KnowledgeStoreError):
    """Access denied.

    Raised when user lacks permission for the requested operation.
    Maps to HTTP 403.
    """

    def __init__(
        self,
        message: str = "Access denied",
        resource: str | None = None,
        required_permission: str | None = None,
    ) -> None:
        """Initialize access denied error.

        Args:
            message: Human-readable error message
            resource: Resource access was attempted on
            required_permission: Permission that was required
        """
        details: dict[str, Any] = {}
        if resource:
            details["resource"] = resource
        if required_permission:
            details["required_permission"] = required_permission

        super().__init__(
            message=message,
            error_code="ACCESS_DENIED",
            details=details,
        )


class ValidationError(KnowledgeStoreError):
    """Validation error.

    Raised when request data fails validation.
    Maps to HTTP 400.
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
    ) -> None:
        """Initialize validation error.

        Args:
            message: Human-readable error message
            field: Field that failed validation
            value: Invalid value (optional)
        """
        details: dict[str, Any] = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)

        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class ConflictError(KnowledgeStoreError):
    """Conflict error.

    Raised when an operation conflicts with current state.
    Maps to HTTP 409.
    """

    def __init__(
        self,
        message: str,
        resource: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        """Initialize conflict error.

        Args:
            message: Human-readable error message
            resource: Type of resource
            resource_id: ID of the resource
        """
        details: dict[str, Any] = {}
        if resource:
            details["resource"] = resource
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(
            message=message,
            error_code="CONFLICT",
            details=details,
        )


class ServiceUnavailableError(KnowledgeStoreError):
    """Service unavailable.

    Raised when a required service is not available.
    Maps to HTTP 503.
    """

    def __init__(self, service: str, reason: str | None = None) -> None:
        """Initialize service unavailable error.

        Args:
            service: Name of the unavailable service
            reason: Reason for unavailability
        """
        details: dict[str, Any] = {"service": service}
        if reason:
            details["reason"] = reason

        super().__init__(
            message=f"Service unavailable: {service}",
            error_code="SERVICE_UNAVAILABLE",
            details=details,
        )


class RateLimitError(KnowledgeStoreError):
    """Rate limit exceeded.

    Raised when a user exceeds their rate limit.
    Maps to HTTP 429.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
    ) -> None:
        """Initialize rate limit error.

        Args:
            message: Human-readable error message
            retry_after: Seconds until rate limit resets
        """
        details: dict[str, Any] = {}
        if retry_after:
            details["retry_after"] = retry_after

        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            details=details,
        )
        self.retry_after = retry_after


class DatabaseError(KnowledgeStoreError):
    """Database error.

    Raised when a database operation fails.
    Maps to HTTP 500.
    """

    def __init__(
        self,
        message: str = "Database operation failed",
        database: str | None = None,
        operation: str | None = None,
    ) -> None:
        """Initialize database error.

        Args:
            message: Human-readable error message
            database: Name of the database
            operation: Operation that failed
        """
        details: dict[str, Any] = {}
        if database:
            details["database"] = database
        if operation:
            details["operation"] = operation

        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            details=details,
        )
