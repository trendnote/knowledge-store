"""API routers package.

This package provides FastAPI routers for the Knowledge Store API:
- search_router: Hybrid search endpoints
- documents_router: Document CRUD endpoints
"""

from src.api.routers.documents import router as documents_router
from src.api.routers.search import router as search_router

__all__ = ["documents_router", "search_router"]
