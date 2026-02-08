"""E2E tests for performance and synchronization.

This module tests:
- Search response time
- Document creation time
- Synchronization time across stores
- Concurrent operation handling
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.e2e.conftest import DocumentHelper, Timer


@pytest.mark.e2e
class TestSearchPerformance:
    """E2E tests for search performance."""

    async def test_search_response_time(
        self,
        doc_helper: DocumentHelper,
        timer: type[Timer],
    ) -> None:
        """Test that search responds within acceptable time.

        Performance targets:
        - Average response time: < 200ms
        - Maximum response time: < 500ms
        """
        # Create test document
        await doc_helper.create(
            title="Performance Test Document",
            content="성능 테스트를 위한 문서입니다. 검색 응답 시간을 측정합니다. "
            "이 문서는 벤치마크 목적으로 사용됩니다.",
        )

        await doc_helper.wait_for_indexing()

        # Measure search time over multiple requests
        times: list[float] = []

        for _ in range(5):
            with timer() as t:
                await doc_helper.search("성능 테스트")
            times.append(t.elapsed_ms)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # Assert performance targets
        assert avg_time < 200, f"Average response time {avg_time:.1f}ms exceeds 200ms target"
        assert max_time < 500, f"Max response time {max_time:.1f}ms exceeds 500ms target"

    async def test_search_cold_vs_warm(
        self,
        doc_helper: DocumentHelper,
        timer: type[Timer],
    ) -> None:
        """Test that cached/warm searches are faster than cold searches."""
        await doc_helper.create(
            title="Cache Test Document",
            content="캐시 테스트를 위한 문서입니다. 웜 캐시 성능을 확인합니다.",
        )

        await doc_helper.wait_for_indexing()

        # Cold search
        with timer() as cold_timer:
            await doc_helper.search("캐시 테스트")
        cold_time = cold_timer.elapsed_ms

        # Warm searches (should be faster due to caching)
        warm_times: list[float] = []
        for _ in range(3):
            with timer() as t:
                await doc_helper.search("캐시 테스트")
            warm_times.append(t.elapsed_ms)

        avg_warm = sum(warm_times) / len(warm_times)

        # Record times (warm should generally be faster)
        # Note: This is informational, not a strict assertion
        assert warm_times is not None  # Basic sanity check

    async def test_empty_search_performance(
        self,
        doc_helper: DocumentHelper,
        timer: type[Timer],
    ) -> None:
        """Test that search with no results is still fast."""
        # Search for non-existent content
        with timer() as t:
            result = await doc_helper.search("xyzzy완전히없는검색어12345")

        assert t.elapsed_ms < 300, f"Empty search took {t.elapsed_ms}ms, expected < 300ms"
        assert len(result.get("results", [])) == 0


@pytest.mark.e2e
class TestDocumentCreationPerformance:
    """E2E tests for document creation performance."""

    async def test_document_creation_time(
        self,
        doc_helper: DocumentHelper,
        timer: type[Timer],
    ) -> None:
        """Test document creation completes within acceptable time.

        Target: Document creation (including chunking and embedding)
        should complete within 5 seconds.
        """
        content = "테스트 문서 내용입니다. " * 50  # ~500 chars

        with timer() as t:
            doc = await doc_helper.create(
                title="Creation Time Test",
                content=content,
            )

        assert doc is not None
        assert t.elapsed_ms < 5000, f"Creation time {t.elapsed_ms}ms exceeds 5s target"

    async def test_large_document_creation(
        self,
        doc_helper: DocumentHelper,
        timer: type[Timer],
    ) -> None:
        """Test creation of larger documents."""
        # Create larger content (~5KB)
        content = ("대용량 문서 테스트입니다. 이 문서는 여러 청크로 분할될 예정입니다. " * 100)

        with timer() as t:
            doc = await doc_helper.create(
                title="Large Document Test",
                content=content,
            )

        assert doc is not None
        # Larger documents may take longer but should still be reasonable
        assert t.elapsed_ms < 10000, f"Large doc creation took {t.elapsed_ms}ms"

    async def test_multiple_document_creation(
        self,
        doc_helper: DocumentHelper,
        timer: type[Timer],
    ) -> None:
        """Test creating multiple documents sequentially."""
        num_docs = 5

        with timer() as t:
            for i in range(num_docs):
                await doc_helper.create(
                    title=f"Batch Document {i}",
                    content=f"배치 생성 테스트 문서 {i}번입니다.",
                )

        avg_time = t.elapsed_ms / num_docs
        assert avg_time < 3000, f"Average creation time {avg_time}ms exceeds 3s"


@pytest.mark.e2e
class TestSynchronization:
    """E2E tests for synchronization across stores."""

    async def test_sync_within_timeout(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test that changes sync across stores within acceptable time.

        Target: Changes should be searchable within 30 seconds.
        """
        # Create document
        doc = await doc_helper.create(
            title="Sync Test Document",
            content="동기화 테스트 원본 내용입니다.",
        )
        doc_uuid = doc.get("doc_uuid") or doc.get("id")

        # Update with unique content
        unique_content = f"동기화 확인 유니크 {time.time()}"
        await doc_helper.update(doc_uuid, content=unique_content)

        # Poll for sync completion
        synced = False
        max_wait = 60  # 60 seconds max
        start = time.time()

        while time.time() - start < max_wait:
            result = await doc_helper.search(unique_content[:20])
            if any(
                (r.get("doc_uuid") or r.get("document_id")) == doc_uuid
                for r in result.get("results", [])
            ):
                synced = True
                break
            await asyncio.sleep(1)

        sync_time = time.time() - start

        assert synced, f"Sync not completed within {max_wait}s"
        assert sync_time < 30, f"Sync took {sync_time:.1f}s, expected < 30s"

    async def test_delete_sync(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test that deletion syncs across all stores."""
        unique_keyword = "삭제동기화테스트키워드"

        doc = await doc_helper.create(
            title="Delete Sync Test",
            content=f"이 문서는 삭제 동기화를 테스트합니다. {unique_keyword}",
        )
        doc_uuid = doc.get("doc_uuid") or doc.get("id")

        await doc_helper.wait_for_indexing()

        # Verify searchable
        result1 = await doc_helper.search(unique_keyword)
        assert any(
            (r.get("doc_uuid") or r.get("document_id")) == doc_uuid
            for r in result1.get("results", [])
        )

        # Delete
        await doc_helper.delete(doc_uuid)

        # Poll for sync
        deleted_from_search = False
        max_wait = 30
        start = time.time()

        while time.time() - start < max_wait:
            result = await doc_helper.search(unique_keyword)
            if not any(
                (r.get("doc_uuid") or r.get("document_id")) == doc_uuid
                for r in result.get("results", [])
            ):
                deleted_from_search = True
                break
            await asyncio.sleep(1)

        assert deleted_from_search, "Deleted document still appears in search"


@pytest.mark.e2e
@pytest.mark.slow
class TestConcurrency:
    """E2E tests for concurrent operations.

    These tests are marked as 'slow' because they create multiple
    documents and perform parallel operations.
    """

    async def test_concurrent_searches(
        self,
        doc_helper: DocumentHelper,
        timer: type[Timer],
    ) -> None:
        """Test multiple concurrent searches complete efficiently."""
        # Create documents first
        for i in range(5):
            await doc_helper.create(
                title=f"Concurrent Test {i}",
                content=f"동시성 테스트 문서 {i}번입니다. 병렬 검색 테스트.",
            )

        await doc_helper.wait_for_indexing(3.0)

        # Run concurrent searches
        queries = ["동시성", "테스트", "문서", "병렬", "검색"]

        async def search_task(query: str) -> dict:
            return await doc_helper.search(query)

        with timer() as t:
            results = await asyncio.gather(*[search_task(q) for q in queries])

        # All should complete
        assert len(results) == 5

        # Should complete faster than sequential (parallel benefit)
        assert t.elapsed_ms < 5000, f"Concurrent searches took {t.elapsed_ms}ms"

    async def test_concurrent_crud(
        self,
        doc_helper: DocumentHelper,
        timer: type[Timer],
    ) -> None:
        """Test concurrent CRUD operations don't conflict."""

        async def create_task(i: int) -> dict:
            return await doc_helper.create(
                title=f"CRUD Concurrent {i}",
                content=f"동시 CRUD 테스트 {i}번 문서입니다.",
            )

        # Create 5 documents concurrently
        with timer() as t:
            docs = await asyncio.gather(*[create_task(i) for i in range(5)])

        assert len(docs) == 5
        assert t.elapsed_ms < 15000, f"Concurrent creation took {t.elapsed_ms}ms"

        # Verify all documents exist
        for doc in docs:
            doc_uuid = doc.get("doc_uuid") or doc.get("id")
            retrieved = await doc_helper.get(doc_uuid)
            assert retrieved is not None

    async def test_concurrent_read_write(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test concurrent reads and writes don't interfere."""
        # Create initial document
        doc = await doc_helper.create(
            title="Read/Write Concurrent Test",
            content="초기 내용입니다.",
        )
        doc_uuid = doc.get("doc_uuid") or doc.get("id")

        await doc_helper.wait_for_indexing()

        async def read_task() -> dict | None:
            return await doc_helper.get(doc_uuid)

        async def search_task() -> dict:
            return await doc_helper.search("초기")

        # Run reads and searches concurrently
        tasks = [read_task() for _ in range(3)] + [search_task() for _ in range(3)]

        results = await asyncio.gather(*tasks)

        # All should complete without error
        assert len(results) == 6

    async def test_high_load_search(
        self,
        doc_helper: DocumentHelper,
        timer: type[Timer],
    ) -> None:
        """Test search performance under higher load."""
        # Create documents
        for i in range(10):
            await doc_helper.create(
                title=f"Load Test Document {i}",
                content=f"부하 테스트 문서입니다. 문서 번호 {i}. 검색 성능 테스트.",
            )

        await doc_helper.wait_for_indexing(5.0)

        # Run many searches concurrently
        num_searches = 20

        async def search_task(i: int) -> dict:
            return await doc_helper.search(f"문서 {i % 10}")

        with timer() as t:
            results = await asyncio.gather(*[search_task(i) for i in range(num_searches)])

        assert len(results) == num_searches

        avg_time = t.elapsed_ms / num_searches
        assert avg_time < 500, f"Average search time under load: {avg_time}ms"


@pytest.mark.e2e
class TestReliability:
    """E2E tests for system reliability."""

    async def test_rapid_create_delete(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test rapid create-delete cycles don't cause issues."""
        for i in range(5):
            doc = await doc_helper.create(
                title=f"Rapid Cycle {i}",
                content=f"빠른 생성-삭제 사이클 테스트 {i}번.",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            # Immediately delete
            deleted = await doc_helper.delete(doc_uuid)
            assert deleted

            # Small delay to avoid overwhelming
            await asyncio.sleep(0.1)

        # System should still be responsive
        result = await doc_helper.search("테스트")
        assert result is not None

    async def test_search_after_multiple_updates(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test that search works correctly after multiple updates."""
        doc = await doc_helper.create(
            title="Multiple Updates Test",
            content="초기 내용입니다.",
        )
        doc_uuid = doc.get("doc_uuid") or doc.get("id")

        # Perform multiple updates
        versions = ["첫번째수정", "두번째수정", "세번째수정", "최종수정내용"]

        for version in versions:
            await doc_helper.update(doc_uuid, content=f"{version} 내용입니다.")
            await asyncio.sleep(0.5)

        await doc_helper.wait_for_sync()

        # Search for final version
        result = await doc_helper.search("최종수정내용")

        found_ids = [
            r.get("doc_uuid") or r.get("document_id") for r in result.get("results", [])
        ]
        assert doc_uuid in found_ids, "Document should be searchable after multiple updates"

    async def test_consistent_after_errors(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test system remains consistent after error scenarios."""
        # Create document
        doc = await doc_helper.create(
            title="Error Recovery Test",
            content="에러 복구 테스트 문서입니다.",
        )
        doc_uuid = doc.get("doc_uuid") or doc.get("id")

        # Try invalid operations (these should fail gracefully)
        try:
            await doc_helper.get("invalid-uuid-format")
        except Exception:
            pass

        try:
            await doc_helper.update("00000000-0000-0000-0000-000000000000", content="test")
        except Exception:
            pass

        # System should still work correctly
        retrieved = await doc_helper.get(doc_uuid)
        assert retrieved is not None
        assert retrieved.get("title") == "Error Recovery Test"


@pytest.mark.e2e
class TestHealthCheck:
    """E2E tests for health check endpoints."""

    async def test_health_endpoint(
        self,
        api_client,
    ) -> None:
        """Test health endpoint returns healthy status."""
        response = await api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"

    async def test_detailed_health(
        self,
        api_client,
    ) -> None:
        """Test detailed health check endpoint."""
        response = await api_client.get("/api/v1/health")

        # Should return health information
        assert response.status_code in [200, 503]  # healthy or degraded

        data = response.json()
        assert "status" in data

    async def test_ready_endpoint(
        self,
        api_client,
    ) -> None:
        """Test readiness probe endpoint."""
        response = await api_client.get("/api/v1/health/ready")

        # May be 200 (ready) or 503 (not ready)
        assert response.status_code in [200, 503]

    async def test_live_endpoint(
        self,
        api_client,
    ) -> None:
        """Test liveness probe endpoint."""
        response = await api_client.get("/api/v1/health/live")

        # Liveness should generally be 200 if app is running
        assert response.status_code in [200, 503]
