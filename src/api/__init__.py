"""API package.

This package provides the FastAPI application and API components:
- routers: API endpoint definitions
- schemas: Request/Response validation schemas
- dependencies: Dependency injection configuration
"""

from src.api.routers import search_router

__all__ = ["search_router"]
