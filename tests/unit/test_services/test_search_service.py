"""Tests for search service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.search import SearchHit, SearchResponse, SearchType
from src.services.search_service import (
    SearchService,
    close_search_service,
    get_search_service,
    reset_search_service,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_milvus_repo() -> MagicMock:
    """Create mock Milvus repository."""
    repo = MagicMock()
    repo.dense_search = AsyncMock()
    repo.sparse_search = AsyncMock()
    repo.hybrid_search = AsyncMock()
    return repo


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create mock embedding service."""
    service = MagicMock()
    service.encode.return_value = MagicMock(
        dense=[[0.1] * 1024],
        sparse=[MagicMock()],
    )
    return service


@pytest.fixture
def mock_acl_service() -> MagicMock:
    """Create mock ACL service."""
    service = MagicMock()
    service.get_accessible_documents = AsyncMock(return_value=["doc-1", "doc-2"])
    service.build_milvus_filter.return_value = 'doc_uuid in ["doc-1", "doc-2"]'
    return service


@pytest.fixture
def search_service(
    mock_milvus_repo: MagicMock,
    mock_embedding_service: MagicMock,
    mock_acl_service: MagicMock,
) -> SearchService:
    """Create search service with mocks."""
    return SearchService(mock_milvus_repo, mock_embedding_service, mock_acl_service)


@pytest.fixture
def sample_search_hits() -> list[SearchHit]:
    """Create sample search hits."""
    return [
        SearchHit(
            chunk_uuid="chunk-1",
            doc_uuid="doc-1",
            score=0.95,
            distance=0.05,
            chunk_text="First result text",
            search_type="dense",
        ),
        SearchHit(
            chunk_uuid="chunk-2",
            doc_uuid="doc-1",
            score=0.85,
            distance=0.15,
            chunk_text="Second result text",
            search_type="dense",
        ),
        SearchHit(
            chunk_uuid="chunk-3",
            doc_uuid="doc-2",
            score=0.45,
            distance=0.55,
            chunk_text="Third result text",
            search_type="dense",
        ),
    ]


# =============================================================================
# Test Dense Search
# =============================================================================


class TestDenseSearch:
    """Tests for dense search."""

    @pytest.mark.asyncio
    async def test_dense_search_success(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
        sample_search_hits: list[SearchHit],
    ) -> None:
        """Test successful dense search."""
        mock_milvus_repo.dense_search.return_value = sample_search_hits[:2]

        results = await search_service.dense_search(
            query="test query",
            user_id="user1",
            user_groups=["group1"],
            top_k=10,
        )

        assert len(results) == 2
        assert results[0].score == 0.95
        assert results[0].chunk_uuid == "chunk-1"

    @pytest.mark.asyncio
    async def test_dense_search_with_min_score(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
        sample_search_hits: list[SearchHit],
    ) -> None:
        """Test dense search with minimum score filter."""
        mock_milvus_repo.dense_search.return_value = sample_search_hits

        results = await search_service.dense_search(
            query="test query",
            user_id="user1",
            top_k=10,
            min_score=0.5,
        )

        assert len(results) == 2
        assert all(r.score >= 0.5 for r in results)

    @pytest.mark.asyncio
    async def test_dense_search_empty_result(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test dense search with no results."""
        mock_milvus_repo.dense_search.return_value = []

        results = await search_service.dense_search(
            query="test query",
            user_id="user1",
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_dense_search_applies_acl_filter(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test that ACL filter is applied."""
        mock_milvus_repo.dense_search.return_value = []

        await search_service.dense_search(
            query="test query",
            user_id="user1",
            user_groups=["group1", "group2"],
        )

        mock_acl_service.get_accessible_documents.assert_called_once_with(
            "user1", ["group1", "group2"]
        )
        mock_milvus_repo.dense_search.assert_called_once()
        call_kwargs = mock_milvus_repo.dense_search.call_args.kwargs
        assert call_kwargs["doc_uuids"] == ["doc-1", "doc-2"]

    @pytest.mark.asyncio
    async def test_dense_search_generates_embedding(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that query embedding is generated."""
        mock_milvus_repo.dense_search.return_value = []

        await search_service.dense_search(
            query="test query",
            user_id="user1",
        )

        mock_embedding_service.encode.assert_called_once_with(["test query"])

    @pytest.mark.asyncio
    async def test_dense_search_no_embedding_returns_empty(
        self,
        search_service: SearchService,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that empty result is returned if embedding fails."""
        mock_embedding_service.encode.return_value = None

        results = await search_service.dense_search(
            query="test query",
            user_id="user1",
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_dense_search_empty_dense_returns_empty(
        self,
        search_service: SearchService,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that empty result is returned if dense embedding is empty."""
        mock_embedding_service.encode.return_value = MagicMock(dense=[], sparse=[])

        results = await search_service.dense_search(
            query="test query",
            user_id="user1",
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_dense_search_with_security_level(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test dense search with security level filter."""
        mock_milvus_repo.dense_search.return_value = []

        await search_service.dense_search(
            query="test query",
            user_id="user1",
            security_level="internal",
        )

        call_kwargs = mock_milvus_repo.dense_search.call_args.kwargs
        assert call_kwargs["security_level"] == "internal"

    @pytest.mark.asyncio
    async def test_dense_search_exception_propagates(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test that exceptions from Milvus propagate."""
        mock_milvus_repo.dense_search.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            await search_service.dense_search(
                query="test query",
                user_id="user1",
            )


class TestDenseSearchWithResponse:
    """Tests for dense search with response wrapper."""

    @pytest.mark.asyncio
    async def test_returns_search_response(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
        sample_search_hits: list[SearchHit],
    ) -> None:
        """Test that SearchResponse is returned."""
        mock_milvus_repo.dense_search.return_value = sample_search_hits[:2]

        response = await search_service.dense_search_with_response(
            query="test query",
            user_id="user1",
        )

        assert isinstance(response, SearchResponse)
        assert response.total == 2
        assert len(response.results) == 2
        assert SearchType.DENSE in response.search_types_used
        assert response.search_time_ms >= 0

    @pytest.mark.asyncio
    async def test_response_to_dict(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
        sample_search_hits: list[SearchHit],
    ) -> None:
        """Test SearchResponse.to_dict() method."""
        mock_milvus_repo.dense_search.return_value = sample_search_hits[:1]

        response = await search_service.dense_search_with_response(
            query="test query",
            user_id="user1",
        )

        response_dict = response.to_dict()
        assert "results" in response_dict
        assert "total" in response_dict
        assert "search_time_ms" in response_dict
        assert "search_types_used" in response_dict
        assert response_dict["search_types_used"] == ["dense"]


# =============================================================================
# Test Sparse Search
# =============================================================================


class TestSparseSearch:
    """Tests for sparse search."""

    @pytest.mark.asyncio
    async def test_sparse_search_success(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
        sample_search_hits: list[SearchHit],
    ) -> None:
        """Test successful sparse search."""
        mock_milvus_repo.sparse_search.return_value = sample_search_hits[:2]

        results = await search_service.sparse_search(
            query="test query",
            user_id="user1",
            user_groups=["group1"],
            top_k=10,
        )

        assert len(results) == 2
        mock_milvus_repo.sparse_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_sparse_search_no_embedding_returns_empty(
        self,
        search_service: SearchService,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that empty result is returned if sparse embedding fails."""
        mock_embedding_service.encode.return_value = MagicMock(dense=[[0.1]], sparse=[])

        results = await search_service.sparse_search(
            query="test query",
            user_id="user1",
        )

        assert len(results) == 0


# =============================================================================
# Test Hybrid Search
# =============================================================================


class TestHybridSearch:
    """Tests for hybrid search."""

    @pytest.mark.asyncio
    async def test_hybrid_search_success(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
        sample_search_hits: list[SearchHit],
    ) -> None:
        """Test successful hybrid search."""
        mock_milvus_repo.hybrid_search.return_value = sample_search_hits[:2]

        results = await search_service.hybrid_search(
            query="test query",
            user_id="user1",
            user_groups=["group1"],
            top_k=10,
        )

        assert len(results) == 2
        mock_milvus_repo.hybrid_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_hybrid_search_with_rrf_k(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test hybrid search with custom RRF k parameter."""
        mock_milvus_repo.hybrid_search.return_value = []

        await search_service.hybrid_search(
            query="test query",
            user_id="user1",
            rrf_k=100,
        )

        call_kwargs = mock_milvus_repo.hybrid_search.call_args.kwargs
        assert call_kwargs["rrf_k"] == 100


# =============================================================================
# Test SearchHit Model
# =============================================================================


class TestSearchHit:
    """Tests for SearchHit model."""

    def test_from_milvus_hit(self) -> None:
        """Test creating SearchHit from Milvus hit."""
        hit_data = {
            "chunk_uuid": "chunk-1",
            "doc_uuid": "doc-1",
            "score": 0.95,
            "distance": 0.05,
            "chunk_text": "Sample text",
            "section_path": "/intro",
            "security_level": "internal",
            "allowed_groups": ["team-ml"],
        }

        hit = SearchHit.from_milvus_hit(hit_data, search_type="dense")

        assert hit.chunk_uuid == "chunk-1"
        assert hit.doc_uuid == "doc-1"
        assert hit.score == 0.95
        assert hit.search_type == "dense"
        assert hit.metadata["security_level"] == "internal"

    def test_to_dict(self) -> None:
        """Test SearchHit.to_dict() method."""
        hit = SearchHit(
            chunk_uuid="chunk-1",
            doc_uuid="doc-1",
            score=0.95,
            distance=0.05,
            chunk_text="Sample text",
            search_type="dense",
        )

        hit_dict = hit.to_dict()

        assert hit_dict["chunk_uuid"] == "chunk-1"
        assert hit_dict["score"] == 0.95
        assert hit_dict["search_type"] == "dense"


class TestSearchType:
    """Tests for SearchType enum."""

    def test_search_type_values(self) -> None:
        """Test SearchType enum values."""
        assert SearchType.DENSE.value == "dense"
        assert SearchType.SPARSE.value == "sparse"
        assert SearchType.GRAPH.value == "graph"
        assert SearchType.HYBRID.value == "hybrid"


# =============================================================================
# Test Singleton Factory
# =============================================================================


class TestSingletonFactory:
    """Tests for singleton factory functions."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_search_service()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_search_service()

    def test_get_search_service_creates_instance(
        self,
        mock_milvus_repo: MagicMock,
        mock_embedding_service: MagicMock,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test get_search_service creates instance."""
        service = get_search_service(
            mock_milvus_repo, mock_embedding_service, mock_acl_service
        )

        assert service is not None
        assert isinstance(service, SearchService)

    def test_get_search_service_returns_same_instance(
        self,
        mock_milvus_repo: MagicMock,
        mock_embedding_service: MagicMock,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test get_search_service returns same instance."""
        service1 = get_search_service(
            mock_milvus_repo, mock_embedding_service, mock_acl_service
        )
        service2 = get_search_service()

        assert service1 is service2

    def test_get_search_service_requires_deps_first_call(self) -> None:
        """Test get_search_service requires dependencies on first call."""
        with pytest.raises(ValueError, match="All dependencies required"):
            get_search_service()

    def test_close_search_service(
        self,
        mock_milvus_repo: MagicMock,
        mock_embedding_service: MagicMock,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test close_search_service clears singleton."""
        service1 = get_search_service(
            mock_milvus_repo, mock_embedding_service, mock_acl_service
        )

        close_search_service()

        service2 = get_search_service(
            mock_milvus_repo, mock_embedding_service, mock_acl_service
        )
        assert service1 is not service2

    def test_reset_search_service(
        self,
        mock_milvus_repo: MagicMock,
        mock_embedding_service: MagicMock,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test reset_search_service creates new instance."""
        service1 = get_search_service(
            mock_milvus_repo, mock_embedding_service, mock_acl_service
        )

        reset_search_service()

        service2 = get_search_service(
            mock_milvus_repo, mock_embedding_service, mock_acl_service
        )
        assert service1 is not service2
