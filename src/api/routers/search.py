"""Search API router.

This module provides the search API endpoint:
- POST /search: Execute hybrid search combining dense, sparse, and graph search

The router uses dependency injection for the search service,
allowing easy testing and configuration.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemas.search import (
    SearchRequestSchema,
    SearchResponseSchema,
    SearchResultSchema,
    SearchTypeEnum,
)
from src.domain.search import SearchRequest, SearchType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# =============================================================================
# Dependency Injection
# =============================================================================


async def get_search_service() -> Any:
    """Get search service instance.

    This is a placeholder that will be overridden during app initialization.

    Raises:
        NotImplementedError: Always, until properly configured
    """
    raise NotImplementedError("Search service not configured")


# =============================================================================
# Type Conversion Helpers
# =============================================================================


def _convert_api_to_domain_types(
    types: list[SearchTypeEnum] | None,
) -> list[SearchType] | None:
    """Convert API enum to domain enum.

    Args:
        types: List of API SearchTypeEnum values

    Returns:
        List of domain SearchType values, or None if input is None
    """
    if types is None:
        return None

    mapping = {
        SearchTypeEnum.DENSE: SearchType.DENSE,
        SearchTypeEnum.SPARSE: SearchType.SPARSE,
        SearchTypeEnum.GRAPH: SearchType.GRAPH,
        SearchTypeEnum.HYBRID: SearchType.HYBRID,
    }
    return [mapping[t] for t in types]


def _convert_domain_to_api_type(t: SearchType) -> str:
    """Convert domain enum to API string.

    Args:
        t: Domain SearchType value

    Returns:
        String value for API response
    """
    return t.value


# =============================================================================
# Search Endpoint
# =============================================================================


@router.post(
    "",
    response_model=SearchResponseSchema,
    summary="Hybrid Search",
    description="""
Execute hybrid search combining dense (semantic), sparse (keyword),
and graph (relationship) search.

The search uses Reciprocal Rank Fusion (RRF) to merge results from
different search types for optimal relevance.

**Features:**
- Dense search: Semantic similarity using BGE-M3 embeddings
- Sparse search: Keyword matching using BM25-style sparse vectors
- Graph search: Relationship-based search via Neo4j

**Access Control:**
Results are filtered based on user_id and user_groups to ensure
users only see documents they have permission to access.
""",
    responses={
        200: {
            "description": "Search results",
            "model": SearchResponseSchema,
        },
        400: {
            "description": "Invalid request parameters",
            "content": {
                "application/json": {
                    "example": {"detail": "Query cannot be empty"}
                }
            },
        },
        403: {
            "description": "Access denied",
            "content": {
                "application/json": {
                    "example": {"detail": "Access denied"}
                }
            },
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Search failed"}
                }
            },
        },
    },
)
async def search(
    request: SearchRequestSchema,
    search_service: Any = Depends(get_search_service),
) -> SearchResponseSchema:
    """Execute hybrid search.

    Combines dense (semantic), sparse (keyword), and graph (relationship)
    search for comprehensive results using RRF fusion.

    Args:
        request: Search request with query and parameters
        search_service: Injected search service instance

    Returns:
        SearchResponseSchema with results and metadata

    Raises:
        HTTPException: 400 for invalid request, 403 for access denied,
                      500 for internal errors
    """
    logger.info(
        f"Search request: query='{request.query[:50]}...' "
        f"user={request.user_id} top_k={request.top_k}"
    )

    try:
        # Convert API types to domain types
        search_types = _convert_api_to_domain_types(request.search_types)

        # Build domain request
        domain_request = SearchRequest(
            query=request.query,
            user_id=request.user_id,
            user_groups=request.user_groups,
            top_k=request.top_k,
            search_types=search_types
            or [SearchType.DENSE, SearchType.SPARSE, SearchType.GRAPH],
            min_score=request.min_score,
        )

        # Execute unified search
        response = await search_service.unified_search(domain_request)

        # Convert to API response
        results = [
            SearchResultSchema(
                chunk_uuid=hit.chunk_uuid,
                doc_uuid=hit.doc_uuid,
                score=hit.score,
                search_type=hit.search_type,
                text_preview=hit.chunk_text[:500] if hit.chunk_text else None,
                title=hit.metadata.get("title") if hit.metadata else None,
                metadata=hit.metadata or {},
            )
            for hit in response.results
        ]

        logger.info(
            f"Search completed: {response.total} results "
            f"in {response.search_time_ms:.2f}ms"
        )

        return SearchResponseSchema(
            results=results,
            total=response.total,
            search_time_ms=response.search_time_ms,
            search_types_used=[
                _convert_domain_to_api_type(t) for t in response.search_types_used
            ],
        )

    except ValueError as e:
        logger.warning(f"Invalid search request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except PermissionError as e:
        logger.warning(f"Access denied for user {request.user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    except Exception as e:
        logger.exception(f"Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed",
        )
