"""FastAPI dependency injection functions.

This module provides dependency injection for API services:
- SearchService: For search operations
- DocumentService: For document CRUD operations

Usage:
    During app startup, call set_* functions to configure services.
    Routes use get_* functions via FastAPI's Depends().

Example:
    # In main.py or startup
    from src.api.dependencies import set_search_service, set_document_service
    set_search_service(search_service_instance)
    set_document_service(document_service_instance)

    # In router
    from src.api.dependencies import get_search_service
    @router.post("/search")
    async def search(service: Annotated[SearchService, Depends(get_search_service)]):
        ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.document_service import DocumentService
    from src.services.search_service import SearchService


# =============================================================================
# Service Instances
# =============================================================================

_search_service: SearchService | None = None
_document_service: DocumentService | None = None


# =============================================================================
# Search Service
# =============================================================================


def set_search_service(service: SearchService) -> None:
    """Set search service instance for dependency injection.

    Should be called during application startup after service initialization.

    Args:
        service: Configured SearchService instance
    """
    global _search_service
    _search_service = service


async def get_search_service() -> SearchService:
    """Get search service instance.

    Used as a FastAPI dependency.

    Returns:
        SearchService instance

    Raises:
        RuntimeError: If search service not initialized
    """
    if _search_service is None:
        raise RuntimeError(
            "Search service not initialized. "
            "Call set_search_service() during app startup."
        )
    return _search_service


# =============================================================================
# Document Service
# =============================================================================


def set_document_service(service: DocumentService) -> None:
    """Set document service instance for dependency injection.

    Should be called during application startup after service initialization.

    Args:
        service: Configured DocumentService instance
    """
    global _document_service
    _document_service = service


async def get_document_service() -> DocumentService:
    """Get document service instance.

    Used as a FastAPI dependency.

    Returns:
        DocumentService instance

    Raises:
        RuntimeError: If document service not initialized
    """
    if _document_service is None:
        raise RuntimeError(
            "Document service not initialized. "
            "Call set_document_service() during app startup."
        )
    return _document_service


# =============================================================================
# Utilities
# =============================================================================


def reset_dependencies() -> None:
    """Reset all dependency instances.

    Useful for testing to ensure clean state between tests.
    """
    global _search_service, _document_service
    _search_service = None
    _document_service = None
