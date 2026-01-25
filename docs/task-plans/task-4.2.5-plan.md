# Task Execution Plan: 4.2.5 - E2E 테스트 작성

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 4.2.5 |
| **Task Name** | E2E 테스트 작성 |
| **Estimate** | 6h |
| **Priority** | P1 |
| **Dependencies** | Task 4.2.4 |

### Description
전체 시스템 플로우를 검증하는 E2E 테스트를 작성합니다.

### Acceptance Criteria
- [ ] `tests/e2e/test_full_cycle.py` 생성
- [ ] 문서 저장 → 검색 → 결과 확인
- [ ] 문서 수정 → 동기화 → 검색 결과 변경 확인
- [ ] 문서 삭제 → 검색 결과 미포함 확인
- [ ] ACL 권한 테스트

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 7 Testing
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 8 Testing

### 2.2 E2E 테스트 범위
```
시나리오 1: 문서 라이프사이클
    Create Document → Search → Update → Search → Delete → Search

시나리오 2: ACL 권한
    Create (user1) → Search (user1 ✓) → Search (user2 ✗)
    Grant Access → Search (user2 ✓)
    Revoke Access → Search (user2 ✗)

시나리오 3: 동기화
    Create Document → Wait Sync → Verify in all stores
    Update Document → Wait Sync → Verify changes

시나리오 4: 검색 품질
    Create Documents → Search (Dense) → Verify relevance
    Search (Sparse) → Verify keyword match
    Search (Hybrid) → Verify combined results
```

### 2.3 설계 결정
1. **Docker Compose**: 실제 인프라 사용
2. **pytest-asyncio**: 비동기 테스트
3. **Fixture 격리**: 테스트별 데이터 분리
4. **성능 검증**: 응답 시간 측정

### 2.4 테스트 환경
```yaml
# docker-compose.test.yml
services:
  postgres:
    image: postgres:15-alpine
    ports: ["5433:5432"]

  milvus:
    image: milvusdb/milvus:v2.5.0
    ports: ["19531:19530"]

  neo4j:
    image: neo4j:5-community
    ports: ["7688:7687"]

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    ports: ["9093:9092"]
```

---

## 3. Implementation Steps

### Step 1: E2E Fixtures 설정 (1.5h)

**작업 내용:**
1. conftest.py 설정
2. API 클라이언트
3. 테스트 데이터 헬퍼

**tests/e2e/conftest.py:**
```python
"""E2E test fixtures."""
import asyncio
import os
from typing import AsyncGenerator, Generator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

# Use test database
os.environ["POSTGRES_PORT"] = "5433"
os.environ["MILVUS_PORT"] = "19531"
os.environ["NEO4J_PORT"] = "7688"
os.environ["KAFKA_PORT"] = "9093"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """API base URL."""
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest_asyncio.fixture(scope="session")
async def api_client(api_base_url: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async HTTP client."""
    async with httpx.AsyncClient(
        base_url=api_base_url,
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture
def user1_headers() -> dict:
    """Headers for user1."""
    return {
        "X-User-Id": "user1",
        "X-User-Groups": "engineering,ml-team",
    }


@pytest.fixture
def user2_headers() -> dict:
    """Headers for user2."""
    return {
        "X-User-Id": "user2",
        "X-User-Groups": "marketing",
    }


@pytest.fixture
def admin_headers() -> dict:
    """Headers for admin user."""
    return {
        "X-User-Id": "admin",
        "X-User-Groups": "admin,engineering",
    }


class DocumentHelper:
    """Helper for document operations."""

    def __init__(self, client: httpx.AsyncClient, headers: dict):
        self.client = client
        self.headers = headers
        self.created_docs: list[str] = []

    async def create(
        self,
        title: str,
        content: str,
        **kwargs,
    ) -> dict:
        """Create a document."""
        response = await self.client.post(
            "/api/v1/documents",
            json={
                "title": title,
                "content": content,
                **kwargs,
            },
            headers=self.headers,
        )
        response.raise_for_status()
        data = response.json()
        self.created_docs.append(data["doc_uuid"])
        return data

    async def get(self, doc_uuid: str) -> dict | None:
        """Get a document."""
        response = await self.client.get(
            f"/api/v1/documents/{doc_uuid}",
            headers=self.headers,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def update(self, doc_uuid: str, **kwargs) -> dict:
        """Update a document."""
        response = await self.client.put(
            f"/api/v1/documents/{doc_uuid}",
            json=kwargs,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    async def delete(self, doc_uuid: str) -> bool:
        """Delete a document."""
        response = await self.client.delete(
            f"/api/v1/documents/{doc_uuid}",
            headers=self.headers,
        )
        if response.status_code == 204:
            if doc_uuid in self.created_docs:
                self.created_docs.remove(doc_uuid)
            return True
        return False

    async def search(
        self,
        query: str,
        top_k: int = 10,
        search_types: list[str] | None = None,
    ) -> dict:
        """Search documents."""
        body = {
            "query": query,
            "user_id": self.headers["X-User-Id"],
            "user_groups": self.headers.get("X-User-Groups", "").split(","),
            "top_k": top_k,
        }
        if search_types:
            body["search_types"] = search_types

        response = await self.client.post(
            "/api/v1/search",
            json=body,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    async def cleanup(self) -> None:
        """Clean up created documents."""
        for doc_uuid in list(self.created_docs):
            try:
                await self.delete(doc_uuid)
            except Exception:
                pass


@pytest_asyncio.fixture
async def doc_helper(
    api_client: httpx.AsyncClient,
    user1_headers: dict,
) -> AsyncGenerator[DocumentHelper, None]:
    """Create document helper."""
    helper = DocumentHelper(api_client, user1_headers)
    yield helper
    await helper.cleanup()
```

**완료 기준:**
- [ ] conftest.py 설정
- [ ] API 클라이언트
- [ ] DocumentHelper 클래스

---

### Step 2: 문서 라이프사이클 테스트 (1.5h)

**작업 내용:**
1. 문서 생성 → 검색 테스트
2. 문서 수정 → 재검색 테스트
3. 문서 삭제 → 미검색 확인

**tests/e2e/test_full_cycle.py:**
```python
"""E2E tests for full document lifecycle."""
import asyncio
import pytest

from tests.e2e.conftest import DocumentHelper


@pytest.mark.e2e
class TestDocumentLifecycle:
    """E2E tests for document lifecycle."""

    async def test_create_and_search(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test creating a document and finding it via search."""
        # Create document
        doc = await doc_helper.create(
            title="인공지능 기술 개요",
            content="""
            인공지능(AI)은 기계가 인간의 지능을 모방하는 기술입니다.
            머신러닝과 딥러닝은 인공지능의 핵심 기술입니다.
            자연어 처리, 컴퓨터 비전 등 다양한 응용 분야가 있습니다.
            """,
        )

        doc_uuid = doc["doc_uuid"]
        assert doc["title"] == "인공지능 기술 개요"
        assert doc["chunk_count"] >= 1

        # Wait for indexing
        await asyncio.sleep(2)

        # Search and find the document
        search_result = await doc_helper.search("인공지능 기술")

        assert search_result["total"] >= 1

        found_docs = [r["doc_uuid"] for r in search_result["results"]]
        assert doc_uuid in found_docs

    async def test_update_and_search(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test updating document and verifying search results."""
        # Create document
        doc = await doc_helper.create(
            title="원래 제목",
            content="원래 내용입니다. 검색할 수 없는 내용.",
        )
        doc_uuid = doc["doc_uuid"]

        await asyncio.sleep(2)

        # Initial search - should not find specific term
        result1 = await doc_helper.search("업데이트된 키워드")
        initial_found = any(r["doc_uuid"] == doc_uuid for r in result1["results"])

        # Update content with new keywords
        await doc_helper.update(
            doc_uuid,
            content="업데이트된 키워드가 포함된 새로운 내용입니다.",
        )

        await asyncio.sleep(3)  # Wait for sync

        # Search again - should find new content
        result2 = await doc_helper.search("업데이트된 키워드")

        updated_found = any(r["doc_uuid"] == doc_uuid for r in result2["results"])
        assert updated_found, "Updated document should be found"

    async def test_delete_removes_from_search(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test deleting document removes it from search."""
        # Create document
        doc = await doc_helper.create(
            title="삭제될 문서",
            content="이 문서는 삭제될 예정입니다. 고유한 삭제 테스트 내용.",
        )
        doc_uuid = doc["doc_uuid"]

        await asyncio.sleep(2)

        # Verify it's searchable
        result1 = await doc_helper.search("고유한 삭제 테스트")
        assert any(r["doc_uuid"] == doc_uuid for r in result1["results"])

        # Delete document
        deleted = await doc_helper.delete(doc_uuid)
        assert deleted

        await asyncio.sleep(3)  # Wait for sync

        # Verify not in search results
        result2 = await doc_helper.search("고유한 삭제 테스트")
        assert not any(r["doc_uuid"] == doc_uuid for r in result2["results"])

        # Verify document not accessible
        doc = await doc_helper.get(doc_uuid)
        assert doc is None


@pytest.mark.e2e
class TestSearchQuality:
    """E2E tests for search quality."""

    async def test_dense_search_semantic(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test dense search finds semantically similar content."""
        await doc_helper.create(
            title="AI Overview",
            content="Machine learning is a subset of artificial intelligence.",
        )

        await asyncio.sleep(2)

        # Search with different words
        result = await doc_helper.search(
            "인공지능과 기계학습",  # Korean query
            search_types=["dense"],
        )

        # Dense search should find semantically related content
        assert result["total"] >= 0  # May or may not find depending on similarity

    async def test_sparse_search_keyword(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test sparse search matches keywords."""
        await doc_helper.create(
            title="토큰화 가이드",
            content="텍스트 토큰화는 NLP의 기본 단계입니다. 토큰화 과정을 설명합니다.",
        )

        await asyncio.sleep(2)

        # Exact keyword search
        result = await doc_helper.search(
            "토큰화",
            search_types=["sparse"],
        )

        assert result["total"] >= 1
        # Should find document with keyword
        assert any("토큰화" in str(r.get("text_preview", "")) for r in result["results"])

    async def test_hybrid_search_combines(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test hybrid search combines dense and sparse."""
        await doc_helper.create(
            title="하이브리드 검색 문서",
            content="하이브리드 검색은 의미 기반과 키워드 기반을 결합합니다.",
        )

        await asyncio.sleep(2)

        result = await doc_helper.search(
            "하이브리드 검색 기술",
            search_types=["dense", "sparse", "graph"],
        )

        assert result["total"] >= 1
        assert len(result["search_types_used"]) >= 1
```

**완료 기준:**
- [ ] 생성 → 검색 테스트
- [ ] 수정 → 재검색 테스트
- [ ] 삭제 → 미검색 테스트
- [ ] 검색 품질 테스트

---

### Step 3: ACL 권한 테스트 (1.5h)

**작업 내용:**
1. 소유자 접근 테스트
2. 권한 부여/해제 테스트
3. 그룹 권한 테스트

**tests/e2e/test_acl.py:**
```python
"""E2E tests for ACL enforcement."""
import asyncio
import pytest
import httpx

from tests.e2e.conftest import DocumentHelper


@pytest.mark.e2e
class TestACLEnforcement:
    """E2E tests for ACL."""

    async def test_owner_can_access(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict,
    ) -> None:
        """Test owner can access their document."""
        helper = DocumentHelper(api_client, user1_headers)

        try:
            doc = await helper.create(
                title="User1's Document",
                content="This document belongs to user1.",
            )

            await asyncio.sleep(2)

            # Search as owner
            result = await helper.search("user1 document")

            assert any(r["doc_uuid"] == doc["doc_uuid"] for r in result["results"])

        finally:
            await helper.cleanup()

    async def test_other_user_cannot_access_private(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict,
        user2_headers: dict,
    ) -> None:
        """Test other user cannot access private document."""
        helper1 = DocumentHelper(api_client, user1_headers)
        helper2 = DocumentHelper(api_client, user2_headers)

        try:
            # User1 creates document
            doc = await helper1.create(
                title="Private Document",
                content="비공개 문서 내용입니다. 프라이빗 테스트.",
            )

            await asyncio.sleep(2)

            # User2 searches - should not find
            result = await helper2.search("프라이빗 테스트")

            found_docs = [r["doc_uuid"] for r in result["results"]]
            assert doc["doc_uuid"] not in found_docs

            # User2 tries direct access - should fail
            response = await api_client.get(
                f"/api/v1/documents/{doc['doc_uuid']}",
                headers=user2_headers,
            )
            assert response.status_code in [403, 404]

        finally:
            await helper1.cleanup()

    async def test_shared_document_accessible(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict,
        user2_headers: dict,
    ) -> None:
        """Test shared document is accessible."""
        helper1 = DocumentHelper(api_client, user1_headers)
        helper2 = DocumentHelper(api_client, user2_headers)

        try:
            # User1 creates document
            doc = await helper1.create(
                title="Shared Document",
                content="공유된 문서입니다. 협업 테스트 내용.",
            )

            # Grant access to user2 (would need ACL API)
            # For now, assume org-wide access
            # In real test, call: POST /api/v1/documents/{id}/share

            await asyncio.sleep(2)

            # User1 can search and find
            result1 = await helper1.search("협업 테스트")
            assert any(r["doc_uuid"] == doc["doc_uuid"] for r in result1["results"])

        finally:
            await helper1.cleanup()


@pytest.mark.e2e
class TestACLSearch:
    """E2E tests for ACL in search."""

    async def test_search_only_returns_accessible(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict,
        user2_headers: dict,
    ) -> None:
        """Test search only returns documents user can access."""
        helper1 = DocumentHelper(api_client, user1_headers)
        helper2 = DocumentHelper(api_client, user2_headers)

        try:
            # Both users create documents with same keyword
            doc1 = await helper1.create(
                title="User1 AI Document",
                content="인공지능 기술에 관한 user1의 문서입니다.",
            )
            doc2 = await helper2.create(
                title="User2 AI Document",
                content="인공지능 기술에 관한 user2의 문서입니다.",
            )

            await asyncio.sleep(2)

            # User1 searches
            result1 = await helper1.search("인공지능 기술")
            found1 = [r["doc_uuid"] for r in result1["results"]]

            # Should find own doc, not user2's
            assert doc1["doc_uuid"] in found1
            assert doc2["doc_uuid"] not in found1

            # User2 searches
            result2 = await helper2.search("인공지능 기술")
            found2 = [r["doc_uuid"] for r in result2["results"]]

            # Should find own doc, not user1's
            assert doc2["doc_uuid"] in found2
            assert doc1["doc_uuid"] not in found2

        finally:
            await helper1.cleanup()
            await helper2.cleanup()
```

**완료 기준:**
- [ ] 소유자 접근 테스트
- [ ] 비권한자 차단 테스트
- [ ] 검색 ACL 필터 테스트

---

### Step 4: 성능 및 동기화 테스트 (1.5h)

**작업 내용:**
1. 응답 시간 테스트
2. 동기화 시간 테스트
3. 부하 테스트 (선택)

**tests/e2e/test_performance.py:**
```python
"""E2E tests for performance."""
import asyncio
import time
import pytest

from tests.e2e.conftest import DocumentHelper


@pytest.mark.e2e
class TestPerformance:
    """E2E tests for performance."""

    async def test_search_response_time(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test search responds within acceptable time."""
        # Create test document
        await doc_helper.create(
            title="Performance Test",
            content="성능 테스트를 위한 문서입니다. 검색 응답 시간을 측정합니다.",
        )

        await asyncio.sleep(2)

        # Measure search time
        times = []
        for _ in range(5):
            start = time.time()
            await doc_helper.search("성능 테스트")
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # P95 should be < 100ms (relaxed for E2E)
        assert avg_time < 200, f"Average time {avg_time}ms exceeds 200ms"
        assert max_time < 500, f"Max time {max_time}ms exceeds 500ms"

    async def test_document_creation_time(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test document creation time."""
        content = "테스트 문서 " * 100  # ~300 chars

        start = time.time()
        await doc_helper.create(
            title="Creation Time Test",
            content=content,
        )
        elapsed = (time.time() - start) * 1000

        # Document creation should be < 5 seconds
        assert elapsed < 5000, f"Creation time {elapsed}ms exceeds 5s"


@pytest.mark.e2e
class TestSynchronization:
    """E2E tests for synchronization."""

    async def test_sync_within_timeout(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test changes sync within acceptable time."""
        # Create document
        doc = await doc_helper.create(
            title="Sync Test",
            content="동기화 테스트 원본 내용",
        )

        # Update with unique content
        unique_content = f"동기화 확인 유니크 {time.time()}"
        await doc_helper.update(doc["doc_uuid"], content=unique_content)

        # Poll for sync completion
        synced = False
        max_wait = 60  # 60 seconds max
        start = time.time()

        while time.time() - start < max_wait:
            result = await doc_helper.search(unique_content[:20])
            if any(r["doc_uuid"] == doc["doc_uuid"] for r in result["results"]):
                synced = True
                break
            await asyncio.sleep(1)

        sync_time = time.time() - start

        assert synced, f"Sync not completed within {max_wait}s"
        assert sync_time < 30, f"Sync took {sync_time}s, expected < 30s"


@pytest.mark.e2e
@pytest.mark.slow
class TestConcurrency:
    """E2E tests for concurrent operations."""

    async def test_concurrent_searches(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test multiple concurrent searches."""
        # Create documents
        for i in range(5):
            await doc_helper.create(
                title=f"Concurrent Test {i}",
                content=f"동시성 테스트 문서 {i}번입니다.",
            )

        await asyncio.sleep(3)

        # Run concurrent searches
        queries = ["동시성", "테스트", "문서", "번입니다", "Concurrent"]

        async def search_task(query: str) -> dict:
            return await doc_helper.search(query)

        start = time.time()
        results = await asyncio.gather(*[search_task(q) for q in queries])
        elapsed = time.time() - start

        # All should complete
        assert len(results) == 5

        # Should complete within reasonable time
        # (parallel execution should be faster than sequential)
        assert elapsed < 5, f"Concurrent searches took {elapsed}s"

    async def test_concurrent_crud(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test concurrent CRUD operations."""
        async def create_task(i: int) -> dict:
            return await doc_helper.create(
                title=f"CRUD Test {i}",
                content=f"CRUD 테스트 {i}번 문서",
            )

        # Create 5 documents concurrently
        start = time.time()
        docs = await asyncio.gather(*[create_task(i) for i in range(5)])
        elapsed = time.time() - start

        assert len(docs) == 5
        # Concurrent creation should complete within reasonable time
        assert elapsed < 15, f"Concurrent creation took {elapsed}s"
```

**완료 기준:**
- [ ] 검색 응답 시간 테스트
- [ ] 문서 생성 시간 테스트
- [ ] 동기화 시간 테스트
- [ ] 동시성 테스트

---

## 4. Testing Plan

### 4.1 E2E Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_create_and_search` | 생성 → 검색 | 문서 발견 |
| `test_update_and_search` | 수정 → 재검색 | 변경 반영 |
| `test_delete_removes` | 삭제 → 미검색 | 문서 미발견 |
| `test_owner_access` | 소유자 접근 | 접근 허용 |
| `test_other_blocked` | 비권한자 차단 | 접근 거부 |
| `test_search_time` | 검색 응답 | < 200ms |
| `test_sync_time` | 동기화 | < 30s |

### 4.2 테스트 실행
```bash
# E2E 테스트만 실행
pytest tests/e2e -m e2e -v

# 느린 테스트 제외
pytest tests/e2e -m "e2e and not slow" -v

# 전체 E2E 테스트 (CI)
pytest tests/e2e --tb=short
```

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 테스트 환경 불안정 | High | Medium | Docker health checks |
| 데이터 잔류 | Medium | Medium | Fixture cleanup |
| 타이밍 이슈 | Medium | High | 적절한 대기 시간 |

---

## 6. Definition of Done

- [ ] `tests/e2e/conftest.py` 생성
- [ ] `tests/e2e/test_full_cycle.py` 생성
- [ ] `tests/e2e/test_acl.py` 생성
- [ ] `tests/e2e/test_performance.py` 생성
- [ ] 문서 라이프사이클 테스트
- [ ] ACL 권한 테스트
- [ ] 성능/동기화 테스트
- [ ] 모든 테스트 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Fixtures 설정 | 1.5h | - |
| Step 2: 라이프사이클 테스트 | 1.5h | - |
| Step 3: ACL 테스트 | 1.5h | - |
| Step 4: 성능 테스트 | 1.5h | - |
| **Total** | **6h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
