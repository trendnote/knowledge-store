"""Tests for Milvus repository."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scipy.sparse import csr_array

from src.domain.search import MilvusChunk, SearchHit
from src.repositories.milvus.repository import (
    MilvusRepository,
    get_milvus_repository,
    reset_milvus_repository,
)


@pytest.fixture
def mock_client() -> MagicMock:
    """Create mock Milvus client."""
    client = MagicMock()
    client.insert_async = AsyncMock(return_value=["uuid1", "uuid2"])
    client.delete_async = AsyncMock(return_value=2)
    client.flush_async = AsyncMock()
    client.count_async = AsyncMock(return_value=100)
    client.dense_search_async = AsyncMock(return_value=[])
    client.sparse_search_async = AsyncMock(return_value=[])
    client.hybrid_search_async = AsyncMock(return_value=[])
    return client


@pytest.fixture
def repo(mock_client: MagicMock) -> MilvusRepository:
    """Create repository with mock client."""
    return MilvusRepository(mock_client)


@pytest.fixture
def sample_chunks() -> list[MilvusChunk]:
    """Create sample chunks for testing."""
    sparse1 = csr_array(([0.5, 0.3], ([0, 0], [100, 200])), shape=(1, 30000))
    sparse2 = csr_array(([0.4, 0.2], ([0, 0], [150, 250])), shape=(1, 30000))

    return [
        MilvusChunk(
            chunk_uuid="chunk-1",
            doc_uuid="doc-1",
            dense_embedding=[0.1] * 1024,
            sparse_embedding=sparse1,
            chunk_text="This is the first test chunk.",
            section_path="/intro",
            security_level="internal",
            allowed_groups=["group-1"],
        ),
        MilvusChunk(
            chunk_uuid="chunk-2",
            doc_uuid="doc-1",
            dense_embedding=[0.2] * 1024,
            sparse_embedding=sparse2,
            chunk_text="This is the second test chunk.",
            section_path="/body",
            security_level="public",
            allowed_groups=[],
        ),
    ]


@pytest.fixture
def sample_search_results() -> list[dict]:
    """Sample Milvus search results."""
    return [
        {
            "id": "chunk-1",
            "chunk_uuid": "chunk-1",
            "doc_uuid": "doc-1",
            "score": 0.95,
            "distance": 0.05,
            "chunk_text": "This is the first test chunk.",
            "section_path": "/intro",
            "security_level": "internal",
            "allowed_groups": ["group-1"],
        },
        {
            "id": "chunk-2",
            "chunk_uuid": "chunk-2",
            "doc_uuid": "doc-1",
            "score": 0.85,
            "distance": 0.15,
            "chunk_text": "This is the second test chunk.",
            "section_path": "/body",
            "security_level": "public",
            "allowed_groups": [],
        },
    ]


class TestInsertDelete:
    """Tests for insert and delete operations."""

    async def test_insert_chunks(
        self,
        repo: MilvusRepository,
        mock_client: MagicMock,
        sample_chunks: list[MilvusChunk],
    ) -> None:
        """Test chunk insertion."""
        result = await repo.insert_chunks(sample_chunks)

        assert len(result) == 2
        mock_client.insert_async.assert_called_once()

        # Verify data format
        call_args = mock_client.insert_async.call_args
        data = call_args[0][0]
        assert len(data) == 2
        assert data[0]["chunk_uuid"] == "chunk-1"
        assert data[1]["chunk_uuid"] == "chunk-2"
        assert len(data[0]["dense_embedding"]) == 1024

    async def test_insert_empty_list(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test inserting empty list returns empty without calling client."""
        result = await repo.insert_chunks([])

        assert result == []
        mock_client.insert_async.assert_not_called()

    async def test_insert_chunks_truncates_text(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test that long text is truncated."""
        long_text = "x" * 10000
        sparse = csr_array(([0.5], ([0], [100])), shape=(1, 30000))
        chunk = MilvusChunk(
            chunk_uuid="chunk-1",
            doc_uuid="doc-1",
            dense_embedding=[0.1] * 1024,
            sparse_embedding=sparse,
            chunk_text=long_text,
        )

        await repo.insert_chunks([chunk])

        call_args = mock_client.insert_async.call_args
        data = call_args[0][0]
        assert len(data[0]["chunk_text"]) == 8000

    async def test_delete_by_chunk_uuids(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test deletion by chunk UUIDs."""
        result = await repo.delete_by_chunk_uuids(["uuid1", "uuid2"])

        assert result == 2
        mock_client.delete_async.assert_called_once()

        # Verify expression format
        call_expr = mock_client.delete_async.call_args[0][0]
        assert "chunk_uuid in" in call_expr
        assert '"uuid1"' in call_expr
        assert '"uuid2"' in call_expr

    async def test_delete_by_chunk_uuids_empty(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test deletion with empty list."""
        result = await repo.delete_by_chunk_uuids([])

        assert result == 0
        mock_client.delete_async.assert_not_called()

    async def test_delete_by_doc_uuid(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test deletion by document UUID."""
        result = await repo.delete_by_doc_uuid("doc-1")

        assert result == 2
        mock_client.delete_async.assert_called_once()

        call_expr = mock_client.delete_async.call_args[0][0]
        assert 'doc_uuid == "doc-1"' in call_expr

    async def test_get_chunk_count_total(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test getting total chunk count."""
        result = await repo.get_chunk_count()

        assert result == 100
        mock_client.count_async.assert_called_once()

    async def test_get_chunk_count_by_doc(
        self,
        repo: MilvusRepository,
        mock_client: MagicMock,
        sample_search_results: list[dict],
    ) -> None:
        """Test getting chunk count for a document."""
        mock_client.dense_search_async.return_value = sample_search_results

        result = await repo.get_chunk_count("doc-1")

        assert result == 2
        mock_client.dense_search_async.assert_called_once()


class TestFilterExpression:
    """Tests for filter expression building."""

    def test_build_filter_with_doc_uuids(self, repo: MilvusRepository) -> None:
        """Test filter with document UUIDs."""
        expr = repo.build_filter_expr(doc_uuids=["doc-1", "doc-2"])

        assert expr is not None
        assert "doc_uuid in" in expr
        assert '"doc-1"' in expr
        assert '"doc-2"' in expr

    def test_build_filter_with_empty_doc_uuids(self, repo: MilvusRepository) -> None:
        """Test filter with empty document UUID list (no access)."""
        expr = repo.build_filter_expr(doc_uuids=[])

        assert expr is not None
        assert "__no_access__" in expr

    def test_build_filter_with_security_public(self, repo: MilvusRepository) -> None:
        """Test filter with public security level."""
        expr = repo.build_filter_expr(security_level="public")

        assert expr is not None
        assert 'security_level == "public"' in expr

    def test_build_filter_with_security_internal(self, repo: MilvusRepository) -> None:
        """Test filter with internal security level."""
        expr = repo.build_filter_expr(security_level="internal")

        assert expr is not None
        assert 'security_level in ["public", "internal"]' in expr

    def test_build_filter_with_security_confidential(
        self, repo: MilvusRepository
    ) -> None:
        """Test filter with confidential security level (no filter)."""
        expr = repo.build_filter_expr(security_level="confidential")

        assert expr is None

    def test_build_filter_combined(self, repo: MilvusRepository) -> None:
        """Test filter with both doc_uuids and security_level."""
        expr = repo.build_filter_expr(
            doc_uuids=["doc-1"], security_level="internal"
        )

        assert expr is not None
        assert "doc_uuid in" in expr
        assert "security_level in" in expr
        assert " and " in expr

    def test_build_filter_empty(self, repo: MilvusRepository) -> None:
        """Test empty filter."""
        expr = repo.build_filter_expr()

        assert expr is None


class TestDenseSearch:
    """Tests for dense vector search."""

    async def test_dense_search(
        self,
        repo: MilvusRepository,
        mock_client: MagicMock,
        sample_search_results: list[dict],
    ) -> None:
        """Test dense vector search."""
        mock_client.dense_search_async.return_value = sample_search_results

        results = await repo.dense_search(
            query_vector=[0.1] * 1024,
            doc_uuids=["doc-1"],
            top_k=10,
        )

        assert len(results) == 2
        assert all(isinstance(r, SearchHit) for r in results)
        assert results[0].chunk_uuid == "chunk-1"
        assert results[0].search_type == "dense"
        assert results[0].score == 0.95

        mock_client.dense_search_async.assert_called_once()
        call_kwargs = mock_client.dense_search_async.call_args[1]
        assert len(call_kwargs["query_vector"]) == 1024
        assert call_kwargs["limit"] == 10
        assert call_kwargs["output_fields"] == repo.OUTPUT_FIELDS

    async def test_dense_search_with_security_filter(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test dense search with security level filter."""
        mock_client.dense_search_async.return_value = []

        await repo.dense_search(
            query_vector=[0.1] * 1024,
            security_level="internal",
            top_k=10,
        )

        call_kwargs = mock_client.dense_search_async.call_args[1]
        assert "security_level" in call_kwargs["expr"]

    async def test_dense_search_no_filter(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test dense search without any filter."""
        mock_client.dense_search_async.return_value = []

        await repo.dense_search(query_vector=[0.1] * 1024, top_k=5)

        call_kwargs = mock_client.dense_search_async.call_args[1]
        assert call_kwargs["expr"] is None


class TestSparseSearch:
    """Tests for sparse vector search."""

    async def test_sparse_search(
        self,
        repo: MilvusRepository,
        mock_client: MagicMock,
        sample_search_results: list[dict],
    ) -> None:
        """Test sparse vector search."""
        mock_client.sparse_search_async.return_value = sample_search_results
        query_sparse = csr_array(([0.5, 0.3], ([0, 0], [100, 200])), shape=(1, 30000))

        results = await repo.sparse_search(
            query_sparse=query_sparse,
            doc_uuids=["doc-1"],
            top_k=10,
        )

        assert len(results) == 2
        assert all(isinstance(r, SearchHit) for r in results)
        assert results[0].search_type == "sparse"

        mock_client.sparse_search_async.assert_called_once()
        call_kwargs = mock_client.sparse_search_async.call_args[1]
        assert call_kwargs["limit"] == 10

    async def test_sparse_search_with_security(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test sparse search with security level."""
        mock_client.sparse_search_async.return_value = []
        query_sparse = csr_array(([0.5], ([0], [100])), shape=(1, 30000))

        await repo.sparse_search(
            query_sparse=query_sparse,
            security_level="public",
            top_k=10,
        )

        call_kwargs = mock_client.sparse_search_async.call_args[1]
        assert 'security_level == "public"' in call_kwargs["expr"]


class TestHybridSearch:
    """Tests for hybrid search."""

    async def test_hybrid_search(
        self,
        repo: MilvusRepository,
        mock_client: MagicMock,
        sample_search_results: list[dict],
    ) -> None:
        """Test hybrid search."""
        mock_client.hybrid_search_async.return_value = sample_search_results
        query_sparse = csr_array(([0.5, 0.3], ([0, 0], [100, 200])), shape=(1, 30000))

        results = await repo.hybrid_search(
            query_dense=[0.1] * 1024,
            query_sparse=query_sparse,
            doc_uuids=["doc-1"],
            top_k=10,
            rrf_k=60,
        )

        assert len(results) == 2
        assert all(isinstance(r, SearchHit) for r in results)
        assert results[0].search_type == "hybrid"

        mock_client.hybrid_search_async.assert_called_once()
        call_kwargs = mock_client.hybrid_search_async.call_args[1]
        assert len(call_kwargs["query_dense"]) == 1024
        assert call_kwargs["limit"] == 10
        assert call_kwargs["rrf_k"] == 60

    async def test_hybrid_search_custom_rrf_k(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test hybrid search with custom RRF k parameter."""
        mock_client.hybrid_search_async.return_value = []
        query_sparse = csr_array(([0.5], ([0], [100])), shape=(1, 30000))

        await repo.hybrid_search(
            query_dense=[0.1] * 1024,
            query_sparse=query_sparse,
            top_k=20,
            rrf_k=100,
        )

        call_kwargs = mock_client.hybrid_search_async.call_args[1]
        assert call_kwargs["rrf_k"] == 100
        assert call_kwargs["limit"] == 20


class TestGetByChunkUuid:
    """Tests for getting chunk by UUID."""

    async def test_get_by_chunk_uuid_found(
        self,
        repo: MilvusRepository,
        mock_client: MagicMock,
        sample_search_results: list[dict],
    ) -> None:
        """Test getting chunk by UUID when found."""
        mock_client.dense_search_async.return_value = [sample_search_results[0]]

        result = await repo.get_by_chunk_uuid("chunk-1")

        assert result is not None
        assert result.chunk_uuid == "chunk-1"

        call_kwargs = mock_client.dense_search_async.call_args[1]
        assert 'chunk_uuid == "chunk-1"' in call_kwargs["expr"]

    async def test_get_by_chunk_uuid_not_found(
        self, repo: MilvusRepository, mock_client: MagicMock
    ) -> None:
        """Test getting chunk by UUID when not found."""
        mock_client.dense_search_async.return_value = []

        result = await repo.get_by_chunk_uuid("non-existent")

        assert result is None


class TestSearchHit:
    """Tests for SearchHit model."""

    def test_from_milvus_hit(self) -> None:
        """Test creating SearchHit from Milvus result."""
        hit = {
            "id": "chunk-1",
            "chunk_uuid": "chunk-1",
            "doc_uuid": "doc-1",
            "score": 0.95,
            "distance": 0.05,
            "chunk_text": "Test chunk text",
            "section_path": "/intro",
            "security_level": "internal",
            "allowed_groups": ["group-1"],
        }

        result = SearchHit.from_milvus_hit(hit, search_type="dense")

        assert result.chunk_uuid == "chunk-1"
        assert result.doc_uuid == "doc-1"
        assert result.score == 0.95
        assert result.distance == 0.05
        assert result.chunk_text == "Test chunk text"
        assert result.section_path == "/intro"
        assert result.search_type == "dense"
        assert result.metadata["security_level"] == "internal"
        assert result.metadata["allowed_groups"] == ["group-1"]

    def test_from_milvus_hit_missing_fields(self) -> None:
        """Test creating SearchHit with missing fields."""
        hit = {
            "id": "chunk-1",
            "score": 0.8,
            "distance": 0.2,
        }

        result = SearchHit.from_milvus_hit(hit)

        assert result.chunk_uuid == "chunk-1"
        assert result.doc_uuid == ""
        assert result.chunk_text == ""
        assert result.section_path is None


class TestSingleton:
    """Tests for singleton factory."""

    def test_get_milvus_repository_creates_instance(
        self, mock_client: MagicMock
    ) -> None:
        """Test that factory creates repository instance."""
        reset_milvus_repository()

        repo = get_milvus_repository(mock_client)

        assert repo is not None
        assert isinstance(repo, MilvusRepository)

    def test_get_milvus_repository_returns_same_instance(
        self, mock_client: MagicMock
    ) -> None:
        """Test that factory returns same instance."""
        reset_milvus_repository()

        repo1 = get_milvus_repository(mock_client)
        repo2 = get_milvus_repository()

        assert repo1 is repo2

    def test_reset_milvus_repository(self, mock_client: MagicMock) -> None:
        """Test resetting singleton."""
        reset_milvus_repository()
        repo1 = get_milvus_repository(mock_client)

        reset_milvus_repository()
        repo2 = get_milvus_repository(mock_client)

        assert repo1 is not repo2

    def test_get_milvus_repository_auto_creates_client(self) -> None:
        """Test that factory auto-creates client when not provided."""
        reset_milvus_repository()

        with patch(
            "src.infrastructure.database.get_milvus_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            repo = get_milvus_repository()

            assert repo is not None
            mock_get_client.assert_called_once()
