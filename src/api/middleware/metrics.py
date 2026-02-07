"""Metrics middleware.

This module provides middleware to record request metrics for Prometheus.
"""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.routers.metrics import record_request


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to record request metrics.

    Records request count and latency for all requests except
    health and metrics endpoints.
    """

    # Paths to exclude from metrics recording
    EXCLUDED_PATHS = frozenset([
        "/api/v1/health",
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/metrics",
    ])

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process request and record metrics.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response from the handler
        """
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time

        # Record metrics (skip excluded endpoints)
        path = request.url.path
        if not self._should_exclude(path):
            record_request(
                method=request.method,
                endpoint=path,
                status=response.status_code,
                duration=duration,
            )

        return response

    def _should_exclude(self, path: str) -> bool:
        """Check if path should be excluded from metrics.

        Args:
            path: Request path

        Returns:
            True if path should be excluded
        """
        # Check exact matches first
        if path in self.EXCLUDED_PATHS:
            return True

        # Check prefix matches
        if path.startswith("/api/v1/health") or path.startswith("/api/v1/metrics"):
            return True

        return False
