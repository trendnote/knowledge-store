"""Milvus repository for vector operations.

This module provides a data access layer for Milvus vector database:
- Insert/Delete chunk vectors
- Dense search (semantic similarity)
- Sparse search (keyword matching)
- Hybrid search (combined dense + sparse with RRF)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from scipy.sparse import csr_array

from src.domain.search import MilvusChunk, SearchHit

if TYPE_CHECKING:
    from src.infrastructure.database.milvus import MilvusClient


class MilvusRepository:
    """Milvus data access layer for vector operations.

    This repository provides:
    - Vector insert/delete operations
    - Dense/Sparse/Hybrid search with ACL filtering
    - Filter expression building for security

    Example:
        >>> from src.infrastructure.database import get_milvus_client
        >>> from src.repositories.milvus import get_milvus_repository
        >>>
        >>> client = get_milvus_client()
        >>> client.connect()
        >>> repo = get_milvus_repository(client)
        >>>
        >>> # Search
        >>> results = await repo.dense_search(
        ...     query_vector=[0.1] * 1024,
        ...     doc_uuids=["doc-1", "doc-2"],
        ...     top_k=10,
        ... )
    """

    # Output fields for search
    OUTPUT_FIELDS = [
        "chunk_uuid",
        "doc_uuid",
        "chunk_text",
        "section_path",
        "security_level",
        "allowed_groups",
    ]

    def __init__(self, client: MilvusClient) -> None:
        """Initialize repository.

        Args:
            client: Milvus client instance
        """
        self._client = client

    @property
    def client(self) -> MilvusClient:
        """Get underlying Milvus client."""
        return self._client

    # =========================================================================
    # Insert/Delete Operations
    # =========================================================================

    async def insert_chunks(self, chunks: list[MilvusChunk]) -> list[str]:
        """Insert chunks into Milvus.

        Args:
            chunks: List of chunks to insert

        Returns:
            List of inserted chunk UUIDs
        """
        if not chunks:
            return []

        # Prepare data in row format for Milvus
        data: list[dict[str, Any]] = []
        current_time = int(time.time())

        for chunk in chunks:
            row: dict[str, Any] = {
                "chunk_uuid": chunk.chunk_uuid,
                "doc_uuid": chunk.doc_uuid,
                "dense_embedding": chunk.dense_embedding,
                "sparse_embedding": chunk.sparse_embedding,
                "chunk_text": chunk.chunk_text[:8000],  # Max length limit
                "section_path": chunk.section_path or "",
                "security_level": chunk.security_level,
                "allowed_groups": chunk.allowed_groups or [],
                "created_at": chunk.created_at or current_time,
            }
            data.append(row)

        # Insert using async wrapper
        result = await self._client.insert_async(data)

        return result

    async def delete_by_chunk_uuids(self, chunk_uuids: list[str]) -> int:
        """Delete chunks by their UUIDs.

        Args:
            chunk_uuids: List of chunk UUIDs to delete

        Returns:
            Number of deleted entities
        """
        if not chunk_uuids:
            return 0

        # Build filter expression
        uuids_str = ", ".join(f'"{uuid}"' for uuid in chunk_uuids)
        expr = f"chunk_uuid in [{uuids_str}]"

        result = await self._client.delete_async(expr)
        return result

    async def delete_by_doc_uuid(self, doc_uuid: str) -> int:
        """Delete all chunks for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Number of deleted entities
        """
        expr = f'doc_uuid == "{doc_uuid}"'
        result = await self._client.delete_async(expr)
        return result

    async def get_chunk_count(self, doc_uuid: str | None = None) -> int:
        """Get chunk count.

        Args:
            doc_uuid: Optional document UUID to filter

        Returns:
            Number of chunks

        Note:
            When doc_uuid is provided, this performs a search which
            may not be accurate for counting. For total count, use
            without doc_uuid.
        """
        if doc_uuid:
            # Use query with filter to count
            # Note: This is a workaround since Milvus doesn't have direct count with filter
            results = await self._client.dense_search_async(
                query_vector=[0.0] * 1024,  # Dummy vector
                limit=10000,  # Max reasonable limit
                expr=f'doc_uuid == "{doc_uuid}"',
                output_fields=["chunk_uuid"],
            )
            return len(results)

        # Total count using num_entities
        return await self._client.count_async()

    # =========================================================================
    # Filter Expression Building
    # =========================================================================

    def build_filter_expr(
        self,
        doc_uuids: list[str] | None = None,
        security_level: str | None = None,
    ) -> str | None:
        """Build filter expression for search.

        Args:
            doc_uuids: Allowed document UUIDs (ACL filtered)
            security_level: Maximum security level for user

        Returns:
            Filter expression string or None

        Note:
            Security level hierarchy: public < internal < confidential
            - public: can only see public
            - internal: can see public and internal
            - confidential: can see all
        """
        conditions: list[str] = []

        if doc_uuids is not None:
            if not doc_uuids:
                # Empty list means no access
                return 'doc_uuid == "__no_access__"'
            uuids_str = ", ".join(f'"{uuid}"' for uuid in doc_uuids)
            conditions.append(f"doc_uuid in [{uuids_str}]")

        if security_level:
            # Security level hierarchy
            if security_level == "public":
                conditions.append('security_level == "public"')
            elif security_level == "internal":
                conditions.append('security_level in ["public", "internal"]')
            # confidential can see all - no filter needed

        if not conditions:
            return None

        return " and ".join(conditions)

    # =========================================================================
    # Search Operations
    # =========================================================================

    async def dense_search(
        self,
        query_vector: list[float],
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        security_level: str | None = None,
    ) -> list[SearchHit]:
        """Search by dense vector (semantic similarity).

        Uses COSINE similarity with HNSW index for fast approximate
        nearest neighbor search.

        Args:
            query_vector: Query embedding (1024 dim for BGE-M3)
            doc_uuids: Allowed document UUIDs (ACL filtered)
            top_k: Maximum number of results
            security_level: Maximum security level for user

        Returns:
            List of search hits ordered by similarity
        """
        filter_expr = self.build_filter_expr(doc_uuids, security_level)

        results = await self._client.dense_search_async(
            query_vector=query_vector,
            limit=top_k,
            expr=filter_expr,
            output_fields=self.OUTPUT_FIELDS,
        )

        return [SearchHit.from_milvus_hit(hit, search_type="dense") for hit in results]

    async def sparse_search(
        self,
        query_sparse: csr_array,
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        security_level: str | None = None,
    ) -> list[SearchHit]:
        """Search by sparse vector (keyword matching).

        Uses Inner Product with SPARSE_INVERTED_INDEX for BM25-like
        keyword matching.

        Args:
            query_sparse: Sparse query vector (scipy.sparse.csr_array)
            doc_uuids: Allowed document UUIDs (ACL filtered)
            top_k: Maximum number of results
            security_level: Maximum security level for user

        Returns:
            List of search hits ordered by relevance
        """
        filter_expr = self.build_filter_expr(doc_uuids, security_level)

        results = await self._client.sparse_search_async(
            query_sparse=query_sparse,
            limit=top_k,
            expr=filter_expr,
            output_fields=self.OUTPUT_FIELDS,
        )

        return [SearchHit.from_milvus_hit(hit, search_type="sparse") for hit in results]

    async def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse: csr_array,
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        security_level: str | None = None,
        rrf_k: int = 60,
    ) -> list[SearchHit]:
        """Hybrid search combining dense and sparse vectors.

        Uses RRF (Reciprocal Rank Fusion) to combine results from
        dense and sparse searches for better recall and precision.

        RRF Score = sum(1 / (k + rank_i)) for each retrieval method

        Args:
            query_dense: Dense embedding (1024 dim)
            query_sparse: Sparse vector (scipy.sparse.csr_array)
            doc_uuids: Allowed document UUIDs (ACL filtered)
            top_k: Maximum number of results
            security_level: Maximum security level for user
            rrf_k: RRF parameter k (default: 60, higher = less aggressive)

        Returns:
            List of search hits (merged and reranked)
        """
        filter_expr = self.build_filter_expr(doc_uuids, security_level)

        results = await self._client.hybrid_search_async(
            query_dense=query_dense,
            query_sparse=query_sparse,
            limit=top_k,
            expr=filter_expr,
            output_fields=self.OUTPUT_FIELDS,
            rrf_k=rrf_k,
        )

        return [SearchHit.from_milvus_hit(hit, search_type="hybrid") for hit in results]

    async def get_by_chunk_uuid(self, chunk_uuid: str) -> SearchHit | None:
        """Get chunk by UUID.

        Args:
            chunk_uuid: Chunk UUID to retrieve

        Returns:
            SearchHit or None if not found
        """
        results = await self._client.dense_search_async(
            query_vector=[0.0] * 1024,  # Dummy vector
            limit=1,
            expr=f'chunk_uuid == "{chunk_uuid}"',
            output_fields=self.OUTPUT_FIELDS,
        )

        if not results:
            return None

        return SearchHit.from_milvus_hit(results[0])


# =============================================================================
# Singleton Factory
# =============================================================================

_repository: MilvusRepository | None = None


def get_milvus_repository(client: MilvusClient | None = None) -> MilvusRepository:
    """Get or create Milvus repository singleton.

    Args:
        client: Milvus client (required on first call,
                or auto-loaded from infrastructure)

    Returns:
        MilvusRepository instance
    """
    global _repository
    if _repository is None:
        if client is None:
            from src.infrastructure.database import get_milvus_client

            client = get_milvus_client()
        _repository = MilvusRepository(client)
    return _repository


def reset_milvus_repository() -> None:
    """Reset the repository singleton (for testing)."""
    global _repository
    _repository = None
