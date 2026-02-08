"""API middleware package.

This package provides middleware for the Knowledge Store API:
- MetricsMiddleware: Record request metrics for Prometheus
- AuditContextMiddleware: Add audit context to requests
"""

from src.api.middleware.audit import (
    AuditContextMiddleware,
    get_audit_context,
    get_client_ip,
    get_user_agent,
)
from src.api.middleware.metrics import MetricsMiddleware

__all__ = [
    "AuditContextMiddleware",
    "MetricsMiddleware",
    "get_audit_context",
    "get_client_ip",
    "get_user_agent",
]
