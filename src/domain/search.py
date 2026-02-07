"""Search-related domain models.

This module provides domain models for vector search operations:
- SearchType: Type of search operation
- MilvusChunk: Data for Milvus insertion
- SearchHit: Search result representation
- SearchRequest: Search request parameters
- SearchResponse: Search response with results
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SearchType(str, Enum):
    """Type of search performed.

    Attributes:
        DENSE: Semantic similarity search using dense embeddings
        SPARSE: Keyword matching search using sparse embeddings
        GRAPH: Graph-based search through Neo4j
        HYBRID: Combined dense + sparse search with RRF fusion
    """

    DENSE = "dense"
    SPARSE = "sparse"
    GRAPH = "graph"
    HYBRID = "hybrid"


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response.

        Returns:
            Dictionary representation
        """
        return {
            "chunk_uuid": self.chunk_uuid,
            "doc_uuid": self.doc_uuid,
            "score": self.score,
            "distance": self.distance,
            "chunk_text": self.chunk_text,
            "section_path": self.section_path,
            "search_type": self.search_type,
            "metadata": self.metadata,
        }


@dataclass
class SearchRequest:
    """Search request parameters.

    Attributes:
        query: Search query text
        user_id: User identifier for ACL
        user_groups: User's group memberships
        top_k: Maximum results to return
        search_types: Types of search to perform
        min_score: Minimum score threshold
        include_chunk_text: Whether to include full chunk text
    """

    query: str
    user_id: str
    user_groups: list[str] = field(default_factory=list)
    top_k: int = 10
    search_types: list[SearchType] = field(
        default_factory=lambda: [SearchType.DENSE]
    )
    min_score: float = 0.0
    include_chunk_text: bool = True


@dataclass
class SearchResponse:
    """Search response with results.

    Attributes:
        results: List of search hits
        total: Total number of results
        search_time_ms: Search execution time in milliseconds
        search_types_used: Types of search that were executed
    """

    results: list[SearchHit]
    total: int
    search_time_ms: float
    search_types_used: list[SearchType] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response.

        Returns:
            Dictionary representation
        """
        return {
            "results": [r.to_dict() for r in self.results],
            "total": self.total,
            "search_time_ms": self.search_time_ms,
            "search_types_used": [t.value for t in self.search_types_used],
        }
