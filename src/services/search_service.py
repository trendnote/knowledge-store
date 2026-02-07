"""Search service for vector and graph search operations.

This module provides a high-level search service that:
- Generates query embeddings using BGE-M3
- Applies ACL-based document filtering
- Performs dense/sparse/hybrid vector search via Milvus
- Supports minimum score filtering

Example:
    >>> from src.services.search_service import get_search_service
    >>> service = get_search_service(milvus_repo, embedding_service, acl_service)
    >>> results = await service.dense_search(
    ...     query="machine learning",
    ...     user_id="user1",
    ...     user_groups=["team-ml"],
    ...     top_k=10,
    ... )
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Protocol

from src.domain.search import SearchHit, SearchResponse, SearchType

if TYPE_CHECKING:
    from scipy.sparse import csr_array


logger = logging.getLogger(__name__)


# =============================================================================
# Protocol Definitions
# =============================================================================


class MilvusRepositoryProtocol(Protocol):
    """Protocol for Milvus repository operations."""

    async def dense_search(
        self,
        query_vector: list[float],
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        security_level: str | None = None,
    ) -> list[SearchHit]:
        """Execute dense vector search."""
        ...

    async def sparse_search(
        self,
        query_sparse: csr_array,
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        security_level: str | None = None,
    ) -> list[SearchHit]:
        """Execute sparse vector search."""
        ...

    async def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse: csr_array,
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        security_level: str | None = None,
        rrf_k: int = 60,
    ) -> list[SearchHit]:
        """Execute hybrid vector search."""
        ...


class EmbeddingServiceProtocol(Protocol):
    """Protocol for embedding service operations."""

    def encode(self, texts: list[str]) -> Any:
        """Encode texts to embeddings.

        Returns:
            EmbeddingResult with dense and sparse embeddings
        """
        ...

    def encode_query(self, query: str) -> Any:
        """Encode single query to embeddings."""
        ...


class AclServiceProtocol(Protocol):
    """Protocol for ACL service operations."""

    async def get_accessible_documents(
        self,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> list[str]:
        """Get accessible document UUIDs for user."""
        ...

    def build_milvus_filter(self, doc_uuids: list[str]) -> str:
        """Build Milvus filter expression."""
        ...


# =============================================================================
# Search Service
# =============================================================================


class SearchService:
    """Service for search operations.

    Provides dense, sparse, and hybrid search capabilities with:
    - Automatic query embedding generation
    - ACL-based document filtering
    - Minimum score thresholding
    - Search time tracking

    Example:
        >>> service = SearchService(milvus_repo, embedding_service, acl_service)
        >>> results = await service.dense_search("query", "user1", ["group1"])
    """

    def __init__(
        self,
        milvus_repo: MilvusRepositoryProtocol,
        embedding_service: EmbeddingServiceProtocol,
        acl_service: AclServiceProtocol,
    ) -> None:
        """Initialize search service.

        Args:
            milvus_repo: Milvus repository for vector search
            embedding_service: Service for generating embeddings
            acl_service: Service for access control
        """
        self._milvus_repo = milvus_repo
        self._embedding_service = embedding_service
        self._acl_service = acl_service

    def _encode_query(self, query: str) -> Any:
        """Encode query to embeddings.

        Args:
            query: Query text

        Returns:
            EmbeddingResult with dense and sparse embeddings
        """
        return self._embedding_service.encode([query])

    async def _get_accessible_doc_uuids(
        self,
        user_id: str,
        user_groups: list[str],
    ) -> list[str]:
        """Get accessible document UUIDs for user.

        Args:
            user_id: User identifier
            user_groups: User's group memberships

        Returns:
            List of accessible document UUIDs
        """
        return await self._acl_service.get_accessible_documents(user_id, user_groups)

    def _filter_by_min_score(
        self,
        results: list[SearchHit],
        min_score: float,
    ) -> list[SearchHit]:
        """Filter results by minimum score.

        Args:
            results: Search results
            min_score: Minimum score threshold

        Returns:
            Filtered results
        """
        if min_score <= 0:
            return results
        return [r for r in results if r.score >= min_score]

    async def dense_search(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
        security_level: str | None = None,
    ) -> list[SearchHit]:
        """Execute dense vector search.

        Uses cosine similarity on dense embeddings (1024 dim BGE-M3).
        Results are filtered by user's accessible documents.

        Args:
            query: Search query text
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold (0.0 to 1.0)
            security_level: Maximum security level for user

        Returns:
            List of search results sorted by score (descending)

        Example:
            >>> results = await service.dense_search(
            ...     query="machine learning",
            ...     user_id="user1",
            ...     user_groups=["team-ml"],
            ...     top_k=10,
            ...     min_score=0.5,
            ... )
        """
        groups = user_groups or []
        start_time = time.time()

        # 1. Get accessible documents
        doc_uuids = await self._get_accessible_doc_uuids(user_id, groups)
        logger.debug(f"User {user_id} has access to {len(doc_uuids)} documents")

        # 2. Generate query embedding
        embeddings = self._encode_query(query)
        if not embeddings or not embeddings.dense:
            logger.warning("Failed to generate query embedding")
            return []

        query_vector = embeddings.dense[0]
        logger.debug(f"Generated query embedding with {len(query_vector)} dimensions")

        # 3. Execute search
        try:
            results = await self._milvus_repo.dense_search(
                query_vector=query_vector,
                doc_uuids=doc_uuids if doc_uuids else None,
                top_k=top_k,
                security_level=security_level,
            )
        except Exception as e:
            logger.exception(f"Dense search failed: {e}")
            raise

        # 4. Filter by minimum score
        results = self._filter_by_min_score(results, min_score)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"Dense search completed: {len(results)} results in {elapsed_ms:.2f}ms"
        )

        return results

    async def dense_search_with_response(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
        security_level: str | None = None,
    ) -> SearchResponse:
        """Execute dense search and return SearchResponse.

        Convenience method that wraps dense_search with timing and metadata.

        Args:
            query: Search query text
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold
            security_level: Maximum security level for user

        Returns:
            SearchResponse with results and metadata
        """
        start_time = time.time()

        results = await self.dense_search(
            query=query,
            user_id=user_id,
            user_groups=user_groups,
            top_k=top_k,
            min_score=min_score,
            security_level=security_level,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            results=results,
            total=len(results),
            search_time_ms=elapsed_ms,
            search_types_used=[SearchType.DENSE],
        )

    async def sparse_search(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
        security_level: str | None = None,
    ) -> list[SearchHit]:
        """Execute sparse vector search (keyword matching).

        Uses sparse embeddings for BM25-like keyword matching.

        Args:
            query: Search query text
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold
            security_level: Maximum security level for user

        Returns:
            List of search results sorted by relevance
        """
        groups = user_groups or []
        start_time = time.time()

        # 1. Get accessible documents
        doc_uuids = await self._get_accessible_doc_uuids(user_id, groups)

        # 2. Generate query embedding
        embeddings = self._encode_query(query)
        if not embeddings or not embeddings.sparse:
            logger.warning("Failed to generate sparse query embedding")
            return []

        query_sparse = embeddings.sparse[0]

        # 3. Execute search
        try:
            results = await self._milvus_repo.sparse_search(
                query_sparse=query_sparse,
                doc_uuids=doc_uuids if doc_uuids else None,
                top_k=top_k,
                security_level=security_level,
            )
        except Exception as e:
            logger.exception(f"Sparse search failed: {e}")
            raise

        # 4. Filter by minimum score
        results = self._filter_by_min_score(results, min_score)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"Sparse search completed: {len(results)} results in {elapsed_ms:.2f}ms"
        )

        return results

    async def hybrid_search(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
        security_level: str | None = None,
        rrf_k: int = 60,
    ) -> list[SearchHit]:
        """Execute hybrid search (dense + sparse with RRF fusion).

        Combines dense semantic search with sparse keyword matching
        using Reciprocal Rank Fusion for better recall.

        Args:
            query: Search query text
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold
            security_level: Maximum security level for user
            rrf_k: RRF parameter k (default: 60)

        Returns:
            List of search results sorted by RRF score
        """
        groups = user_groups or []
        start_time = time.time()

        # 1. Get accessible documents
        doc_uuids = await self._get_accessible_doc_uuids(user_id, groups)

        # 2. Generate query embeddings
        embeddings = self._encode_query(query)
        if not embeddings or not embeddings.dense or not embeddings.sparse:
            logger.warning("Failed to generate query embeddings")
            return []

        query_dense = embeddings.dense[0]
        query_sparse = embeddings.sparse[0]

        # 3. Execute hybrid search
        try:
            results = await self._milvus_repo.hybrid_search(
                query_dense=query_dense,
                query_sparse=query_sparse,
                doc_uuids=doc_uuids if doc_uuids else None,
                top_k=top_k,
                security_level=security_level,
                rrf_k=rrf_k,
            )
        except Exception as e:
            logger.exception(f"Hybrid search failed: {e}")
            raise

        # 4. Filter by minimum score
        results = self._filter_by_min_score(results, min_score)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"Hybrid search completed: {len(results)} results in {elapsed_ms:.2f}ms"
        )

        return results


# =============================================================================
# Singleton Factory
# =============================================================================

_service: SearchService | None = None


def get_search_service(
    milvus_repo: MilvusRepositoryProtocol | None = None,
    embedding_service: EmbeddingServiceProtocol | None = None,
    acl_service: AclServiceProtocol | None = None,
) -> SearchService:
    """Get or create search service singleton.

    Args:
        milvus_repo: Milvus repository (required on first call)
        embedding_service: Embedding service (required on first call)
        acl_service: ACL service (required on first call)

    Returns:
        SearchService instance

    Raises:
        ValueError: If dependencies not provided on first call
    """
    global _service
    if _service is None:
        if milvus_repo is None or embedding_service is None or acl_service is None:
            raise ValueError("All dependencies required for first initialization")
        _service = SearchService(milvus_repo, embedding_service, acl_service)
    return _service


def close_search_service() -> None:
    """Close the search service singleton."""
    global _service
    _service = None


def reset_search_service() -> None:
    """Reset search service singleton (for testing)."""
    global _service
    _service = None
