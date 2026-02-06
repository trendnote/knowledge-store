"""Milvus vector database client.

This module provides a client for Milvus vector database with support for:
- Dense vector search (HNSW with COSINE similarity)
- Sparse vector search (SPARSE_INVERTED_INDEX with IP)
- Hybrid search (RRF reranking)

Example:
    >>> from src.infrastructure.database import get_milvus_client
    >>> client = get_milvus_client()
    >>> client.connect()
    >>> results = await client.dense_search_async(query_vector, limit=10)
    >>> client.disconnect()
"""

from __future__ import annotations

import asyncio
from typing import Any

from pymilvus import Collection, connections, utility
from scipy.sparse import csr_array

from src.config import MilvusSettings


class MilvusClient:
    """Milvus client for vector operations.

    This client provides:
    - Connection management (connect/disconnect)
    - Insert/Delete/Flush operations
    - Dense/Sparse/Hybrid search
    - Async wrappers for all operations

    Note:
        pymilvus is a synchronous SDK. All async methods use
        run_in_executor for non-blocking operation.
    """

    def __init__(self, settings: MilvusSettings) -> None:
        """Initialize Milvus client.

        Args:
            settings: Milvus connection settings
        """
        self._settings = settings
        self._collection: Collection | None = None
        self._connected = False
        self._alias = "default"

    @property
    def collection(self) -> Collection:
        """Get collection.

        Returns:
            Collection instance

        Raises:
            RuntimeError: If client is not connected
        """
        if self._collection is None:
            raise RuntimeError("MilvusClient is not connected. Call connect() first.")
        return self._collection

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    def connect(self) -> None:
        """Connect to Milvus and load collection.

        This method is idempotent - calling it multiple times
        will not create additional connections.

        Raises:
            RuntimeError: If collection does not exist
        """
        if self._connected:
            return

        connections.connect(
            alias=self._alias,
            host=self._settings.host,
            port=str(self._settings.port),
            timeout=30,
        )

        # Check if collection exists
        if not utility.has_collection(self._settings.collection, using=self._alias):
            connections.disconnect(self._alias)
            raise RuntimeError(
                f"Collection '{self._settings.collection}' does not exist. "
                "Run init_milvus.py first."
            )

        # Load collection into memory
        self._collection = Collection(self._settings.collection, using=self._alias)
        self._collection.load()
        self._connected = True

    async def connect_async(self) -> None:
        """Async wrapper for connect."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.connect)

    def disconnect(self) -> None:
        """Disconnect from Milvus.

        This method is idempotent - calling it multiple times is safe.
        """
        if self._connected:
            if self._collection is not None:
                self._collection.release()
                self._collection = None
            connections.disconnect(self._alias)
            self._connected = False

    def ping(self) -> bool:
        """Check if Milvus is reachable.

        Returns:
            True if Milvus is accessible, False otherwise
        """
        try:
            if not self._connected:
                return False
            utility.list_collections(using=self._alias)
            return True
        except Exception:
            return False

    async def ping_async(self) -> bool:
        """Async wrapper for ping."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.ping)

    # =========================================================================
    # Insert/Delete/Flush Operations
    # =========================================================================

    def insert(self, data: list[dict[str, Any]]) -> list[str]:
        """Insert data into collection.

        Args:
            data: List of row dictionaries with field names as keys

        Returns:
            List of inserted primary keys (chunk_uuids)

        Example:
            >>> data = [
            ...     {
            ...         "chunk_uuid": "uuid1",
            ...         "doc_uuid": "doc1",
            ...         "dense_embedding": [0.1] * 1024,
            ...         "sparse_embedding": sparse_vector,  # scipy.sparse.csr_array
            ...         ...
            ...     }
            ... ]
            >>> pks = client.insert(data)
        """
        result = self.collection.insert(data)
        self.collection.flush()
        return list(result.primary_keys)

    async def insert_async(self, data: list[dict[str, Any]]) -> list[str]:
        """Async wrapper for insert."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.insert, data)

    def delete(self, expr: str) -> int:
        """Delete entities matching expression.

        Args:
            expr: Boolean expression (e.g., 'chunk_uuid == "uuid1"')

        Returns:
            Number of deleted entities

        Example:
            >>> count = client.delete('chunk_uuid == "uuid1"')
            >>> count = client.delete('doc_uuid == "doc1"')
        """
        result = self.collection.delete(expr)
        self.collection.flush()
        return result.delete_count

    async def delete_async(self, expr: str) -> int:
        """Async wrapper for delete."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.delete, expr)

    def flush(self) -> None:
        """Flush data to disk."""
        self.collection.flush()

    async def flush_async(self) -> None:
        """Async wrapper for flush."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.flush)

    def count(self) -> int:
        """Get number of entities in collection.

        Returns:
            Number of entities
        """
        return self.collection.num_entities

    async def count_async(self) -> int:
        """Async wrapper for count."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.count)

    # =========================================================================
    # Search Operations
    # =========================================================================

    def dense_search(
        self,
        query_vector: list[float],
        limit: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
        ef: int = 64,
    ) -> list[dict[str, Any]]:
        """Search by dense vector (COSINE similarity).

        Args:
            query_vector: Query embedding (1024 dim for BGE-M3)
            limit: Maximum number of results
            expr: Filter expression (e.g., 'security_level == "public"')
            output_fields: Fields to return in results
            ef: HNSW search parameter (higher = more accurate but slower)

        Returns:
            List of search results with scores and fields

        Example:
            >>> results = client.dense_search(
            ...     query_vector=[0.1] * 1024,
            ...     limit=10,
            ...     expr='security_level == "public"',
            ...     output_fields=["chunk_uuid", "chunk_text"]
            ... )
        """
        search_params = {
            "metric_type": "COSINE",
            "params": {"ef": ef},
        }

        if output_fields is None:
            output_fields = ["chunk_uuid", "doc_uuid", "chunk_text", "section_path"]

        results = self.collection.search(
            data=[query_vector],
            anns_field="dense_embedding",
            param=search_params,
            limit=limit,
            expr=expr,
            output_fields=output_fields,
        )

        return self._format_search_results(results[0])

    async def dense_search_async(
        self,
        query_vector: list[float],
        limit: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
        ef: int = 64,
    ) -> list[dict[str, Any]]:
        """Async wrapper for dense_search."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.dense_search(query_vector, limit, expr, output_fields, ef),
        )

    def sparse_search(
        self,
        query_sparse: csr_array,
        limit: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search by sparse vector (Inner Product).

        Args:
            query_sparse: Sparse query vector (scipy.sparse.csr_array)
            limit: Maximum number of results
            expr: Filter expression
            output_fields: Fields to return in results

        Returns:
            List of search results with scores and fields

        Example:
            >>> from scipy.sparse import csr_array
            >>> sparse_vector = csr_array(
            ...     ([0.5, 0.3], ([0, 0], [100, 200])),
            ...     shape=(1, 30000)
            ... )
            >>> results = client.sparse_search(sparse_vector, limit=10)
        """
        search_params = {
            "metric_type": "IP",
            "params": {},
        }

        if output_fields is None:
            output_fields = ["chunk_uuid", "doc_uuid", "chunk_text", "section_path"]

        results = self.collection.search(
            data=[query_sparse],
            anns_field="sparse_embedding",
            param=search_params,
            limit=limit,
            expr=expr,
            output_fields=output_fields,
        )

        return self._format_search_results(results[0])

    async def sparse_search_async(
        self,
        query_sparse: csr_array,
        limit: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Async wrapper for sparse_search."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.sparse_search(query_sparse, limit, expr, output_fields),
        )

    def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse: csr_array,
        limit: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
        rrf_k: int = 60,
        ef: int = 64,
    ) -> list[dict[str, Any]]:
        """Hybrid search combining dense and sparse vectors.

        Uses RRF (Reciprocal Rank Fusion) to combine results from
        dense and sparse searches.

        Args:
            query_dense: Dense embedding (1024 dim)
            query_sparse: Sparse vector (scipy.sparse.csr_array)
            limit: Maximum number of results
            expr: Filter expression
            output_fields: Fields to return in results
            rrf_k: RRF parameter k (default: 60)
            ef: HNSW search parameter

        Returns:
            List of merged search results

        Example:
            >>> results = client.hybrid_search(
            ...     query_dense=[0.1] * 1024,
            ...     query_sparse=sparse_vector,
            ...     limit=10,
            ...     expr='security_level in ["public", "internal"]'
            ... )
        """
        from pymilvus import AnnSearchRequest, RRFRanker

        if output_fields is None:
            output_fields = ["chunk_uuid", "doc_uuid", "chunk_text", "section_path"]

        # Dense search request
        dense_req = AnnSearchRequest(
            data=[query_dense],
            anns_field="dense_embedding",
            param={"metric_type": "COSINE", "params": {"ef": ef}},
            limit=limit,
            expr=expr,
        )

        # Sparse search request
        sparse_req = AnnSearchRequest(
            data=[query_sparse],
            anns_field="sparse_embedding",
            param={"metric_type": "IP"},
            limit=limit,
            expr=expr,
        )

        # RRF (Reciprocal Rank Fusion) ranker
        ranker = RRFRanker(k=rrf_k)

        results = self.collection.hybrid_search(
            reqs=[dense_req, sparse_req],
            rerank=ranker,
            limit=limit,
            output_fields=output_fields,
        )

        return self._format_search_results(results[0])

    async def hybrid_search_async(
        self,
        query_dense: list[float],
        query_sparse: csr_array,
        limit: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
        rrf_k: int = 60,
        ef: int = 64,
    ) -> list[dict[str, Any]]:
        """Async wrapper for hybrid_search."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.hybrid_search(
                query_dense, query_sparse, limit, expr, output_fields, rrf_k, ef
            ),
        )

    def _format_search_results(self, hits: Any) -> list[dict[str, Any]]:
        """Format Milvus search hits to dict list.

        Args:
            hits: Milvus search hits

        Returns:
            List of result dictionaries
        """
        results = []
        for hit in hits:
            result: dict[str, Any] = {
                "id": hit.id,
                "score": hit.score,
                "distance": hit.distance,
            }
            # Add output fields from entity
            if hasattr(hit, "entity"):
                for key, value in hit.entity.items():
                    result[key] = value
            results.append(result)
        return results


# =============================================================================
# Singleton Factory
# =============================================================================

_client: MilvusClient | None = None


def get_milvus_client(settings: MilvusSettings | None = None) -> MilvusClient:
    """Get or create Milvus client singleton.

    Args:
        settings: Milvus settings (required on first call,
                  or auto-loaded from environment)

    Returns:
        MilvusClient instance
    """
    global _client
    if _client is None:
        if settings is None:
            from src.config import get_settings

            settings = get_settings().milvus
        _client = MilvusClient(settings)
    return _client


def close_milvus_client() -> None:
    """Close the Milvus client singleton."""
    global _client
    if _client is not None:
        _client.disconnect()
        _client = None


def reset_milvus_client() -> None:
    """Reset the Milvus client singleton (for testing)."""
    global _client
    _client = None
