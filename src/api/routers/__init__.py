"""API routers package.

This package provides FastAPI routers for the Knowledge Store API:
- search_router: Hybrid search endpoints
- documents_router: Document CRUD endpoints
- health_router: Health check endpoints
- metrics_router: Prometheus metrics endpoints
"""

from src.api.routers.documents import router as documents_router
from src.api.routers.health import router as health_router
from src.api.routers.metrics import router as metrics_router
from src.api.routers.search import router as search_router

__all__ = ["documents_router", "health_router", "metrics_router", "search_router"]
