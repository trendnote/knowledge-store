"""Audit middleware.

This module provides middleware for extracting audit context from requests:
- Client IP address extraction (handles proxies)
- User agent extraction
- Request context for audit logging
"""

from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request.

    Handles various proxy configurations by checking headers in order:
    1. X-Forwarded-For (standard proxy header)
    2. X-Real-IP (nginx proxy)
    3. Direct client connection

    Args:
        request: FastAPI request object

    Returns:
        Client IP address or None if not available
    """
    # Check X-Forwarded-For header (for proxied requests)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First IP in the list is the original client
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client connection
    if request.client:
        return request.client.host

    return None


def get_user_agent(request: Request) -> str | None:
    """Extract user agent from request.

    Args:
        request: FastAPI request object

    Returns:
        User agent string or None if not available
    """
    return request.headers.get("User-Agent")


class AuditContextMiddleware(BaseHTTPMiddleware):
    """Middleware to add audit context to request state.

    Extracts client IP and user agent from the request and stores
    them in request.state for later use in audit logging.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Add audit context to request state.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response from the handler
        """
        # Add audit context to request state
        request.state.client_ip = get_client_ip(request)
        request.state.user_agent = get_user_agent(request)

        return await call_next(request)


def get_audit_context(request: Request) -> dict[str, str | None]:
    """Get audit context from request.

    Helper function to extract audit context that was set by
    AuditContextMiddleware.

    Args:
        request: FastAPI request object

    Returns:
        Dictionary with ip_address and user_agent
    """
    return {
        "ip_address": getattr(request.state, "client_ip", None),
        "user_agent": getattr(request.state, "user_agent", None),
    }
