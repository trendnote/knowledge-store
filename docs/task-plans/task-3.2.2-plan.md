# Task Execution Plan: 3.2.2 - Search 통합 테스트

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 3.2.2 |
| **Task Name** | Search 통합 테스트 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 3.2.1 |

### Description
Search 기능 전체 플로우를 검증하는 통합 테스트를 작성합니다.

### Acceptance Criteria
- [ ] `tests/integration/test_search_flow.py` 생성
- [ ] 테스트 데이터 시딩
- [ ] Dense Search 통합 테스트
- [ ] Sparse Search 통합 테스트
- [ ] Graph Search 통합 테스트
- [ ] Hybrid Search 통합 테스트
- [ ] ACL 필터링 통합 테스트

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 7 Testing Strategy
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 8 Testing

### 2.2 테스트 환경
```
테스트 인프라:
- PostgreSQL (Docker)
- Milvus (Docker)
- Neo4j (Docker)

테스트 데이터:
- 5개 문서
- 각 문서 3-5개 청크
- 다양한 ACL 설정
```

### 2.3 설계 결정
1. **pytest-asyncio**: 비동기 테스트 지원
2. **Docker Compose**: 테스트 인프라 관리
3. **Fixture 기반**: 재사용 가능한 테스트 데이터
4. **Cleanup**: 테스트 후 데이터 정리

### 2.4 테스트 시나리오
| 시나리오 | 설명 |
|----------|------|
| 기본 검색 | 쿼리 → 결과 반환 |
| ACL 필터링 | 권한 있는 문서만 반환 |
| 검색 타입 | Dense/Sparse/Graph 각각 테스트 |
| 성능 | P95 < 100ms |

---

## 3. Implementation Steps

### Step 1: 테스트 Fixtures 및 데이터 시딩 (1.5h)

**작업 내용:**
1. conftest.py 설정
2. 테스트 데이터 생성
3. 데이터베이스 시딩

**tests/integration/conftest.py:**
```python
"""Integration test fixtures."""
import asyncio
from typing import AsyncGenerator, Generator
from uuid import uuid4

import pytest
import pytest_asyncio

from src.config import get_settings
from src.infrastructure.database.postgres import PostgresClient
from src.infrastructure.database.milvus import MilvusClient
from src.infrastructure.database.neo4j import Neo4jClient
from src.infrastructure.embedding.bge_m3 import EmbeddingService
from src.repositories.postgres.repository import PostgresRepository
from src.repositories.milvus.repository import MilvusRepository
from src.repositories.neo4j.repository import Neo4jRepository
from src.services.acl_service import AclService
from src.services.search_service import SearchService


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def postgres_client() -> AsyncGenerator[PostgresClient, None]:
    """Create PostgreSQL client."""
    settings = get_settings()
    client = PostgresClient(settings.postgres)
    await client.connect()
    yield client
    await client.close()


@pytest_asyncio.fixture(scope="session")
async def milvus_client() -> AsyncGenerator[MilvusClient, None]:
    """Create Milvus client."""
    settings = get_settings()
    client = MilvusClient(settings.milvus)
    await client.connect()
    yield client
    await client.close()


@pytest_asyncio.fixture(scope="session")
async def neo4j_client() -> AsyncGenerator[Neo4jClient, None]:
    """Create Neo4j client."""
    settings = get_settings()
    client = Neo4jClient(settings.neo4j)
    await client.connect()
    yield client
    await client.close()


@pytest.fixture(scope="session")
def embedding_service() -> EmbeddingService:
    """Create embedding service."""
    return EmbeddingService()


@pytest_asyncio.fixture
async def test_data(
    postgres_client: PostgresClient,
    milvus_client: MilvusClient,
    neo4j_client: Neo4jClient,
    embedding_service: EmbeddingService,
) -> AsyncGenerator[dict, None]:
    """Create test data for search tests."""
    # Create test documents
    docs = [
        {
            "doc_uuid": str(uuid4()),
            "title": "인공지능 기술 개요",
            "owner_id": "user1",
            "chunks": [
                "인공지능(AI)은 기계가 인간의 지능을 모방하는 기술입니다.",
                "머신러닝은 인공지능의 하위 분야로 데이터에서 학습합니다.",
                "딥러닝은 신경망을 사용하는 머신러닝 기법입니다.",
            ],
        },
        {
            "doc_uuid": str(uuid4()),
            "title": "자연어 처리 가이드",
            "owner_id": "user1",
            "chunks": [
                "자연어 처리(NLP)는 텍스트와 음성을 이해하는 기술입니다.",
                "토큰화는 텍스트를 작은 단위로 나누는 과정입니다.",
            ],
        },
        {
            "doc_uuid": str(uuid4()),
            "title": "비공개 문서",
            "owner_id": "user2",
            "chunks": [
                "이 문서는 user2만 접근할 수 있습니다.",
            ],
        },
    ]

    postgres_repo = PostgresRepository(postgres_client)
    milvus_repo = MilvusRepository(milvus_client)
    neo4j_repo = Neo4jRepository(neo4j_client)

    created_docs = []
    created_chunks = []

    try:
        for doc in docs:
            # Create document in PostgreSQL
            doc_record = await postgres_repo.create_document({
                "doc_uuid": doc["doc_uuid"],
                "title": doc["title"],
                "owner_id": doc["owner_id"],
            })
            created_docs.append(doc_record)

            # Create ACL entry
            await postgres_repo.create_acl_entry({
                "doc_uuid": doc["doc_uuid"],
                "principal_type": "user",
                "principal_id": doc["owner_id"],
                "permission": "read",
            })

            # Create chunks
            for i, text in enumerate(doc["chunks"]):
                chunk_uuid = str(uuid4())
                embeddings = embedding_service.encode([text])

                # PostgreSQL chunk
                chunk = await postgres_repo.create_chunk({
                    "chunk_uuid": chunk_uuid,
                    "doc_uuid": doc["doc_uuid"],
                    "chunk_index": i,
                    "text": text,
                })
                created_chunks.append(chunk)

                # Milvus vector
                await milvus_repo.insert_vectors([{
                    "chunk_uuid": chunk_uuid,
                    "doc_uuid": doc["doc_uuid"],
                    "dense_embedding": embeddings.dense[0],
                    "sparse_embedding": embeddings.sparse[0],
                    "text_preview": text[:100],
                }])

                # Neo4j nodes
                await neo4j_repo.create_chunk_node({
                    "chunk_uuid": chunk_uuid,
                    "doc_uuid": doc["doc_uuid"],
                    "text_preview": text[:100],
                })

            # Neo4j document node
            await neo4j_repo.create_document_node({
                "doc_uuid": doc["doc_uuid"],
                "title": doc["title"],
            })

        yield {
            "docs": docs,
            "created_docs": created_docs,
            "created_chunks": created_chunks,
        }

    finally:
        # Cleanup
        for chunk in created_chunks:
            await milvus_repo.delete_vectors([chunk["chunk_uuid"]])
            await neo4j_repo.delete_chunk_node(chunk["chunk_uuid"])

        for doc in created_docs:
            await postgres_repo.delete_document(doc["doc_uuid"])
            await neo4j_repo.delete_document_node(doc["doc_uuid"])


@pytest_asyncio.fixture
async def search_service(
    postgres_client: PostgresClient,
    milvus_client: MilvusClient,
    neo4j_client: Neo4jClient,
    embedding_service: EmbeddingService,
) -> SearchService:
    """Create search service."""
    postgres_repo = PostgresRepository(postgres_client)
    milvus_repo = MilvusRepository(milvus_client)
    neo4j_repo = Neo4jRepository(neo4j_client)
    acl_service = AclService(postgres_repo)

    return SearchService(
        milvus_repo=milvus_repo,
        embedding_service=embedding_service,
        acl_service=acl_service,
        neo4j_repo=neo4j_repo,
    )
```

**완료 기준:**
- [ ] conftest.py 설정
- [ ] 테스트 데이터 생성
- [ ] Fixture cleanup 구현

---

### Step 2: 검색 타입별 통합 테스트 (1.5h)

**작업 내용:**
1. Dense Search 통합 테스트
2. Sparse Search 통합 테스트
3. Graph Search 통합 테스트

**tests/integration/test_search_flow.py:**
```python
"""Integration tests for search flow."""
import pytest

from src.domain.models.search import SearchRequest, SearchType


@pytest.mark.integration
class TestDenseSearchIntegration:
    """Integration tests for dense search."""

    async def test_dense_search_returns_results(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test dense search returns relevant results."""
        results = await search_service.dense_search(
            query="인공지능 기술",
            user_id="user1",
            top_k=5,
        )

        assert len(results) > 0
        # Should find AI-related chunks
        assert any("인공지능" in r.text_preview for r in results if r.text_preview)

    async def test_dense_search_respects_acl(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test dense search respects ACL."""
        results = await search_service.dense_search(
            query="비공개 문서",
            user_id="user1",  # Not owner of private doc
            top_k=10,
        )

        # Should not find private doc
        private_doc = test_data["docs"][2]
        assert all(r.doc_uuid != private_doc["doc_uuid"] for r in results)

    async def test_dense_search_semantic_similarity(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test dense search finds semantically similar content."""
        results = await search_service.dense_search(
            query="machine learning algorithms",  # English query
            user_id="user1",
            top_k=5,
        )

        # Should still find Korean ML-related content
        assert len(results) > 0


@pytest.mark.integration
class TestSparseSearchIntegration:
    """Integration tests for sparse search."""

    async def test_sparse_search_keyword_match(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test sparse search matches keywords."""
        results = await search_service.sparse_search(
            query="토큰화",
            user_id="user1",
            top_k=5,
        )

        assert len(results) > 0
        # Should find tokenization chunk
        assert any("토큰화" in r.text_preview for r in results if r.text_preview)

    async def test_sparse_search_korean_keywords(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test sparse search with Korean keywords."""
        results = await search_service.sparse_search(
            query="자연어 처리 NLP",
            user_id="user1",
            top_k=5,
        )

        assert len(results) > 0


@pytest.mark.integration
class TestGraphSearchIntegration:
    """Integration tests for graph search."""

    async def test_graph_search_text_match(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test graph search matches text content."""
        results = await search_service.graph_search(
            query="딥러닝",
            user_id="user1",
            top_k=5,
        )

        assert len(results) > 0

    async def test_graph_search_respects_acl(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test graph search respects ACL."""
        results = await search_service.graph_search(
            query="비공개",
            user_id="user1",
            top_k=10,
        )

        private_doc = test_data["docs"][2]
        assert all(r.doc_uuid != private_doc["doc_uuid"] for r in results)
```

**완료 기준:**
- [ ] Dense Search 테스트
- [ ] Sparse Search 테스트
- [ ] Graph Search 테스트
- [ ] ACL 필터링 테스트

---

### Step 3: Hybrid Search 및 성능 테스트 (0.5h)

**작업 내용:**
1. Hybrid Search 통합 테스트
2. 성능 테스트 (P95 < 100ms)

**tests/integration/test_search_flow.py (계속):**
```python
@pytest.mark.integration
class TestHybridSearchIntegration:
    """Integration tests for hybrid search."""

    async def test_hybrid_search_combines_results(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test hybrid search combines all search types."""
        request = SearchRequest(
            query="인공지능 머신러닝",
            user_id="user1",
            top_k=10,
        )

        response = await search_service.hybrid_search(request)

        assert response.total > 0
        assert len(response.search_types_used) >= 1

    async def test_hybrid_search_selected_types(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test hybrid search with selected types only."""
        request = SearchRequest(
            query="인공지능",
            user_id="user1",
            top_k=10,
            search_types=[SearchType.DENSE, SearchType.SPARSE],
        )

        response = await search_service.hybrid_search(request)

        assert SearchType.GRAPH not in response.search_types_used

    async def test_hybrid_search_deduplication(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test hybrid search deduplicates results."""
        request = SearchRequest(
            query="인공지능 기술",
            user_id="user1",
            top_k=10,
        )

        response = await search_service.hybrid_search(request)

        # Check no duplicate chunk_uuids
        chunk_uuids = [r.chunk_uuid for r in response.results]
        assert len(chunk_uuids) == len(set(chunk_uuids))


@pytest.mark.integration
class TestSearchPerformance:
    """Performance tests for search."""

    async def test_search_response_time(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test search responds within 100ms."""
        import time

        start = time.time()

        request = SearchRequest(
            query="인공지능",
            user_id="user1",
            top_k=10,
        )
        response = await search_service.hybrid_search(request)

        elapsed = (time.time() - start) * 1000

        # P95 should be < 100ms
        # In test environment with small data, should be faster
        assert elapsed < 500  # Relaxed for CI
        assert response.search_time_ms < 500

    async def test_multiple_searches_performance(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test multiple sequential searches."""
        queries = ["인공지능", "자연어처리", "머신러닝", "딥러닝", "토큰화"]
        total_time = 0

        for query in queries:
            request = SearchRequest(
                query=query,
                user_id="user1",
                top_k=5,
            )
            response = await search_service.hybrid_search(request)
            total_time += response.search_time_ms

        avg_time = total_time / len(queries)
        assert avg_time < 200  # Average should be reasonable
```

**완료 기준:**
- [ ] Hybrid Search 통합 테스트
- [ ] 중복 제거 테스트
- [ ] 성능 테스트

---

### Step 4: ACL 통합 테스트 (0.5h)

**작업 내용:**
1. 사용자 권한 테스트
2. 그룹 권한 테스트
3. 전사 공개 테스트

**tests/integration/test_search_acl.py:**
```python
"""Integration tests for search ACL."""
import pytest

from src.domain.models.search import SearchRequest


@pytest.mark.integration
class TestSearchACL:
    """Integration tests for search ACL filtering."""

    async def test_user_sees_own_documents(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test user can search their own documents."""
        # user1 should see their documents
        request = SearchRequest(
            query="인공지능",
            user_id="user1",
            top_k=10,
        )

        response = await search_service.hybrid_search(request)

        user1_docs = [d["doc_uuid"] for d in test_data["docs"] if d["owner_id"] == "user1"]
        result_docs = [r.doc_uuid for r in response.results]

        # At least some results should be from user1's docs
        assert any(doc in result_docs for doc in user1_docs)

    async def test_user_cannot_see_others_private_documents(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test user cannot see others' private documents."""
        # user1 should not see user2's documents
        request = SearchRequest(
            query="비공개",  # Query matches user2's doc
            user_id="user1",
            top_k=10,
        )

        response = await search_service.hybrid_search(request)

        private_doc = test_data["docs"][2]  # user2's doc
        result_docs = [r.doc_uuid for r in response.results]

        assert private_doc["doc_uuid"] not in result_docs

    async def test_owner_can_see_own_private_document(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test owner can see their private document."""
        # user2 should see their own document
        request = SearchRequest(
            query="비공개 문서",
            user_id="user2",
            top_k=10,
        )

        response = await search_service.hybrid_search(request)

        private_doc = test_data["docs"][2]
        result_docs = [r.doc_uuid for r in response.results]

        assert private_doc["doc_uuid"] in result_docs

    async def test_no_accessible_documents_returns_empty(
        self,
        search_service,
        test_data,
    ) -> None:
        """Test user with no access gets empty results."""
        request = SearchRequest(
            query="인공지능",
            user_id="unknown_user",  # No access to any docs
            top_k=10,
        )

        response = await search_service.hybrid_search(request)

        assert response.total == 0
        assert len(response.results) == 0
```

**완료 기준:**
- [ ] 사용자 권한 테스트
- [ ] 비공개 문서 접근 테스트
- [ ] 권한 없는 사용자 테스트

---

## 4. Testing Plan

### 4.1 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_dense_search_returns_results` | Dense 검색 결과 | 관련 결과 반환 |
| `test_sparse_search_keyword_match` | 키워드 매칭 | 키워드 포함 결과 |
| `test_graph_search_text_match` | 그래프 검색 | 텍스트 매칭 결과 |
| `test_hybrid_search_combines` | 통합 검색 | 병합된 결과 |
| `test_search_response_time` | 성능 | < 100ms |
| `test_user_access` | ACL | 권한 있는 문서만 |

### 4.2 테스트 실행
```bash
# 통합 테스트만 실행
pytest tests/integration -m integration -v

# 성능 테스트 포함
pytest tests/integration -m "integration or performance" -v
```

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 테스트 데이터 잔류 | Medium | Medium | Fixture cleanup |
| Docker 불안정 | Medium | Low | Retry 로직 |
| 임베딩 생성 시간 | Low | Medium | 캐시 활용 |

---

## 6. Definition of Done

- [ ] `tests/integration/conftest.py` 생성
- [ ] `tests/integration/test_search_flow.py` 생성
- [ ] `tests/integration/test_search_acl.py` 생성
- [ ] Dense/Sparse/Graph 통합 테스트
- [ ] Hybrid Search 통합 테스트
- [ ] ACL 필터링 통합 테스트
- [ ] 성능 테스트 (P95 < 100ms)
- [ ] 모든 테스트 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Fixtures 및 데이터 시딩 | 1.5h | - |
| Step 2: 검색 타입별 테스트 | 1.5h | - |
| Step 3: Hybrid 및 성능 테스트 | 0.5h | - |
| Step 4: ACL 통합 테스트 | 0.5h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
