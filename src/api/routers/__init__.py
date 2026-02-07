"""API routers package.

This package provides FastAPI routers for the Knowledge Store API.
"""

from src.api.routers.search import router as search_router

__all__ = ["search_router"]
