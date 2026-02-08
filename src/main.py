"""Knowledge Store Layer - FastAPI Application Entry Point.

This module provides the FastAPI application with:
- Lifespan management (startup/shutdown)
- Router registration
- Middleware configuration
- CORS settings
- Exception handlers
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src import __version__
from src.api.dependencies import (
    close_clients,
    get_clients_for_health,
    init_clients,
    init_services,
)
from src.api.exception_handlers import register_exception_handlers
from src.api.middleware.audit import AuditContextMiddleware
from src.api.middleware.metrics import MetricsMiddleware
from src.api.routers import (
    documents_router,
    health_router,
    metrics_router,
    search_router,
)
from src.api.routers.health import set_clients as set_health_clients
from src.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Manages startup and shutdown events:
    - Startup: Initialize database clients and services
    - Shutdown: Close all connections gracefully

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup
    logger.info("Starting Knowledge Store application...")

    try:
        # Initialize clients (databases, kafka, embedding)
        await init_clients()

        # Initialize services (document, search, acl, audit)
        await init_services()

        # Set health check clients
        set_health_clients(**get_clients_for_health())

        logger.info("Application started successfully")
        yield

    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise

    finally:
        # Shutdown
        logger.info("Shutting down application...")
        await close_clients()
        logger.info("Application shut down")


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()

    app = FastAPI(
        title="Knowledge Store API",
        description=(
            "Knowledge Store Layer for enterprise document management and search. "
            "Provides Tri-Store Architecture (Vector + Graph + RDB) for GraphRAG Platform."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ==========================================================================
    # CORS Configuration
    # ==========================================================================

    cors_origins = settings.api.cors_origins
    if settings.is_development:
        # Allow all origins in development
        cors_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ==========================================================================
    # Custom Middleware (order: outer -> inner)
    # ==========================================================================

    # Metrics middleware (outermost - measures total request time)
    app.add_middleware(MetricsMiddleware)

    # Audit context middleware (extracts client IP, user agent)
    app.add_middleware(AuditContextMiddleware)

    # ==========================================================================
    # Exception Handlers
    # ==========================================================================

    register_exception_handlers(app)

    # ==========================================================================
    # Router Registration
    # ==========================================================================

    # API v1 routers
    app.include_router(
        documents_router,
        prefix="/api/v1",
        tags=["documents"],
    )
    app.include_router(
        search_router,
        prefix="/api/v1",
        tags=["search"],
    )
    app.include_router(
        health_router,
        prefix="/api/v1",
        tags=["health"],
    )
    app.include_router(
        metrics_router,
        prefix="/api/v1",
        tags=["metrics"],
    )

    # ==========================================================================
    # Root Endpoints
    # ==========================================================================

    @app.get("/", tags=["root"])
    async def root() -> dict:
        """Root endpoint returning API information.

        Returns:
            API name, version, and documentation URL
        """
        return {
            "name": "Knowledge Store API",
            "version": __version__,
            "description": "Tri-Store Architecture for GraphRAG Platform",
            "docs": "/api/docs",
            "health": "/api/v1/health",
        }

    @app.get("/health", tags=["root"])
    async def root_health() -> dict:
        """Simple health check endpoint.

        For detailed health checks, use /api/v1/health.

        Returns:
            Simple health status
        """
        return {"status": "healthy"}

    return app


# =============================================================================
# Application Instance
# =============================================================================

app = create_app()


# =============================================================================
# Development Server
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "src.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.is_development,
        log_level=settings.log.level.lower(),
    )
