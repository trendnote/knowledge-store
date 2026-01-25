# Task Execution Plan: 3.1.1 - Dense Search 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 3.1.1 |
| **Task Name** | Dense Search 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 2.2.2, Task 2.3.1 |

### Description
Milvus Dense Vector 코사인 유사도 검색을 구현합니다.

### Acceptance Criteria
- [ ] `src/services/search_service.py` 생성
- [ ] 쿼리 임베딩 생성 (Dense)
- [ ] Milvus Dense Search 호출
- [ ] ACL 필터 적용
- [ ] 검색 결과 포맷팅

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 5.4 Search Service
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 5 FR-3

### 2.2 Dense Search 개요
```python
# Milvus Dense Search
search_params = {
    "metric_type": "COSINE",
    "params": {"nprobe": 10}
}

results = collection.search(
    data=[query_vector],          # (1, 1024) dense embedding
    anns_field="dense_embedding",
    param=search_params,
    limit=top_k,
    expr=filter_expr,             # ACL 필터
    output_fields=["chunk_uuid", "doc_uuid", "text_preview"]
)
```

### 2.3 설계 결정
1. **COSINE 유사도**: 정규화된 벡터 비교에 적합
2. **nprobe=10**: 속도/정확도 균형
3. **ACL 필터 선적용**: Milvus expr로 필터링
4. **결과 정규화**: 0~1 범위로 스코어 정규화

### 2.4 클래스 구조
```
SearchService
├── __init__(milvus_repo, embedding_service, acl_service)
├── dense_search(query, user_id, groups, top_k) -> list[SearchResult]
├── _encode_query(query) -> EmbeddingResult
├── _build_filter(doc_uuids) -> str
└── _format_results(hits, search_type) -> list[SearchResult]

SearchResult
├── chunk_uuid: str
├── doc_uuid: str
├── score: float
├── search_type: str
├── text_preview: str | None
└── metadata: dict
```

---

## 3. Implementation Steps

### Step 1: SearchResult 모델 및 기본 구조 (1h)

**작업 내용:**
1. SearchResult 데이터 클래스 정의
2. SearchService 클래스 기본 구조
3. 의존성 주입 설정

**src/domain/models/search.py:**
```python
"""Search domain models."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SearchType(str, Enum):
    """Type of search performed."""

    DENSE = "dense"
    SPARSE = "sparse"
    GRAPH = "graph"
    HYBRID = "hybrid"


@dataclass
class SearchResult:
    """Single search result."""

    chunk_uuid: str
    doc_uuid: str
    score: float
    search_type: SearchType
    text_preview: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_uuid": self.chunk_uuid,
            "doc_uuid": self.doc_uuid,
            "score": self.score,
            "search_type": self.search_type.value,
            "text_preview": self.text_preview,
            "title": self.title,
            "metadata": self.metadata,
        }


@dataclass
class SearchRequest:
    """Search request parameters."""

    query: str
    user_id: str
    user_groups: list[str] = field(default_factory=list)
    top_k: int = 10
    search_types: list[SearchType] = field(
        default_factory=lambda: [SearchType.DENSE, SearchType.SPARSE, SearchType.GRAPH]
    )
    min_score: float = 0.0


@dataclass
class SearchResponse:
    """Search response."""

    results: list[SearchResult]
    total: int
    search_time_ms: float
    search_types_used: list[SearchType] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "results": [r.to_dict() for r in self.results],
            "total": self.total,
            "search_time_ms": self.search_time_ms,
            "search_types_used": [t.value for t in self.search_types_used],
        }
```

**src/services/search_service.py:**
```python
"""Search service for hybrid search."""
from typing import Any, Protocol

from src.domain.models.search import SearchResult, SearchType


class MilvusRepositoryProtocol(Protocol):
    """Protocol for Milvus repository."""

    async def dense_search(
        self,
        query_vector: list[float],
        filter_expr: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Execute dense vector search."""
        ...


class EmbeddingServiceProtocol(Protocol):
    """Protocol for embedding service."""

    def encode(self, texts: list[str]) -> Any:
        """Encode texts to embeddings."""
        ...


class AclServiceProtocol(Protocol):
    """Protocol for ACL service."""

    async def get_accessible_documents(
        self,
        user_id: str,
        user_groups: list[str] | None,
    ) -> list[str]:
        """Get accessible document UUIDs."""
        ...

    def build_milvus_filter(self, doc_uuids: list[str]) -> str:
        """Build Milvus filter expression."""
        ...


class SearchService:
    """Service for search operations."""

    def __init__(
        self,
        milvus_repo: MilvusRepositoryProtocol,
        embedding_service: EmbeddingServiceProtocol,
        acl_service: AclServiceProtocol,
    ) -> None:
        """Initialize search service.

        Args:
            milvus_repo: Milvus repository for vector search
            embedding_service: Service for generating embeddings
            acl_service: Service for access control
        """
        self._milvus_repo = milvus_repo
        self._embedding_service = embedding_service
        self._acl_service = acl_service
```

**완료 기준:**
- [ ] SearchResult 모델 정의
- [ ] SearchRequest/SearchResponse 모델 정의
- [ ] SearchService 기본 구조

---

### Step 2: 쿼리 임베딩 및 필터 생성 (1h)

**작업 내용:**
1. 쿼리 임베딩 생성 메서드
2. ACL 기반 필터 생성
3. 결과 포맷팅 헬퍼

**src/services/search_service.py (계속):**
```python
    def _encode_query(self, query: str) -> Any:
        """Encode query to embeddings.

        Args:
            query: Query text

        Returns:
            EmbeddingResult with dense and sparse embeddings
        """
        return self._embedding_service.encode([query])

    async def _get_acl_filter(
        self,
        user_id: str,
        user_groups: list[str],
    ) -> str:
        """Get Milvus filter expression for ACL.

        Args:
            user_id: User identifier
            user_groups: User's group memberships

        Returns:
            Milvus filter expression
        """
        accessible_docs = await self._acl_service.get_accessible_documents(
            user_id, user_groups
        )
        return self._acl_service.build_milvus_filter(accessible_docs)

    def _format_dense_results(
        self,
        hits: list[dict[str, Any]],
    ) -> list[SearchResult]:
        """Format Milvus search hits to SearchResult.

        Args:
            hits: Raw search hits from Milvus

        Returns:
            List of formatted SearchResult
        """
        results = []
        for hit in hits:
            results.append(
                SearchResult(
                    chunk_uuid=hit.get("chunk_uuid", ""),
                    doc_uuid=hit.get("doc_uuid", ""),
                    score=float(hit.get("score", 0.0)),
                    search_type=SearchType.DENSE,
                    text_preview=hit.get("text_preview"),
                    title=hit.get("title"),
                    metadata={
                        "distance": hit.get("distance"),
                    },
                )
            )
        return results
```

**완료 기준:**
- [ ] _encode_query 구현
- [ ] _get_acl_filter 구현
- [ ] _format_dense_results 구현

---

### Step 3: Dense Search 메서드 구현 (1h)

**작업 내용:**
1. dense_search 메서드 구현
2. 에러 핸들링
3. 로깅 추가

**src/services/search_service.py (계속):**
```python
    async def dense_search(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Execute dense vector search.

        Uses cosine similarity on dense embeddings.

        Args:
            query: Search query text
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold

        Returns:
            List of search results sorted by score
        """
        import logging

        logger = logging.getLogger(__name__)
        groups = user_groups or []

        # 1. Get ACL filter
        filter_expr = await self._get_acl_filter(user_id, groups)
        logger.debug(f"ACL filter: {filter_expr}")

        # 2. Generate query embedding
        embeddings = self._encode_query(query)
        if not embeddings or not embeddings.dense:
            logger.warning("Failed to generate query embedding")
            return []

        query_vector = embeddings.dense[0]

        # 3. Execute search
        try:
            hits = await self._milvus_repo.dense_search(
                query_vector=query_vector,
                filter_expr=filter_expr,
                top_k=top_k,
            )
        except Exception as e:
            logger.error(f"Dense search failed: {e}")
            raise

        # 4. Format and filter results
        results = self._format_dense_results(hits)

        # Apply minimum score filter
        if min_score > 0:
            results = [r for r in results if r.score >= min_score]

        logger.info(f"Dense search returned {len(results)} results")
        return results
```

**완료 기준:**
- [ ] dense_search 메서드 구현
- [ ] ACL 필터 적용
- [ ] min_score 필터 적용
- [ ] 로깅 추가

---

### Step 4: Factory 및 테스트 (1h)

**작업 내용:**
1. Factory 함수
2. 테스트 작성

**src/services/search_service.py (추가):**
```python
# Service factory
_service: SearchService | None = None


def get_search_service(
    milvus_repo: MilvusRepositoryProtocol | None = None,
    embedding_service: EmbeddingServiceProtocol | None = None,
    acl_service: AclServiceProtocol | None = None,
) -> SearchService:
    """Get or create search service singleton.

    Args:
        milvus_repo: Milvus repository
        embedding_service: Embedding service
        acl_service: ACL service

    Returns:
        SearchService instance
    """
    global _service
    if _service is None:
        if milvus_repo is None or embedding_service is None or acl_service is None:
            raise ValueError("All dependencies required for first initialization")
        _service = SearchService(milvus_repo, embedding_service, acl_service)
    return _service


def reset_search_service() -> None:
    """Reset search service singleton (for testing)."""
    global _service
    _service = None
```

**tests/unit/test_services/test_search_service.py:**
```python
"""Tests for search service."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.search_service import SearchService
from src.domain.models.search import SearchResult, SearchType


@pytest.fixture
def mock_milvus_repo() -> MagicMock:
    """Create mock Milvus repository."""
    return MagicMock()


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create mock embedding service."""
    mock = MagicMock()
    mock.encode.return_value = MagicMock(
        dense=[[0.1] * 1024],
        sparse=[{1: 0.5}],
    )
    return mock


@pytest.fixture
def mock_acl_service() -> MagicMock:
    """Create mock ACL service."""
    mock = MagicMock()
    mock.get_accessible_documents = AsyncMock(return_value=["doc-1", "doc-2"])
    mock.build_milvus_filter.return_value = 'doc_uuid in ["doc-1", "doc-2"]'
    return mock


@pytest.fixture
def search_service(
    mock_milvus_repo: MagicMock,
    mock_embedding_service: MagicMock,
    mock_acl_service: MagicMock,
) -> SearchService:
    """Create search service with mocks."""
    return SearchService(mock_milvus_repo, mock_embedding_service, mock_acl_service)


class TestDenseSearch:
    """Tests for dense search."""

    async def test_dense_search_success(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test successful dense search."""
        mock_milvus_repo.dense_search = AsyncMock(
            return_value=[
                {"chunk_uuid": "c1", "doc_uuid": "d1", "score": 0.95},
                {"chunk_uuid": "c2", "doc_uuid": "d1", "score": 0.85},
            ]
        )

        results = await search_service.dense_search(
            query="test query",
            user_id="user1",
            user_groups=["group1"],
            top_k=10,
        )

        assert len(results) == 2
        assert results[0].score == 0.95
        assert results[0].search_type == SearchType.DENSE

    async def test_dense_search_with_min_score(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test dense search with minimum score filter."""
        mock_milvus_repo.dense_search = AsyncMock(
            return_value=[
                {"chunk_uuid": "c1", "doc_uuid": "d1", "score": 0.95},
                {"chunk_uuid": "c2", "doc_uuid": "d1", "score": 0.45},
            ]
        )

        results = await search_service.dense_search(
            query="test query",
            user_id="user1",
            top_k=10,
            min_score=0.5,
        )

        assert len(results) == 1
        assert results[0].score >= 0.5

    async def test_dense_search_empty_result(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test dense search with no results."""
        mock_milvus_repo.dense_search = AsyncMock(return_value=[])

        results = await search_service.dense_search(
            query="test query",
            user_id="user1",
        )

        assert len(results) == 0

    async def test_dense_search_applies_acl_filter(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test that ACL filter is applied."""
        mock_milvus_repo.dense_search = AsyncMock(return_value=[])

        await search_service.dense_search(
            query="test query",
            user_id="user1",
            user_groups=["group1"],
        )

        mock_acl_service.get_accessible_documents.assert_called_once_with(
            "user1", ["group1"]
        )
        mock_milvus_repo.dense_search.assert_called_once()
        call_args = mock_milvus_repo.dense_search.call_args
        assert "filter_expr" in call_args.kwargs
```

**완료 기준:**
- [ ] Factory 함수 구현
- [ ] dense_search 성공 테스트
- [ ] min_score 필터 테스트
- [ ] ACL 필터 적용 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_dense_search_success` | 정상 검색 | 결과 리스트 반환 |
| `test_dense_search_with_min_score` | 최소 점수 필터 | 필터된 결과 |
| `test_dense_search_empty_result` | 결과 없음 | 빈 리스트 |
| `test_dense_search_applies_acl_filter` | ACL 필터 적용 | 필터 호출 확인 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_dense_search_real_milvus` | 실제 Milvus 검색 | 결과 반환 |
| `test_dense_search_performance` | 성능 테스트 | < 100ms |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 임베딩 생성 지연 | Medium | Medium | 쿼리 캐싱 고려 |
| ACL 필터 과다 | High | Low | 필터 최적화, 페이지네이션 |
| Milvus 연결 실패 | High | Low | 재시도 로직, 타임아웃 |

---

## 6. Definition of Done

- [ ] `src/services/search_service.py` 생성
- [ ] `src/domain/models/search.py` 생성
- [ ] dense_search 메서드 구현
- [ ] ACL 필터 적용
- [ ] 결과 포맷팅
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 모델 및 기본 구조 | 1h | - |
| Step 2: 쿼리 임베딩 및 필터 | 1h | - |
| Step 3: Dense Search 구현 | 1h | - |
| Step 4: Factory 및 테스트 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
