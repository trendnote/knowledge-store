"""Tests for search router."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.search import router, _convert_api_to_domain_types
from src.api.schemas.search import SearchTypeEnum
from src.domain.search import SearchHit, SearchResponse, SearchType


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_search_service() -> MagicMock:
    """Create mock search service."""
    service = MagicMock()
    service.unified_search = AsyncMock(
        return_value=SearchResponse(
            results=[
                SearchHit(
                    chunk_uuid="chunk-1",
                    doc_uuid="doc-1",
                    score=0.95,
                    distance=0.05,
                    chunk_text="Test text content for the search result",
                    search_type="hybrid",
                    metadata={"title": "Test Document"},
                )
            ],
            total=1,
            search_time_ms=45.0,
            search_types_used=[SearchType.DENSE, SearchType.SPARSE],
        )
    )
    return service


@pytest.fixture
def app(mock_search_service: MagicMock) -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override dependency
    async def get_mock_service() -> MagicMock:
        return mock_search_service

    from src.api.routers import search

    app.dependency_overrides[search.get_search_service] = get_mock_service

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


# =============================================================================
# Test Type Conversion
# =============================================================================


class TestTypeConversion:
    """Tests for type conversion functions."""

    def test_convert_api_to_domain_types_none(self) -> None:
        """Test conversion with None input."""
        result = _convert_api_to_domain_types(None)
        assert result is None

    def test_convert_api_to_domain_types_single(self) -> None:
        """Test conversion with single type."""
        result = _convert_api_to_domain_types([SearchTypeEnum.DENSE])
        assert result == [SearchType.DENSE]

    def test_convert_api_to_domain_types_multiple(self) -> None:
        """Test conversion with multiple types."""
        result = _convert_api_to_domain_types(
            [SearchTypeEnum.DENSE, SearchTypeEnum.SPARSE, SearchTypeEnum.GRAPH]
        )
        assert result == [SearchType.DENSE, SearchType.SPARSE, SearchType.GRAPH]

    def test_convert_api_to_domain_types_all(self) -> None:
        """Test conversion with all types."""
        result = _convert_api_to_domain_types(
            [
                SearchTypeEnum.DENSE,
                SearchTypeEnum.SPARSE,
                SearchTypeEnum.GRAPH,
                SearchTypeEnum.HYBRID,
            ]
        )
        assert len(result) == 4


# =============================================================================
# Test Search Endpoint
# =============================================================================


class TestSearchEndpoint:
    """Tests for search endpoint."""

    def test_search_success(
        self,
        client: TestClient,
        mock_search_service: MagicMock,
    ) -> None:
        """Test successful search."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test query",
                "user_id": "user1",
                "top_k": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["results"]) == 1
        assert data["search_time_ms"] == 45.0
        assert "dense" in data["search_types_used"]
        assert "sparse" in data["search_types_used"]

        # Verify service was called
        mock_search_service.unified_search.assert_called_once()

    def test_search_with_all_params(
        self,
        client: TestClient,
    ) -> None:
        """Test search with all parameters."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "인공지능 기술",
                "user_id": "user123",
                "user_groups": ["engineering", "ml-team"],
                "top_k": 20,
                "search_types": ["dense", "sparse"],
                "min_score": 0.5,
            },
        )

        assert response.status_code == 200

    def test_search_result_fields(
        self,
        client: TestClient,
    ) -> None:
        """Test search result contains expected fields."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "user_id": "user1",
            },
        )

        assert response.status_code == 200
        data = response.json()

        result = data["results"][0]
        assert "chunk_uuid" in result
        assert "doc_uuid" in result
        assert "score" in result
        assert "search_type" in result
        assert "text_preview" in result
        assert "metadata" in result

    def test_search_empty_query_fails(
        self,
        client: TestClient,
    ) -> None:
        """Test search with empty query returns validation error."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "",
                "user_id": "user1",
            },
        )

        assert response.status_code == 422  # Validation error

    def test_search_whitespace_query_fails(
        self,
        client: TestClient,
    ) -> None:
        """Test search with whitespace-only query fails."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "   ",
                "user_id": "user1",
            },
        )

        assert response.status_code == 422

    def test_search_missing_user_id_fails(
        self,
        client: TestClient,
    ) -> None:
        """Test search without user_id returns validation error."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
            },
        )

        assert response.status_code == 422

    def test_search_invalid_top_k_fails(
        self,
        client: TestClient,
    ) -> None:
        """Test search with invalid top_k."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "user_id": "user1",
                "top_k": 0,
            },
        )

        assert response.status_code == 422

        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "user_id": "user1",
                "top_k": 101,
            },
        )

        assert response.status_code == 422

    def test_search_invalid_min_score_fails(
        self,
        client: TestClient,
    ) -> None:
        """Test search with invalid min_score."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "user_id": "user1",
                "min_score": -0.1,
            },
        )

        assert response.status_code == 422

    def test_search_value_error_returns_400(
        self,
        client: TestClient,
        mock_search_service: MagicMock,
    ) -> None:
        """Test that ValueError returns 400."""
        mock_search_service.unified_search.side_effect = ValueError("Invalid parameter")

        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "user_id": "user1",
            },
        )

        assert response.status_code == 400
        assert "Invalid parameter" in response.json()["detail"]

    def test_search_permission_error_returns_403(
        self,
        client: TestClient,
        mock_search_service: MagicMock,
    ) -> None:
        """Test that PermissionError returns 403."""
        mock_search_service.unified_search.side_effect = PermissionError("No access")

        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "user_id": "user1",
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def test_search_exception_returns_500(
        self,
        client: TestClient,
        mock_search_service: MagicMock,
    ) -> None:
        """Test that general exceptions return 500."""
        mock_search_service.unified_search.side_effect = Exception("Database error")

        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "user_id": "user1",
            },
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Search failed"


# =============================================================================
# Test Empty Results
# =============================================================================


class TestEmptyResults:
    """Tests for empty search results."""

    def test_search_empty_results(
        self,
        client: TestClient,
        mock_search_service: MagicMock,
    ) -> None:
        """Test search with no results."""
        mock_search_service.unified_search.return_value = SearchResponse(
            results=[],
            total=0,
            search_time_ms=10.0,
            search_types_used=[SearchType.DENSE],
        )

        response = client.post(
            "/api/v1/search",
            json={
                "query": "nonexistent query",
                "user_id": "user1",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["results"]) == 0


# =============================================================================
# Test Korean Query
# =============================================================================


class TestKoreanQuery:
    """Tests for Korean language queries."""

    def test_korean_query_success(
        self,
        client: TestClient,
    ) -> None:
        """Test search with Korean query."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "인공지능 기술 문서를 찾아주세요",
                "user_id": "user1",
            },
        )

        assert response.status_code == 200

    def test_korean_user_groups(
        self,
        client: TestClient,
    ) -> None:
        """Test search with Korean user groups."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
                "user_id": "user1",
                "user_groups": ["개발팀", "AI팀"],
            },
        )

        assert response.status_code == 200
