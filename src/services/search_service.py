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

from src.domain.search import SearchHit, SearchRequest, SearchResponse, SearchType

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


class Neo4jRepositoryProtocol(Protocol):
    """Protocol for Neo4j repository operations."""

    async def search_by_keyword(
        self,
        keyword: str,
        doc_uuids: list[str],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search chunks by keyword in text.

        Args:
            keyword: Keyword to search for
            doc_uuids: Document UUIDs to filter by
            top_k: Maximum results to return

        Returns:
            List of matching chunks with metadata
        """
        ...

    async def search_by_entity(
        self,
        entity_name: str,
        doc_uuids: list[str],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search chunks mentioning an entity.

        Args:
            entity_name: Entity name to search for
            doc_uuids: Document UUIDs to filter by
            top_k: Maximum results to return

        Returns:
            List of chunks mentioning the entity
        """
        ...

    async def search_related(
        self,
        chunk_uuid: str,
        doc_uuids: list[str],
        max_depth: int = 2,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search related chunks by graph traversal.

        Args:
            chunk_uuid: Starting chunk UUID
            doc_uuids: Document UUIDs to filter by
            max_depth: Maximum traversal depth
            top_k: Maximum results to return

        Returns:
            List of related chunks
        """
        ...


# =============================================================================
# Search Service
# =============================================================================


class SearchService:
    """Service for search operations.

    Provides dense, sparse, hybrid, and graph search capabilities with:
    - Automatic query embedding generation
    - ACL-based document filtering
    - Minimum score thresholding
    - Search time tracking
    - Graph-based relationship search

    Example:
        >>> service = SearchService(milvus_repo, embedding_service, acl_service)
        >>> results = await service.dense_search("query", "user1", ["group1"])
    """

    def __init__(
        self,
        milvus_repo: MilvusRepositoryProtocol,
        embedding_service: EmbeddingServiceProtocol,
        acl_service: AclServiceProtocol,
        neo4j_repo: Neo4jRepositoryProtocol | None = None,
    ) -> None:
        """Initialize search service.

        Args:
            milvus_repo: Milvus repository for vector search
            embedding_service: Service for generating embeddings
            acl_service: Service for access control
            neo4j_repo: Neo4j repository for graph search (optional)
        """
        self._milvus_repo = milvus_repo
        self._embedding_service = embedding_service
        self._acl_service = acl_service
        self._neo4j_repo = neo4j_repo

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

    def _preprocess_query(self, query: str) -> str:
        """Preprocess query for better search.

        Currently a passthrough - BGE-M3 handles Korean well.
        Can be extended for:
        - Query expansion
        - Stop word removal
        - Normalization

        Args:
            query: Raw query text

        Returns:
            Preprocessed query
        """
        # BGE-M3 handles Korean tokenization internally
        # Just trim whitespace for now
        return query.strip()

    def _is_valid_sparse_vector(self, sparse_vector: Any) -> bool:
        """Check if sparse vector is valid (non-empty).

        Args:
            sparse_vector: Sparse vector to validate

        Returns:
            True if valid, False otherwise
        """
        if sparse_vector is None:
            return False
        # Handle dict-like sparse vectors
        if hasattr(sparse_vector, "__len__"):
            return len(sparse_vector) > 0
        # Handle scipy sparse arrays
        if hasattr(sparse_vector, "nnz"):
            return sparse_vector.nnz > 0
        return True

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract keywords from query for graph search.

        Simple tokenization - can be enhanced with NLP.
        Handles both English and Korean text.

        Args:
            query: Search query

        Returns:
            List of keywords
        """
        import re

        # Normalize whitespace
        text = re.sub(r"\s+", " ", query.strip())

        # Split by whitespace and punctuation
        tokens = re.split(r"[\s,;:!?()[\]{}]+", text)

        # Common stopwords (English and Korean)
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "to",
            "of",
            "and",
            "in",
            "for",
            "on",
            "with",
            "의",
            "를",
            "을",
            "이",
            "가",
            "은",
            "는",
            "에",
            "에서",
            "로",
            "으로",
            "와",
            "과",
            "도",
            "만",
        }

        keywords = [
            token.lower()
            for token in tokens
            if len(token) >= 2 and token.lower() not in stopwords
        ]

        return keywords

    def _extract_primary_keyword(self, query: str) -> str:
        """Extract primary keyword for graph search.

        Uses the longest keyword as primary.

        Args:
            query: Search query

        Returns:
            Primary keyword
        """
        keywords = self._extract_keywords(query)
        if not keywords:
            return query.strip()

        # Use longest keyword as primary
        return max(keywords, key=len)

    def _format_graph_results(
        self,
        hits: list[dict[str, Any]],
    ) -> list[SearchHit]:
        """Format Neo4j search hits to SearchHit.

        Scores are calculated based on position and path length.

        Args:
            hits: Raw search hits from Neo4j

        Returns:
            List of formatted SearchHit
        """
        results = []
        for i, hit in enumerate(hits):
            # Score based on position and path length
            path_length = hit.get("path_length", 0)
            base_score = 1.0 - (i * 0.05)  # Position penalty
            path_penalty = path_length * 0.1  # Longer paths score lower
            score = max(0.0, base_score - path_penalty)

            results.append(
                SearchHit(
                    chunk_uuid=hit.get("chunk_uuid", ""),
                    doc_uuid=hit.get("doc_uuid", ""),
                    score=score,
                    distance=1.0 - score,
                    chunk_text=hit.get("text_preview"),
                    search_type="graph",
                    metadata={
                        "title": hit.get("title"),
                        "path_length": path_length,
                        "matched_entity": hit.get("matched_entity"),
                        "relationships": hit.get("relationships", []),
                    },
                )
            )
        return results

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

        Uses inner product on sparse embeddings for BM25-style keyword matching.
        BGE-M3 model handles Korean tokenization internally.

        Args:
            query: Search query text
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold
            security_level: Maximum security level for user

        Returns:
            List of search results sorted by relevance

        Example:
            >>> results = await service.sparse_search(
            ...     query="인공지능 기술 문서",
            ...     user_id="user1",
            ...     user_groups=["team-ml"],
            ...     top_k=10,
            ... )
        """
        groups = user_groups or []
        start_time = time.time()

        # 0. Preprocess query
        processed_query = self._preprocess_query(query)
        if not processed_query:
            logger.warning("Empty query after preprocessing")
            return []

        # 1. Get accessible documents
        doc_uuids = await self._get_accessible_doc_uuids(user_id, groups)
        logger.debug(f"User {user_id} has access to {len(doc_uuids)} documents")

        # 2. Generate query embedding
        embeddings = self._encode_query(processed_query)
        if not embeddings or not embeddings.sparse:
            logger.warning("Failed to generate sparse query embedding")
            return []

        query_sparse = embeddings.sparse[0]

        # Validate sparse vector is not empty
        if not self._is_valid_sparse_vector(query_sparse):
            logger.warning("Empty sparse embedding for query")
            return []

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

    async def sparse_search_with_response(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
        security_level: str | None = None,
    ) -> SearchResponse:
        """Execute sparse search and return SearchResponse.

        Convenience method that wraps sparse_search with timing and metadata.

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

        results = await self.sparse_search(
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
            search_types_used=[SearchType.SPARSE],
        )

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

    async def graph_search(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        """Execute graph-based search using Neo4j.

        Searches for chunks based on text content and graph relationships.
        Extracts primary keyword from query for Cypher text matching.

        Args:
            query: Search query text
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold

        Returns:
            List of search results sorted by graph relevance

        Example:
            >>> results = await service.graph_search(
            ...     query="machine learning algorithms",
            ...     user_id="user1",
            ...     user_groups=["team-ml"],
            ...     top_k=10,
            ... )
        """
        if self._neo4j_repo is None:
            logger.warning("Neo4j repository not configured, skipping graph search")
            return []

        groups = user_groups or []
        start_time = time.time()

        # 1. Get accessible documents
        accessible_docs = await self._get_accessible_doc_uuids(user_id, groups)
        logger.debug(f"User {user_id} has access to {len(accessible_docs)} documents")

        if not accessible_docs:
            logger.debug("No accessible documents for user")
            return []

        # 2. Extract keyword
        keyword = self._extract_primary_keyword(query)
        if not keyword:
            logger.warning("No keyword extracted from query")
            return []

        logger.debug(f"Graph search keyword: {keyword}")

        # 3. Execute graph search
        try:
            hits = await self._neo4j_repo.search_by_keyword(
                keyword=keyword,
                doc_uuids=accessible_docs,
                top_k=top_k,
            )
        except Exception as e:
            logger.exception(f"Graph search failed: {e}")
            raise

        # 4. Format and filter results
        results = self._format_graph_results(hits)
        results = self._filter_by_min_score(results, min_score)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"Graph search completed: {len(results)} results in {elapsed_ms:.2f}ms"
        )

        return results

    async def graph_search_by_entity(
        self,
        entity_name: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        """Search chunks by entity name.

        Finds chunks that mention a specific entity via MENTIONS relationship.

        Args:
            entity_name: Entity name to search for
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold

        Returns:
            List of search results

        Example:
            >>> results = await service.graph_search_by_entity(
            ...     entity_name="TensorFlow",
            ...     user_id="user1",
            ...     top_k=10,
            ... )
        """
        if self._neo4j_repo is None:
            logger.warning("Neo4j repository not configured")
            return []

        groups = user_groups or []
        start_time = time.time()

        accessible_docs = await self._get_accessible_doc_uuids(user_id, groups)

        if not accessible_docs:
            return []

        try:
            hits = await self._neo4j_repo.search_by_entity(
                entity_name=entity_name,
                doc_uuids=accessible_docs,
                top_k=top_k,
            )
        except Exception as e:
            logger.exception(f"Entity search failed: {e}")
            raise

        results = self._format_graph_results(hits)
        results = self._filter_by_min_score(results, min_score)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"Entity search completed: {len(results)} results in {elapsed_ms:.2f}ms"
        )

        return results

    async def graph_search_with_response(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> SearchResponse:
        """Execute graph search and return SearchResponse.

        Convenience method that wraps graph_search with timing and metadata.

        Args:
            query: Search query text
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold

        Returns:
            SearchResponse with results and metadata
        """
        start_time = time.time()

        results = await self.graph_search(
            query=query,
            user_id=user_id,
            user_groups=user_groups,
            top_k=top_k,
            min_score=min_score,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            results=results,
            total=len(results),
            search_time_ms=elapsed_ms,
            search_types_used=[SearchType.GRAPH],
        )

    # =========================================================================
    # Unified Search (Hybrid with RRF)
    # =========================================================================

    # Default weights for different search types
    DEFAULT_WEIGHTS: dict[SearchType, float] = {
        SearchType.DENSE: 1.0,
        SearchType.SPARSE: 0.8,
        SearchType.GRAPH: 0.6,
    }

    def _calculate_rrf_scores(
        self,
        results_by_type: dict[SearchType, list[SearchHit]],
        k: int = 60,
    ) -> dict[str, dict[str, Any]]:
        """Calculate RRF scores for all results.

        RRF(d) = Σ 1 / (k + rank_i(d))

        Args:
            results_by_type: Results grouped by search type
            k: RRF constant (default 60)

        Returns:
            Dict of chunk_uuid to merged result info
        """
        merged: dict[str, dict[str, Any]] = {}

        for search_type, results in results_by_type.items():
            for rank, result in enumerate(results, start=1):
                chunk_uuid = result.chunk_uuid
                rrf_contribution = 1 / (k + rank)

                if chunk_uuid in merged:
                    merged[chunk_uuid]["rrf_score"] += rrf_contribution
                    merged[chunk_uuid]["sources"][search_type] = {
                        "score": result.score,
                        "rank": rank,
                    }
                    # Keep the best chunk_text if not already set
                    if not merged[chunk_uuid].get("chunk_text") and result.chunk_text:
                        merged[chunk_uuid]["chunk_text"] = result.chunk_text
                else:
                    merged[chunk_uuid] = {
                        "chunk_uuid": chunk_uuid,
                        "doc_uuid": result.doc_uuid,
                        "rrf_score": rrf_contribution,
                        "chunk_text": result.chunk_text,
                        "sources": {
                            search_type: {
                                "score": result.score,
                                "rank": rank,
                            }
                        },
                        "metadata": result.metadata.copy() if result.metadata else {},
                    }

        return merged

    def _merge_search_results(
        self,
        results_by_type: dict[SearchType, list[SearchHit]],
        top_k: int,
        weights: dict[SearchType, float] | None = None,
        rrf_k: int = 60,
    ) -> list[SearchHit]:
        """Merge results from multiple search types using RRF.

        Args:
            results_by_type: Results grouped by search type
            top_k: Maximum results to return
            weights: Optional weights per search type
            rrf_k: RRF constant k

        Returns:
            Merged and sorted SearchHit list
        """
        if not results_by_type:
            return []

        # Apply weights by adjusting effective ranks
        weighted_results: dict[SearchType, list[SearchHit]] = {}
        for search_type, results in results_by_type.items():
            weight = 1.0
            if weights:
                weight = weights.get(search_type, 1.0)

            # Create weighted copies
            weighted = []
            for r in results:
                weighted_hit = SearchHit(
                    chunk_uuid=r.chunk_uuid,
                    doc_uuid=r.doc_uuid,
                    score=r.score * weight,
                    distance=r.distance,
                    chunk_text=r.chunk_text,
                    section_path=r.section_path,
                    search_type=r.search_type,
                    metadata=r.metadata.copy() if r.metadata else {},
                )
                weighted.append(weighted_hit)
            weighted_results[search_type] = weighted

        # Calculate RRF scores
        merged = self._calculate_rrf_scores(weighted_results, k=rrf_k)

        # Sort by RRF score and take top_k
        sorted_items = sorted(
            merged.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )[:top_k]

        # Convert to SearchHit
        final_results = []
        for item in sorted_items:
            hit = SearchHit(
                chunk_uuid=item["chunk_uuid"],
                doc_uuid=item["doc_uuid"],
                score=item["rrf_score"],
                distance=1.0 - item["rrf_score"],
                chunk_text=item.get("chunk_text", ""),
                search_type="hybrid",
                metadata={
                    "sources": item["sources"],
                    **item.get("metadata", {}),
                },
            )
            final_results.append(hit)

        return final_results

    async def unified_search(
        self,
        request: SearchRequest,
    ) -> SearchResponse:
        """Execute unified search combining multiple search types.

        Runs Dense, Sparse, and Graph searches in parallel,
        then merges results using RRF (Reciprocal Rank Fusion).

        Args:
            request: Search request parameters

        Returns:
            SearchResponse with merged results

        Example:
            >>> request = SearchRequest(
            ...     query="machine learning",
            ...     user_id="user1",
            ...     search_types=[SearchType.DENSE, SearchType.SPARSE],
            ... )
            >>> response = await service.unified_search(request)
        """
        import asyncio

        start_time = time.time()

        # Determine which search types to use
        search_types = request.search_types or [
            SearchType.DENSE,
            SearchType.SPARSE,
            SearchType.GRAPH,
        ]

        logger.info(f"Unified search with types: {[t.value for t in search_types]}")

        # Build search tasks
        tasks: dict[SearchType, Any] = {}

        if SearchType.DENSE in search_types:
            tasks[SearchType.DENSE] = self.dense_search(
                query=request.query,
                user_id=request.user_id,
                user_groups=request.user_groups,
                top_k=request.top_k * 2,  # Over-fetch for merging
                min_score=0.0,  # Apply min_score after merging
            )

        if SearchType.SPARSE in search_types:
            tasks[SearchType.SPARSE] = self.sparse_search(
                query=request.query,
                user_id=request.user_id,
                user_groups=request.user_groups,
                top_k=request.top_k * 2,
                min_score=0.0,
            )

        if SearchType.GRAPH in search_types:
            tasks[SearchType.GRAPH] = self.graph_search(
                query=request.query,
                user_id=request.user_id,
                user_groups=request.user_groups,
                top_k=request.top_k * 2,
                min_score=0.0,
            )

        if not tasks:
            logger.warning("No search types specified")
            return SearchResponse(
                results=[],
                total=0,
                search_time_ms=(time.time() - start_time) * 1000,
                search_types_used=[],
            )

        # Execute in parallel
        task_list = list(tasks.values())
        task_keys = list(tasks.keys())

        results_list = await asyncio.gather(*task_list, return_exceptions=True)

        # Process results
        results_by_type: dict[SearchType, list[SearchHit]] = {}
        errors: list[str] = []

        for search_type, result in zip(task_keys, results_list, strict=False):
            if isinstance(result, Exception):
                logger.error(f"{search_type.value} search failed: {result}")
                errors.append(f"{search_type.value}: {result!s}")
            else:
                results_by_type[search_type] = result

        # Merge results using RRF
        merged_results = self._merge_search_results(
            results_by_type,
            top_k=request.top_k,
        )

        # Apply min_score filter after merging
        if request.min_score > 0:
            merged_results = [r for r in merged_results if r.score >= request.min_score]

        # Calculate search time
        search_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Unified search completed: {len(merged_results)} results "
            f"in {search_time_ms:.2f}ms"
        )

        return SearchResponse(
            results=merged_results,
            total=len(merged_results),
            search_time_ms=search_time_ms,
            search_types_used=list(results_by_type.keys()),
        )

    async def unified_search_with_weights(
        self,
        request: SearchRequest,
        weights: dict[SearchType, float] | None = None,
    ) -> SearchResponse:
        """Execute unified search with custom weights.

        Args:
            request: Search request parameters
            weights: Custom weights per search type (default: DEFAULT_WEIGHTS)

        Returns:
            SearchResponse with weighted merged results
        """
        import asyncio

        start_time = time.time()
        effective_weights = weights or self.DEFAULT_WEIGHTS

        search_types = request.search_types or list(effective_weights.keys())

        # Filter weights for selected types
        active_weights = {t: effective_weights.get(t, 1.0) for t in search_types}

        logger.info(
            f"Unified search with weights: "
            f"{[(t.value, w) for t, w in active_weights.items()]}"
        )

        # Build and execute search tasks
        tasks: dict[SearchType, Any] = {}
        if SearchType.DENSE in search_types:
            tasks[SearchType.DENSE] = self.dense_search(
                request.query,
                request.user_id,
                request.user_groups,
                request.top_k * 2,
            )
        if SearchType.SPARSE in search_types:
            tasks[SearchType.SPARSE] = self.sparse_search(
                request.query,
                request.user_id,
                request.user_groups,
                request.top_k * 2,
            )
        if SearchType.GRAPH in search_types:
            tasks[SearchType.GRAPH] = self.graph_search(
                request.query,
                request.user_id,
                request.user_groups,
                request.top_k * 2,
            )

        if not tasks:
            return SearchResponse(
                results=[],
                total=0,
                search_time_ms=(time.time() - start_time) * 1000,
                search_types_used=[],
            )

        results_list = await asyncio.gather(*tasks.values(), return_exceptions=True)

        results_by_type: dict[SearchType, list[SearchHit]] = {}
        for search_type, result in zip(tasks.keys(), results_list, strict=False):
            if not isinstance(result, Exception):
                results_by_type[search_type] = result

        # Merge with weights
        merged = self._merge_search_results(
            results_by_type,
            top_k=request.top_k,
            weights=active_weights,
        )

        if request.min_score > 0:
            merged = [r for r in merged if r.score >= request.min_score]

        search_time_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            results=merged,
            total=len(merged),
            search_time_ms=search_time_ms,
            search_types_used=list(results_by_type.keys()),
        )

    def suggest_weights(self, query: str) -> dict[SearchType, float]:
        """Suggest weights based on query characteristics.

        Simple heuristic based on query length and keywords.

        Args:
            query: Search query

        Returns:
            Suggested weights per search type
        """
        words = query.split()

        if len(words) <= 2:
            # Short query: prefer keyword match (sparse)
            return {
                SearchType.DENSE: 0.6,
                SearchType.SPARSE: 1.0,
                SearchType.GRAPH: 0.8,
            }
        elif any(word in query.lower() for word in ["similar", "like", "related", "유사"]):
            # Semantic query: prefer dense
            return {
                SearchType.DENSE: 1.0,
                SearchType.SPARSE: 0.5,
                SearchType.GRAPH: 0.7,
            }
        else:
            # Balanced
            return self.DEFAULT_WEIGHTS

    async def search(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        search_types: list[SearchType] | None = None,
        min_score: float = 0.0,
    ) -> SearchResponse:
        """Convenience method for unified search.

        Args:
            query: Search query
            user_id: User identifier
            user_groups: User's group memberships
            top_k: Maximum results
            search_types: Types of search to perform
            min_score: Minimum score threshold

        Returns:
            SearchResponse

        Example:
            >>> response = await service.search(
            ...     query="machine learning",
            ...     user_id="user1",
            ...     top_k=10,
            ... )
        """
        request = SearchRequest(
            query=query,
            user_id=user_id,
            user_groups=user_groups or [],
            top_k=top_k,
            search_types=search_types
            or [SearchType.DENSE, SearchType.SPARSE, SearchType.GRAPH],
            min_score=min_score,
        )
        return await self.unified_search(request)


# =============================================================================
# Singleton Factory
# =============================================================================

_service: SearchService | None = None


def get_search_service(
    milvus_repo: MilvusRepositoryProtocol | None = None,
    embedding_service: EmbeddingServiceProtocol | None = None,
    acl_service: AclServiceProtocol | None = None,
    neo4j_repo: Neo4jRepositoryProtocol | None = None,
) -> SearchService:
    """Get or create search service singleton.

    Args:
        milvus_repo: Milvus repository (required on first call)
        embedding_service: Embedding service (required on first call)
        acl_service: ACL service (required on first call)
        neo4j_repo: Neo4j repository for graph search (optional)

    Returns:
        SearchService instance

    Raises:
        ValueError: If dependencies not provided on first call
    """
    global _service
    if _service is None:
        if milvus_repo is None or embedding_service is None or acl_service is None:
            raise ValueError("All dependencies required for first initialization")
        _service = SearchService(
            milvus_repo, embedding_service, acl_service, neo4j_repo
        )
    return _service


def close_search_service() -> None:
    """Close the search service singleton."""
    global _service
    _service = None


def reset_search_service() -> None:
    """Reset search service singleton (for testing)."""
    global _service
    _service = None
