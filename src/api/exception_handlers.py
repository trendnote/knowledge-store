"""Exception handlers for FastAPI application.

This module provides exception handlers that convert custom exceptions
to appropriate HTTP responses with consistent error format.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    """Standard error response schema.

    Attributes:
        error: Error type name
        message: Human-readable error message
        error_code: Machine-readable error code
        details: Additional error context
    """

    error: str
    message: str
    error_code: str | None = None
    details: dict[str, Any] = {}


def create_error_response(
    status_code: int,
    error: str,
    message: str,
    error_code: str | None = None,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Create standardized error JSON response.

    Args:
        status_code: HTTP status code
        error: Error type name
        message: Human-readable error message
        error_code: Machine-readable error code
        details: Additional error context
        headers: Optional response headers

    Returns:
        JSONResponse with error content
    """
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=error,
            message=message,
            error_code=error_code,
            details=details or {},
        ).model_dump(),
        headers=headers,
    )


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Handle NotFoundError.

    Args:
        request: FastAPI request
        exc: NotFoundError instance

    Returns:
        404 JSONResponse
    """
    logger.warning(f"Not found: {exc.message} [path={request.url.path}]")
    return create_error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        error="Not Found",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def access_denied_handler(
    request: Request, exc: AccessDeniedError
) -> JSONResponse:
    """Handle AccessDeniedError.

    Args:
        request: FastAPI request
        exc: AccessDeniedError instance

    Returns:
        403 JSONResponse
    """
    logger.warning(f"Access denied: {exc.message} [path={request.url.path}]")
    return create_error_response(
        status_code=status.HTTP_403_FORBIDDEN,
        error="Forbidden",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def validation_error_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Handle ValidationError.

    Args:
        request: FastAPI request
        exc: ValidationError instance

    Returns:
        400 JSONResponse
    """
    return create_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        error="Bad Request",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    """Handle ConflictError.

    Args:
        request: FastAPI request
        exc: ConflictError instance

    Returns:
        409 JSONResponse
    """
    logger.warning(f"Conflict: {exc.message} [path={request.url.path}]")
    return create_error_response(
        status_code=status.HTTP_409_CONFLICT,
        error="Conflict",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def service_unavailable_handler(
    request: Request, exc: ServiceUnavailableError
) -> JSONResponse:
    """Handle ServiceUnavailableError.

    Args:
        request: FastAPI request
        exc: ServiceUnavailableError instance

    Returns:
        503 JSONResponse
    """
    logger.error(f"Service unavailable: {exc.message}")
    return create_error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        error="Service Unavailable",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def rate_limit_handler(request: Request, exc: RateLimitError) -> JSONResponse:
    """Handle RateLimitError.

    Args:
        request: FastAPI request
        exc: RateLimitError instance

    Returns:
        429 JSONResponse
    """
    headers = {}
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)

    logger.warning(f"Rate limit exceeded: {request.url.path}")
    return create_error_response(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        error="Too Many Requests",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
        headers=headers if headers else None,
    )


async def database_error_handler(
    request: Request, exc: DatabaseError
) -> JSONResponse:
    """Handle DatabaseError.

    Args:
        request: FastAPI request
        exc: DatabaseError instance

    Returns:
        500 JSONResponse
    """
    logger.error(f"Database error: {exc.message}")
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="Internal Server Error",
        message="A database error occurred",
        error_code=exc.error_code,
        # Don't expose internal database details
        details={},
    )


async def generic_error_handler(
    request: Request, exc: KnowledgeStoreError
) -> JSONResponse:
    """Handle generic KnowledgeStoreError.

    Args:
        request: FastAPI request
        exc: KnowledgeStoreError instance

    Returns:
        500 JSONResponse
    """
    logger.error(f"Application error: {exc.message}")
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="Internal Server Error",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle FastAPI RequestValidationError.

    Args:
        request: FastAPI request
        exc: RequestValidationError instance

    Returns:
        422 JSONResponse
    """
    errors = exc.errors()
    first_error = errors[0] if errors else {}

    # Extract field location
    loc = first_error.get("loc", [])
    field = ".".join(str(l) for l in loc[1:]) if len(loc) > 1 else None

    return create_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error="Unprocessable Entity",
        message=first_error.get("msg", "Validation error"),
        error_code="VALIDATION_ERROR",
        details={
            "field": field,
            "errors": [
                {
                    "field": ".".join(str(l) for l in e.get("loc", [])[1:]),
                    "message": e.get("msg"),
                    "type": e.get("type"),
                }
                for e in errors
            ],
        },
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle unhandled exceptions.

    This is a catch-all handler for any exceptions not caught by
    specific handlers.

    Args:
        request: FastAPI request
        exc: Exception instance

    Returns:
        500 JSONResponse
    """
    logger.exception(f"Unhandled exception: {exc}")
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="Internal Server Error",
        message="An unexpected error occurred",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI app.

    Args:
        app: FastAPI application instance
    """
    # Custom exceptions (order: specific -> generic)
    app.add_exception_handler(NotFoundError, not_found_handler)
    app.add_exception_handler(AccessDeniedError, access_denied_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(ConflictError, conflict_handler)
    app.add_exception_handler(ServiceUnavailableError, service_unavailable_handler)
    app.add_exception_handler(RateLimitError, rate_limit_handler)
    app.add_exception_handler(DatabaseError, database_error_handler)
    app.add_exception_handler(KnowledgeStoreError, generic_error_handler)

    # FastAPI built-in exceptions
    app.add_exception_handler(RequestValidationError, request_validation_handler)

    # Catch-all handler
    app.add_exception_handler(Exception, unhandled_exception_handler)
