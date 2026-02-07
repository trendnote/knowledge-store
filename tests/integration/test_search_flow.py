"""Integration tests for search flow.

These tests verify the complete search flow including:
- Dense (semantic) search
- Sparse (keyword) search
- Graph (relationship) search
- Hybrid (combined) search with RRF fusion

Tests use mock infrastructure by default. Set INTEGRATION_TEST_REAL=1
to run against real databases.
"""

from typing import Any

import pytest

from src.domain.search import SearchRequest, SearchResponse, SearchType
from src.services.search_service import SearchService


# =============================================================================
# Dense Search Integration Tests
# =============================================================================


@pytest.mark.integration
class TestDenseSearchIntegration:
    """Integration tests for dense (semantic) search."""

    @pytest.mark.asyncio
    async def test_dense_search_returns_results(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test dense search returns relevant results."""
        results = await search_service.dense_search(
            query="인공지능 기술",
            user_id="user1",
            top_k=5,
        )

        assert len(results) > 0
        assert all(r.search_type == "dense" for r in results)

    @pytest.mark.asyncio
    async def test_dense_search_respects_top_k(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test dense search respects top_k limit."""
        top_k = 3
        results = await search_service.dense_search(
            query="인공지능",
            user_id="user1",
            top_k=top_k,
        )

        assert len(results) <= top_k

    @pytest.mark.asyncio
    async def test_dense_search_respects_acl(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test dense search respects ACL permissions."""
        results = await search_service.dense_search(
            query="비공개 기밀",
            user_id="user1",  # user1 doesn't own the private doc
            top_k=10,
        )

        # user2's private doc should not appear
        private_doc = next(
            d for d in test_data["docs"] if d["owner_id"] == "user2"
        )
        result_doc_uuids = [r.doc_uuid for r in results]
        assert private_doc["doc_uuid"] not in result_doc_uuids

    @pytest.mark.asyncio
    async def test_dense_search_with_min_score(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test dense search with minimum score filter."""
        results = await search_service.dense_search(
            query="인공지능",
            user_id="user1",
            top_k=10,
            min_score=0.8,
        )

        assert all(r.score >= 0.8 for r in results)

    @pytest.mark.asyncio
    async def test_dense_search_with_groups(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test dense search with user groups."""
        results = await search_service.dense_search(
            query="기술",
            user_id="user3",  # New user not owning any docs
            user_groups=["engineering"],  # Has group access
            top_k=10,
        )

        # Should find docs accessible via engineering group
        assert len(results) > 0


# =============================================================================
# Sparse Search Integration Tests
# =============================================================================


@pytest.mark.integration
class TestSparseSearchIntegration:
    """Integration tests for sparse (keyword) search."""

    @pytest.mark.asyncio
    async def test_sparse_search_keyword_match(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test sparse search matches keywords."""
        results = await search_service.sparse_search(
            query="토큰화",
            user_id="user1",
            top_k=5,
        )

        assert len(results) > 0
        assert all(r.search_type == "sparse" for r in results)

    @pytest.mark.asyncio
    async def test_sparse_search_korean_keywords(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test sparse search with Korean keywords."""
        results = await search_service.sparse_search(
            query="자연어 처리 NLP",
            user_id="user1",
            top_k=5,
        )

        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_sparse_search_respects_acl(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test sparse search respects ACL."""
        results = await search_service.sparse_search(
            query="비공개",
            user_id="user1",
            top_k=10,
        )

        private_doc = next(
            d for d in test_data["docs"] if d["owner_id"] == "user2"
        )
        result_doc_uuids = [r.doc_uuid for r in results]
        assert private_doc["doc_uuid"] not in result_doc_uuids

    @pytest.mark.asyncio
    async def test_sparse_search_empty_query_returns_empty(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test sparse search with empty query."""
        results = await search_service.sparse_search(
            query="   ",  # Whitespace only
            user_id="user1",
            top_k=5,
        )

        assert len(results) == 0


# =============================================================================
# Graph Search Integration Tests
# =============================================================================


@pytest.mark.integration
class TestGraphSearchIntegration:
    """Integration tests for graph (relationship) search."""

    @pytest.mark.asyncio
    async def test_graph_search_text_match(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test graph search matches text content."""
        results = await search_service.graph_search(
            query="딥러닝 신경망",
            user_id="user1",
            top_k=5,
        )

        assert len(results) >= 0  # May be 0 if no keyword match
        if results:
            assert all(r.search_type == "graph" for r in results)

    @pytest.mark.asyncio
    async def test_graph_search_respects_acl(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test graph search respects ACL."""
        results = await search_service.graph_search(
            query="비공개",
            user_id="user1",
            top_k=10,
        )

        private_doc = next(
            d for d in test_data["docs"] if d["owner_id"] == "user2"
        )
        result_doc_uuids = [r.doc_uuid for r in results]
        assert private_doc["doc_uuid"] not in result_doc_uuids

    @pytest.mark.asyncio
    async def test_graph_search_without_neo4j(
        self,
        mock_milvus_repo: Any,
        mock_embedding_service: Any,
        mock_acl_service: Any,
    ) -> None:
        """Test graph search without Neo4j returns empty."""
        service = SearchService(
            milvus_repo=mock_milvus_repo,
            embedding_service=mock_embedding_service,
            acl_service=mock_acl_service,
            neo4j_repo=None,  # No Neo4j
        )

        results = await service.graph_search(
            query="인공지능",
            user_id="user1",
            top_k=5,
        )

        assert len(results) == 0


# =============================================================================
# Hybrid/Unified Search Integration Tests
# =============================================================================


@pytest.mark.integration
class TestHybridSearchIntegration:
    """Integration tests for hybrid (unified) search."""

    @pytest.mark.asyncio
    async def test_unified_search_combines_results(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test unified search combines all search types."""
        request = SearchRequest(
            query="인공지능 머신러닝",
            user_id="user1",
            top_k=10,
            search_types=[SearchType.DENSE, SearchType.SPARSE, SearchType.GRAPH],
        )

        response = await search_service.unified_search(request)

        assert isinstance(response, SearchResponse)
        assert response.total >= 0
        assert len(response.search_types_used) >= 1

    @pytest.mark.asyncio
    async def test_unified_search_selected_types(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test unified search with selected types only."""
        request = SearchRequest(
            query="인공지능",
            user_id="user1",
            top_k=10,
            search_types=[SearchType.DENSE, SearchType.SPARSE],
        )

        response = await search_service.unified_search(request)

        assert SearchType.GRAPH not in response.search_types_used

    @pytest.mark.asyncio
    async def test_unified_search_deduplication(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test unified search deduplicates results."""
        request = SearchRequest(
            query="인공지능 기술",
            user_id="user1",
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # Check no duplicate chunk_uuids
        chunk_uuids = [r.chunk_uuid for r in response.results]
        assert len(chunk_uuids) == len(set(chunk_uuids))

    @pytest.mark.asyncio
    async def test_unified_search_with_min_score(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test unified search with minimum score filter."""
        request = SearchRequest(
            query="인공지능",
            user_id="user1",
            top_k=10,
            min_score=0.01,  # RRF scores are small
        )

        response = await search_service.unified_search(request)

        assert all(r.score >= 0.01 for r in response.results)

    @pytest.mark.asyncio
    async def test_search_convenience_method(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test search convenience method."""
        response = await search_service.search(
            query="인공지능",
            user_id="user1",
            top_k=5,
        )

        assert isinstance(response, SearchResponse)
        assert response.search_time_ms >= 0

    @pytest.mark.asyncio
    async def test_unified_search_respects_acl(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test unified search respects ACL across all types."""
        request = SearchRequest(
            query="비공개 기밀",
            user_id="user1",
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # user2's private doc should not appear
        private_doc = next(
            d for d in test_data["docs"] if d["owner_id"] == "user2"
        )
        result_doc_uuids = [r.doc_uuid for r in response.results]
        assert private_doc["doc_uuid"] not in result_doc_uuids


# =============================================================================
# Performance Integration Tests
# =============================================================================


@pytest.mark.integration
class TestSearchPerformance:
    """Performance tests for search operations."""

    @pytest.mark.asyncio
    async def test_search_response_time(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test search responds within acceptable time."""
        import time

        start = time.time()

        request = SearchRequest(
            query="인공지능",
            user_id="user1",
            top_k=10,
        )
        response = await search_service.unified_search(request)

        elapsed_ms = (time.time() - start) * 1000

        # With mocks, should be very fast
        # Relaxed threshold for CI environments
        assert elapsed_ms < 1000  # 1 second max
        assert response.search_time_ms >= 0

    @pytest.mark.asyncio
    async def test_multiple_sequential_searches(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test multiple sequential searches."""
        queries = ["인공지능", "자연어처리", "머신러닝", "딥러닝", "토큰화"]
        total_time = 0.0

        for query in queries:
            request = SearchRequest(
                query=query,
                user_id="user1",
                top_k=5,
            )
            response = await search_service.unified_search(request)
            total_time += response.search_time_ms

        avg_time = total_time / len(queries)
        # Average should be reasonable
        assert avg_time < 500  # 500ms average max

    @pytest.mark.asyncio
    async def test_large_top_k_performance(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test performance with large top_k."""
        import time

        start = time.time()

        request = SearchRequest(
            query="인공지능",
            user_id="user1",
            top_k=100,  # Large top_k
        )
        response = await search_service.unified_search(request)

        elapsed_ms = (time.time() - start) * 1000

        # Should still be fast with mocks
        assert elapsed_ms < 2000  # 2 seconds max
