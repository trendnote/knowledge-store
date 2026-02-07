"""API middleware package.

This package provides middleware for the Knowledge Store API:
- MetricsMiddleware: Record request metrics for Prometheus
"""

from src.api.middleware.metrics import MetricsMiddleware

__all__ = ["MetricsMiddleware"]
