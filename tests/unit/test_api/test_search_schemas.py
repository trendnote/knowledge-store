"""Tests for search API schemas."""

import pytest
from pydantic import ValidationError

from src.api.schemas.search import (
    SearchErrorSchema,
    SearchRequestSchema,
    SearchResponseSchema,
    SearchResultSchema,
    SearchTypeEnum,
)


# =============================================================================
# Test SearchTypeEnum
# =============================================================================


class TestSearchTypeEnum:
    """Tests for SearchTypeEnum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert SearchTypeEnum.DENSE.value == "dense"
        assert SearchTypeEnum.SPARSE.value == "sparse"
        assert SearchTypeEnum.GRAPH.value == "graph"
        assert SearchTypeEnum.HYBRID.value == "hybrid"

    def test_enum_from_string(self) -> None:
        """Test creating enum from string."""
        assert SearchTypeEnum("dense") == SearchTypeEnum.DENSE
        assert SearchTypeEnum("sparse") == SearchTypeEnum.SPARSE


# =============================================================================
# Test SearchRequestSchema
# =============================================================================


class TestSearchRequestSchema:
    """Tests for SearchRequestSchema."""

    def test_valid_minimal_request(self) -> None:
        """Test valid request with minimal fields."""
        schema = SearchRequestSchema(
            query="test query",
            user_id="user1",
        )
        assert schema.query == "test query"
        assert schema.user_id == "user1"
        assert schema.top_k == 10  # Default
        assert schema.user_groups == []  # Default
        assert schema.search_types is None  # Default
        assert schema.min_score == 0.0  # Default

    def test_valid_full_request(self) -> None:
        """Test valid request with all fields."""
        schema = SearchRequestSchema(
            query="인공지능 기술 문서",
            user_id="user123",
            user_groups=["engineering", "ml-team"],
            top_k=20,
            search_types=[SearchTypeEnum.DENSE, SearchTypeEnum.SPARSE],
            min_score=0.5,
        )
        assert schema.query == "인공지능 기술 문서"
        assert schema.user_id == "user123"
        assert len(schema.user_groups) == 2
        assert schema.top_k == 20
        assert len(schema.search_types) == 2
        assert schema.min_score == 0.5

    def test_query_validation_empty(self) -> None:
        """Test query validation with empty string."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequestSchema(query="", user_id="user1")
        # Pydantic 2.x uses "string_too_short" for min_length validation
        assert (
            "Query cannot be empty" in str(exc_info.value)
            or "string_too_short" in str(exc_info.value)
            or "at least 1 character" in str(exc_info.value)
        )

    def test_query_validation_whitespace(self) -> None:
        """Test query validation with whitespace only."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequestSchema(query="   ", user_id="user1")
        assert "Query cannot be empty" in str(exc_info.value)

    def test_query_strips_whitespace(self) -> None:
        """Test that query is stripped."""
        schema = SearchRequestSchema(
            query="  test query  ",
            user_id="user1",
        )
        assert schema.query == "test query"

    def test_user_id_required(self) -> None:
        """Test user_id is required."""
        with pytest.raises(ValidationError):
            SearchRequestSchema(query="test")  # type: ignore

    def test_user_id_not_empty(self) -> None:
        """Test user_id cannot be empty."""
        with pytest.raises(ValidationError):
            SearchRequestSchema(query="test", user_id="")

    def test_top_k_bounds_min(self) -> None:
        """Test top_k minimum bound."""
        with pytest.raises(ValidationError):
            SearchRequestSchema(query="test", user_id="user1", top_k=0)

    def test_top_k_bounds_max(self) -> None:
        """Test top_k maximum bound."""
        with pytest.raises(ValidationError):
            SearchRequestSchema(query="test", user_id="user1", top_k=101)

    def test_min_score_bounds(self) -> None:
        """Test min_score bounds."""
        with pytest.raises(ValidationError):
            SearchRequestSchema(query="test", user_id="user1", min_score=-0.1)

        with pytest.raises(ValidationError):
            SearchRequestSchema(query="test", user_id="user1", min_score=1.1)

    def test_search_types_validation(self) -> None:
        """Test search_types accepts valid enum values."""
        schema = SearchRequestSchema(
            query="test",
            user_id="user1",
            search_types=[SearchTypeEnum.DENSE],
        )
        assert schema.search_types == [SearchTypeEnum.DENSE]

    def test_query_max_length(self) -> None:
        """Test query max length validation."""
        long_query = "a" * 1001
        with pytest.raises(ValidationError):
            SearchRequestSchema(query=long_query, user_id="user1")


# =============================================================================
# Test SearchResultSchema
# =============================================================================


class TestSearchResultSchema:
    """Tests for SearchResultSchema."""

    def test_valid_result(self) -> None:
        """Test valid search result."""
        result = SearchResultSchema(
            chunk_uuid="chunk-123",
            doc_uuid="doc-456",
            score=0.95,
            search_type="hybrid",
            text_preview="AI 기술에 관한 문서...",
            title="인공지능 개요",
            metadata={"sources": {"dense": {"score": 0.92}}},
        )
        assert result.chunk_uuid == "chunk-123"
        assert result.doc_uuid == "doc-456"
        assert result.score == 0.95
        assert result.search_type == "hybrid"
        assert result.text_preview == "AI 기술에 관한 문서..."
        assert result.title == "인공지능 개요"

    def test_minimal_result(self) -> None:
        """Test minimal search result."""
        result = SearchResultSchema(
            chunk_uuid="c1",
            doc_uuid="d1",
            score=0.5,
            search_type="dense",
        )
        assert result.text_preview is None
        assert result.title is None
        assert result.metadata == {}

    def test_score_non_negative(self) -> None:
        """Test score cannot be negative."""
        with pytest.raises(ValidationError):
            SearchResultSchema(
                chunk_uuid="c1",
                doc_uuid="d1",
                score=-0.1,
                search_type="dense",
            )


# =============================================================================
# Test SearchResponseSchema
# =============================================================================


class TestSearchResponseSchema:
    """Tests for SearchResponseSchema."""

    def test_valid_response(self) -> None:
        """Test valid search response."""
        response = SearchResponseSchema(
            results=[
                SearchResultSchema(
                    chunk_uuid="c1",
                    doc_uuid="d1",
                    score=0.95,
                    search_type="hybrid",
                )
            ],
            total=1,
            search_time_ms=45.2,
            search_types_used=["dense", "sparse"],
        )
        assert len(response.results) == 1
        assert response.total == 1
        assert response.search_time_ms == 45.2
        assert response.search_types_used == ["dense", "sparse"]

    def test_empty_results(self) -> None:
        """Test response with no results."""
        response = SearchResponseSchema(
            results=[],
            total=0,
            search_time_ms=10.0,
            search_types_used=["dense"],
        )
        assert len(response.results) == 0
        assert response.total == 0

    def test_total_non_negative(self) -> None:
        """Test total cannot be negative."""
        with pytest.raises(ValidationError):
            SearchResponseSchema(
                results=[],
                total=-1,
                search_time_ms=10.0,
            )

    def test_search_time_non_negative(self) -> None:
        """Test search_time_ms cannot be negative."""
        with pytest.raises(ValidationError):
            SearchResponseSchema(
                results=[],
                total=0,
                search_time_ms=-1.0,
            )


# =============================================================================
# Test SearchErrorSchema
# =============================================================================


class TestSearchErrorSchema:
    """Tests for SearchErrorSchema."""

    def test_error_with_code(self) -> None:
        """Test error with error code."""
        error = SearchErrorSchema(
            detail="Invalid query",
            error_code="INVALID_QUERY",
        )
        assert error.detail == "Invalid query"
        assert error.error_code == "INVALID_QUERY"

    def test_error_without_code(self) -> None:
        """Test error without error code."""
        error = SearchErrorSchema(detail="Something went wrong")
        assert error.detail == "Something went wrong"
        assert error.error_code is None
