"""Search API schemas.

This module provides Pydantic schemas for search API:
- SearchTypeEnum: Search type enumeration for API
- SearchRequestSchema: Request schema with validation
- SearchResultSchema: Single search result
- SearchResponseSchema: Response with results and metadata
- SearchErrorSchema: Error response format
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SearchTypeEnum(str, Enum):
    """Search type enum for API.

    Attributes:
        DENSE: Semantic similarity search
        SPARSE: Keyword matching search
        GRAPH: Graph relationship search
        HYBRID: Combined search with RRF fusion
    """

    DENSE = "dense"
    SPARSE = "sparse"
    GRAPH = "graph"
    HYBRID = "hybrid"


class SearchRequestSchema(BaseModel):
    """Search request schema.

    Validates and documents the search request parameters.

    Attributes:
        query: Search query text (1-1000 characters)
        user_id: User identifier for access control
        user_groups: User's group memberships for ACL
        top_k: Maximum number of results (1-100)
        search_types: Types of search to perform
        min_score: Minimum score threshold (0.0-1.0)
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search query text",
        examples=["인공지능 기술 문서"],
    )
    user_id: str = Field(
        ...,
        min_length=1,
        description="User identifier for ACL",
        examples=["user123"],
    )
    user_groups: list[str] = Field(
        default_factory=list,
        description="User's group memberships",
        examples=[["engineering", "ml-team"]],
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results",
    )
    search_types: list[SearchTypeEnum] | None = Field(
        default=None,
        description="Types of search to perform (default: all)",
        examples=[["dense", "sparse"]],
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum score threshold",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and clean query.

        Args:
            v: Raw query string

        Returns:
            Stripped query string

        Raises:
            ValueError: If query is empty after stripping
        """
        stripped = v.strip()
        if not stripped:
            raise ValueError("Query cannot be empty or whitespace only")
        return stripped

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "인공지능 기술 문서",
                    "user_id": "user123",
                    "user_groups": ["engineering"],
                    "top_k": 10,
                    "search_types": ["dense", "sparse"],
                    "min_score": 0.5,
                }
            ]
        }
    }


class SearchResultSchema(BaseModel):
    """Single search result schema.

    Represents one search hit with all relevant metadata.

    Attributes:
        chunk_uuid: Unique chunk identifier
        doc_uuid: Parent document identifier
        score: Relevance score (RRF or similarity)
        search_type: Type of search that produced this result
        text_preview: Preview of chunk text content
        title: Document title from metadata
        metadata: Additional metadata (sources, section_path, etc.)
    """

    chunk_uuid: str = Field(..., description="Chunk UUID")
    doc_uuid: str = Field(..., description="Document UUID")
    score: float = Field(..., ge=0.0, description="Relevance score")
    search_type: str = Field(..., description="Type of search that found this")
    text_preview: str | None = Field(None, description="Text preview of chunk")
    title: str | None = Field(None, description="Document title")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )


class SearchResponseSchema(BaseModel):
    """Search response schema.

    Contains search results and execution metadata.

    Attributes:
        results: List of search results
        total: Total number of results returned
        search_time_ms: Search execution time in milliseconds
        search_types_used: Search types that were actually executed
    """

    results: list[SearchResultSchema] = Field(
        ...,
        description="Search results",
    )
    total: int = Field(..., ge=0, description="Total number of results")
    search_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Search time in milliseconds",
    )
    search_types_used: list[str] = Field(
        default_factory=list,
        description="Search types that were used",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "results": [
                        {
                            "chunk_uuid": "chunk-123",
                            "doc_uuid": "doc-456",
                            "score": 0.95,
                            "search_type": "hybrid",
                            "text_preview": "AI 기술에 관한 문서...",
                            "title": "인공지능 개요",
                            "metadata": {
                                "sources": {
                                    "dense": {"score": 0.92, "rank": 1},
                                    "sparse": {"score": 0.88, "rank": 2},
                                }
                            },
                        }
                    ],
                    "total": 1,
                    "search_time_ms": 45.2,
                    "search_types_used": ["dense", "sparse"],
                }
            ]
        }
    }


class SearchErrorSchema(BaseModel):
    """Search error response schema.

    Standard error format for search API failures.

    Attributes:
        detail: Human-readable error message
        error_code: Machine-readable error code
    """

    detail: str = Field(..., description="Error message")
    error_code: str | None = Field(None, description="Error code")
