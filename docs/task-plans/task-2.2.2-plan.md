# Task Execution Plan: 2.2.2 - Milvus Repository 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.2.2 |
| **Task Name** | Milvus Repository 구현 |
| **Estimate** | 6h |
| **Priority** | P0 |
| **Dependencies** | Task 2.1.2 |

### Description
Milvus 벡터 데이터 접근 레이어를 구현합니다.

### Acceptance Criteria
- [ ] `src/repositories/milvus/repository.py` 생성
- [ ] Vector Insert 메서드
- [ ] Vector Delete 메서드
- [ ] Dense Search 메서드
- [ ] Sparse Search 메서드
- [ ] Hybrid Search 메서드

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.3 Repository Layer
- **Schema**: `docs/architecture/architecture.md` Section 6.2 Milvus Collection Schema

### 2.2 Collection 스키마
```
knowledge_chunks:
  - chunk_uuid (VARCHAR, PK)
  - doc_uuid (VARCHAR)
  - dense_embedding (FLOAT_VECTOR[1024])
  - sparse_embedding (SPARSE_FLOAT_VECTOR)
  - chunk_text (VARCHAR)
  - section_path (VARCHAR)
  - security_level (VARCHAR)
  - allowed_groups (ARRAY<VARCHAR>)
  - created_at (INT64)
```

### 2.3 설계 결정
1. **MilvusClient 활용**: Infrastructure layer 클라이언트 사용
2. **Filter Expression**: ACL 기반 doc_uuid 필터링
3. **Batch Insert**: 대량 삽입 최적화
4. **Async Wrapper**: 동기 SDK를 async로 래핑

### 2.4 클래스 구조
```
MilvusRepository
├── __init__(client: MilvusClient)
├── Vector CRUD
│   ├── insert_chunks(chunks: list[MilvusChunk]) -> list[str]
│   ├── delete_by_chunk_uuids(chunk_uuids) -> int
│   └── delete_by_doc_uuid(doc_uuid) -> int
├── Search
│   ├── dense_search(vector, filter, top_k) -> list[SearchHit]
│   ├── sparse_search(sparse, filter, top_k) -> list[SearchHit]
│   └── hybrid_search(dense, sparse, filter, top_k) -> list[SearchHit]
└── Utils
    └── build_filter_expr(doc_uuids) -> str
```

---

## 3. Implementation Steps

### Step 1: Domain Models 및 기본 구조 (1h)

**작업 내용:**
1. MilvusChunk 데이터 클래스
2. SearchHit 결과 클래스
3. Repository 기본 구조

**src/domain/search.py:**
```python
"""Search-related domain models."""
from dataclasses import dataclass
from typing import Any


@dataclass
class MilvusChunk:
    """Chunk data for Milvus insertion."""

    chunk_uuid: str
    doc_uuid: str
    dense_embedding: list[float]
    sparse_embedding: dict[str, float]
    chunk_text: str
    section_path: str | None = None
    security_level: str = "internal"
    allowed_groups: list[str] | None = None
    created_at: int | None = None  # Unix timestamp


@dataclass
class SearchHit:
    """Search result hit."""

    chunk_uuid: str
    doc_uuid: str
    score: float
    distance: float
    chunk_text: str
    section_path: str | None = None
    search_type: str = "dense"  # dense, sparse, hybrid
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_milvus_hit(cls, hit: dict, search_type: str = "dense") -> "SearchHit":
        """Create from Milvus search result."""
        return cls(
            chunk_uuid=hit.get("chunk_uuid") or hit.get("id"),
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
```

**src/repositories/milvus/repository.py:**
```python
"""Milvus repository for vector operations."""
import time
from typing import Any

from src.domain.search import MilvusChunk, SearchHit
from src.infrastructure.database.milvus import MilvusClient


class MilvusRepository:
    """Milvus data access layer for vector operations."""

    def __init__(self, client: MilvusClient) -> None:
        """Initialize repository.

        Args:
            client: Milvus client
        """
        self._client = client

    # Output fields for search
    OUTPUT_FIELDS = [
        "chunk_uuid",
        "doc_uuid",
        "chunk_text",
        "section_path",
        "security_level",
        "allowed_groups",
    ]
```

**완료 기준:**
- [ ] MilvusChunk 모델 정의
- [ ] SearchHit 모델 정의
- [ ] Repository 기본 구조

---

### Step 2: Insert/Delete 메서드 구현 (1.5h)

**작업 내용:**
1. insert_chunks - 벡터 삽입
2. delete_by_chunk_uuids - 청크 ID로 삭제
3. delete_by_doc_uuid - 문서 ID로 삭제

**src/repositories/milvus/repository.py (계속):**
```python
    async def insert_chunks(self, chunks: list[MilvusChunk]) -> list[str]:
        """Insert chunks into Milvus.

        Args:
            chunks: List of chunks to insert

        Returns:
            List of inserted chunk UUIDs
        """
        if not chunks:
            return []

        # Prepare data in column format
        data = {
            "chunk_uuid": [],
            "doc_uuid": [],
            "dense_embedding": [],
            "sparse_embedding": [],
            "chunk_text": [],
            "section_path": [],
            "security_level": [],
            "allowed_groups": [],
            "created_at": [],
        }

        current_time = int(time.time())

        for chunk in chunks:
            data["chunk_uuid"].append(chunk.chunk_uuid)
            data["doc_uuid"].append(chunk.doc_uuid)
            data["dense_embedding"].append(chunk.dense_embedding)
            data["sparse_embedding"].append(chunk.sparse_embedding)
            data["chunk_text"].append(chunk.chunk_text[:8000])  # Max length
            data["section_path"].append(chunk.section_path or "")
            data["security_level"].append(chunk.security_level)
            data["allowed_groups"].append(chunk.allowed_groups or [])
            data["created_at"].append(chunk.created_at or current_time)

        # Insert using async wrapper
        result = await self._client.insert_async(data)

        # Flush to ensure data is persisted
        await self._client.flush_async()

        return result

    async def delete_by_chunk_uuids(self, chunk_uuids: list[str]) -> int:
        """Delete chunks by their UUIDs.

        Args:
            chunk_uuids: List of chunk UUIDs to delete

        Returns:
            Number of deleted entities
        """
        if not chunk_uuids:
            return 0

        # Build filter expression
        uuids_str = ", ".join(f'"{uuid}"' for uuid in chunk_uuids)
        expr = f"chunk_uuid in [{uuids_str}]"

        result = await self._client.delete_async(expr)
        await self._client.flush_async()

        return result

    async def delete_by_doc_uuid(self, doc_uuid: str) -> int:
        """Delete all chunks for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Number of deleted entities
        """
        expr = f'doc_uuid == "{doc_uuid}"'
        result = await self._client.delete_async(expr)
        await self._client.flush_async()

        return result

    async def get_chunk_count(self, doc_uuid: str | None = None) -> int:
        """Get chunk count.

        Args:
            doc_uuid: Optional document UUID to filter

        Returns:
            Number of chunks
        """
        if doc_uuid:
            # Query with filter
            results = await self._client.dense_search_async(
                query_vector=[0.0] * 1024,  # Dummy vector
                limit=0,
                expr=f'doc_uuid == "{doc_uuid}"',
            )
            # This is inefficient, better to use count query
            # For now, return 0 as placeholder
            return 0

        # Total count
        return self._client.collection.num_entities
```

**완료 기준:**
- [ ] insert_chunks 구현
- [ ] delete_by_chunk_uuids 구현
- [ ] delete_by_doc_uuid 구현

---

### Step 3: Search 메서드 구현 (2h)

**작업 내용:**
1. build_filter_expr 헬퍼
2. dense_search 메서드
3. sparse_search 메서드
4. hybrid_search 메서드

**src/repositories/milvus/repository.py (계속):**
```python
    def build_filter_expr(
        self,
        doc_uuids: list[str] | None = None,
        security_level: str | None = None,
    ) -> str | None:
        """Build filter expression for search.

        Args:
            doc_uuids: Allowed document UUIDs (ACL filtered)
            security_level: Max security level

        Returns:
            Filter expression string or None
        """
        conditions = []

        if doc_uuids:
            uuids_str = ", ".join(f'"{uuid}"' for uuid in doc_uuids)
            conditions.append(f"doc_uuid in [{uuids_str}]")

        if security_level:
            # Security level hierarchy: public < internal < confidential
            if security_level == "public":
                conditions.append('security_level == "public"')
            elif security_level == "internal":
                conditions.append('security_level in ["public", "internal"]')
            # confidential sees all

        if not conditions:
            return None

        return " and ".join(conditions)

    async def dense_search(
        self,
        query_vector: list[float],
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        security_level: str | None = None,
    ) -> list[SearchHit]:
        """Search by dense vector (semantic similarity).

        Args:
            query_vector: Query embedding (1024 dim)
            doc_uuids: Allowed document UUIDs (ACL)
            top_k: Max results
            security_level: Max security level

        Returns:
            List of search hits
        """
        filter_expr = self.build_filter_expr(doc_uuids, security_level)

        results = await self._client.dense_search_async(
            query_vector=query_vector,
            limit=top_k,
            expr=filter_expr,
            output_fields=self.OUTPUT_FIELDS,
        )

        return [
            SearchHit.from_milvus_hit(hit, search_type="dense")
            for hit in results
        ]

    async def sparse_search(
        self,
        query_sparse: dict[str, float],
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        security_level: str | None = None,
    ) -> list[SearchHit]:
        """Search by sparse vector (keyword matching).

        Args:
            query_sparse: Sparse vector {term: weight}
            doc_uuids: Allowed document UUIDs (ACL)
            top_k: Max results
            security_level: Max security level

        Returns:
            List of search hits
        """
        filter_expr = self.build_filter_expr(doc_uuids, security_level)

        results = await self._client.sparse_search_async(
            query_sparse=query_sparse,
            limit=top_k,
            expr=filter_expr,
            output_fields=self.OUTPUT_FIELDS,
        )

        return [
            SearchHit.from_milvus_hit(hit, search_type="sparse")
            for hit in results
        ]

    async def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse: dict[str, float],
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        security_level: str | None = None,
        dense_weight: float = 0.5,
    ) -> list[SearchHit]:
        """Hybrid search combining dense and sparse.

        Uses RRF (Reciprocal Rank Fusion) for combining results.

        Args:
            query_dense: Dense embedding
            query_sparse: Sparse weights
            doc_uuids: Allowed document UUIDs (ACL)
            top_k: Max results
            security_level: Max security level
            dense_weight: Weight for dense results (0-1)

        Returns:
            List of search hits (merged)
        """
        filter_expr = self.build_filter_expr(doc_uuids, security_level)

        results = await self._client.hybrid_search_async(
            query_dense=query_dense,
            query_sparse=query_sparse,
            limit=top_k,
            expr=filter_expr,
            output_fields=self.OUTPUT_FIELDS,
            dense_weight=dense_weight,
        )

        return [
            SearchHit.from_milvus_hit(hit, search_type="hybrid")
            for hit in results
        ]

    async def search_by_chunk_uuid(self, chunk_uuid: str) -> SearchHit | None:
        """Get chunk by UUID.

        Args:
            chunk_uuid: Chunk UUID

        Returns:
            SearchHit or None
        """
        results = await self._client.dense_search_async(
            query_vector=[0.0] * 1024,  # Dummy vector
            limit=1,
            expr=f'chunk_uuid == "{chunk_uuid}"',
            output_fields=self.OUTPUT_FIELDS,
        )

        if not results:
            return None

        return SearchHit.from_milvus_hit(results[0])
```

**완료 기준:**
- [ ] build_filter_expr 구현
- [ ] dense_search 구현
- [ ] sparse_search 구현
- [ ] hybrid_search 구현

---

### Step 4: 테스트 작성 (1.5h)

**작업 내용:**
1. Insert/Delete 테스트
2. Search 테스트
3. Filter 테스트

**tests/unit/test_repositories/test_milvus_repository.py:**
```python
"""Tests for Milvus repository."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.repositories.milvus.repository import MilvusRepository
from src.domain.search import MilvusChunk, SearchHit


@pytest.fixture
def mock_client() -> MagicMock:
    """Create mock Milvus client."""
    client = MagicMock()
    client.insert_async = AsyncMock(return_value=["uuid1", "uuid2"])
    client.delete_async = AsyncMock(return_value=2)
    client.flush_async = AsyncMock()
    client.dense_search_async = AsyncMock(return_value=[])
    client.sparse_search_async = AsyncMock(return_value=[])
    client.hybrid_search_async = AsyncMock(return_value=[])
    return client


@pytest.fixture
def repo(mock_client: MagicMock) -> MilvusRepository:
    """Create repository with mock client."""
    return MilvusRepository(mock_client)


class TestInsertDelete:
    """Tests for insert and delete operations."""

    async def test_insert_chunks(self, repo: MilvusRepository, mock_client: MagicMock) -> None:
        """Test chunk insertion."""
        chunks = [
            MilvusChunk(
                chunk_uuid="uuid1",
                doc_uuid="doc1",
                dense_embedding=[0.1] * 1024,
                sparse_embedding={"hello": 0.5},
                chunk_text="Test text",
            ),
            MilvusChunk(
                chunk_uuid="uuid2",
                doc_uuid="doc1",
                dense_embedding=[0.2] * 1024,
                sparse_embedding={"world": 0.3},
                chunk_text="Another text",
            ),
        ]

        result = await repo.insert_chunks(chunks)

        assert len(result) == 2
        mock_client.insert_async.assert_called_once()
        mock_client.flush_async.assert_called_once()

    async def test_insert_empty_list(self, repo: MilvusRepository, mock_client: MagicMock) -> None:
        """Test inserting empty list."""
        result = await repo.insert_chunks([])

        assert result == []
        mock_client.insert_async.assert_not_called()

    async def test_delete_by_chunk_uuids(self, repo: MilvusRepository, mock_client: MagicMock) -> None:
        """Test deletion by chunk UUIDs."""
        result = await repo.delete_by_chunk_uuids(["uuid1", "uuid2"])

        assert result == 2
        mock_client.delete_async.assert_called_once()

    async def test_delete_by_doc_uuid(self, repo: MilvusRepository, mock_client: MagicMock) -> None:
        """Test deletion by document UUID."""
        result = await repo.delete_by_doc_uuid("doc1")

        mock_client.delete_async.assert_called_once()
        call_expr = mock_client.delete_async.call_args[0][0]
        assert "doc_uuid" in call_expr
        assert "doc1" in call_expr


class TestSearch:
    """Tests for search operations."""

    async def test_dense_search(self, repo: MilvusRepository, mock_client: MagicMock) -> None:
        """Test dense vector search."""
        mock_client.dense_search_async.return_value = [
            {
                "chunk_uuid": "uuid1",
                "doc_uuid": "doc1",
                "score": 0.95,
                "distance": 0.05,
                "chunk_text": "Test",
            }
        ]

        results = await repo.dense_search(
            query_vector=[0.1] * 1024,
            doc_uuids=["doc1"],
            top_k=10,
        )

        assert len(results) == 1
        assert results[0].chunk_uuid == "uuid1"
        assert results[0].search_type == "dense"

    async def test_sparse_search(self, repo: MilvusRepository, mock_client: MagicMock) -> None:
        """Test sparse vector search."""
        mock_client.sparse_search_async.return_value = [
            {
                "chunk_uuid": "uuid1",
                "doc_uuid": "doc1",
                "score": 0.8,
                "distance": 0.2,
                "chunk_text": "Test",
            }
        ]

        results = await repo.sparse_search(
            query_sparse={"hello": 0.5, "world": 0.3},
            doc_uuids=["doc1"],
            top_k=10,
        )

        assert len(results) == 1
        assert results[0].search_type == "sparse"

    async def test_hybrid_search(self, repo: MilvusRepository, mock_client: MagicMock) -> None:
        """Test hybrid search."""
        mock_client.hybrid_search_async.return_value = [
            {
                "chunk_uuid": "uuid1",
                "doc_uuid": "doc1",
                "score": 0.9,
                "distance": 0.1,
                "chunk_text": "Test",
            }
        ]

        results = await repo.hybrid_search(
            query_dense=[0.1] * 1024,
            query_sparse={"hello": 0.5},
            doc_uuids=["doc1"],
            top_k=10,
        )

        assert len(results) == 1
        assert results[0].search_type == "hybrid"


class TestFilterExpression:
    """Tests for filter expression building."""

    def test_build_filter_with_doc_uuids(self, repo: MilvusRepository) -> None:
        """Test filter with document UUIDs."""
        expr = repo.build_filter_expr(doc_uuids=["doc1", "doc2"])

        assert expr is not None
        assert "doc_uuid in" in expr
        assert '"doc1"' in expr
        assert '"doc2"' in expr

    def test_build_filter_with_security(self, repo: MilvusRepository) -> None:
        """Test filter with security level."""
        expr = repo.build_filter_expr(security_level="internal")

        assert expr is not None
        assert "security_level" in expr

    def test_build_filter_empty(self, repo: MilvusRepository) -> None:
        """Test empty filter."""
        expr = repo.build_filter_expr()

        assert expr is None
```

**완료 기준:**
- [ ] Insert/Delete 테스트 작성
- [ ] Search 테스트 작성
- [ ] Filter 테스트 작성

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_insert_chunks` | 청크 삽입 | UUID 리스트 반환 |
| `test_delete_by_chunk_uuids` | UUID로 삭제 | 삭제 건수 |
| `test_delete_by_doc_uuid` | 문서별 삭제 | 삭제 건수 |
| `test_dense_search` | Dense 검색 | SearchHit 리스트 |
| `test_sparse_search` | Sparse 검색 | SearchHit 리스트 |
| `test_hybrid_search` | Hybrid 검색 | SearchHit 리스트 |
| `test_build_filter_*` | 필터 빌드 | 올바른 표현식 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_insert_search` | 삽입 후 검색 | 결과 일치 |
| `test_acl_filtering` | ACL 필터링 | 권한 있는 문서만 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 대량 삽입 성능 | Medium | Medium | 배치 크기 조절 |
| Filter 표현식 오류 | High | Low | 유닛 테스트로 검증 |
| Sparse 벡터 형식 | Medium | Low | 형식 검증 추가 |

---

## 6. Definition of Done

- [ ] `src/repositories/milvus/repository.py` 구현
- [ ] `src/domain/search.py` 모델 정의
- [ ] Vector Insert/Delete 구현
- [ ] Dense/Sparse/Hybrid Search 구현
- [ ] Filter 표현식 빌더 구현
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Domain Models | 1h | - |
| Step 2: Insert/Delete | 1.5h | - |
| Step 3: Search 메서드 | 2h | - |
| Step 4: 테스트 | 1.5h | - |
| **Total** | **6h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
