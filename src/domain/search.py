"""Search-related domain models.

This module provides domain models for vector search operations:
- MilvusChunk: Data for Milvus insertion
- SearchHit: Search result representation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MilvusChunk:
    """Chunk data for Milvus insertion.

    Attributes:
        chunk_uuid: Unique identifier for the chunk
        doc_uuid: Document UUID this chunk belongs to
        dense_embedding: Dense vector (1024 dim for BGE-M3)
        sparse_embedding: Sparse vector as scipy.sparse.csr_array
        chunk_text: Text content of the chunk
        section_path: Section path in document (optional)
        security_level: Security classification (public/internal/confidential)
        allowed_groups: Groups allowed to access this chunk
        created_at: Unix timestamp of creation
    """

    chunk_uuid: str
    doc_uuid: str
    dense_embedding: list[float]
    sparse_embedding: Any  # scipy.sparse.csr_array
    chunk_text: str
    section_path: str | None = None
    security_level: str = "internal"
    allowed_groups: list[str] = field(default_factory=list)
    created_at: int | None = None


@dataclass
class SearchHit:
    """Search result hit.

    Attributes:
        chunk_uuid: Chunk identifier
        doc_uuid: Document identifier
        score: Similarity/relevance score
        distance: Distance metric
        chunk_text: Text content of the chunk
        section_path: Section path in document
        search_type: Type of search (dense/sparse/hybrid)
        metadata: Additional metadata from Milvus
    """

    chunk_uuid: str
    doc_uuid: str
    score: float
    distance: float
    chunk_text: str
    section_path: str | None = None
    search_type: str = "dense"  # dense, sparse, hybrid
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_milvus_hit(cls, hit: dict[str, Any], search_type: str = "dense") -> SearchHit:
        """Create SearchHit from Milvus search result.

        Args:
            hit: Dictionary from Milvus search result
            search_type: Type of search performed

        Returns:
            SearchHit instance
        """
        return cls(
            chunk_uuid=hit.get("chunk_uuid") or hit.get("id", ""),
            doc_uuid=hit.get("doc_uuid", ""),
            score=hit.get("score", 0.0),
            distance=hit.get("distance", 0.0),
            chunk_text=hit.get("chunk_text", ""),
            section_path=hit.get("section_path"),
            search_type=search_type,
            metadata={
                "security_level": hit.get("security_level"),
                "allowed_groups": hit.get("allowed_groups"),
            },
        )
