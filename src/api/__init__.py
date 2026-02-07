"""API package.

This package provides the FastAPI application and API components:
- routers: API endpoint definitions (search, documents)
- schemas: Request/Response validation schemas
- dependencies: Dependency injection configuration
"""

from src.api.routers import documents_router, search_router

__all__ = ["documents_router", "search_router"]
