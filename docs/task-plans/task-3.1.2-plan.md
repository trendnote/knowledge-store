# Task Execution Plan: 3.1.2 - Sparse Search 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 3.1.2 |
| **Task Name** | Sparse Search 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 2.2.2, Task 2.3.1 |

### Description
Milvus Sparse Vector (BM25) 키워드 검색을 구현합니다.

### Acceptance Criteria
- [ ] 쿼리 임베딩 생성 (Sparse)
- [ ] Milvus Sparse Search 호출
- [ ] ACL 필터 적용
- [ ] 검색 결과 포맷팅

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 5.4 Search Service
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 5 FR-3

### 2.2 Sparse Search 개요
```python
# Milvus Sparse Search
from scipy.sparse import csr_array

# Sparse vector format: dict[int, float]
# {token_id: weight, ...}
sparse_vector = {123: 0.5, 456: 0.8, 789: 0.3}

search_params = {
    "metric_type": "IP",  # Inner Product for sparse
    "params": {}
}

results = collection.search(
    data=[sparse_vector],
    anns_field="sparse_embedding",
    param=search_params,
    limit=top_k,
    expr=filter_expr,
    output_fields=["chunk_uuid", "doc_uuid", "text_preview"]
)
```

### 2.3 설계 결정
1. **Inner Product**: Sparse 벡터에 적합한 메트릭
2. **BGE-M3 Sparse**: Lexical weights 활용
3. **한국어 지원**: BGE-M3는 다국어 토크나이저 사용
4. **키워드 매칭**: BM25 스타일 가중치

### 2.4 Dense vs Sparse 차이
| 특성 | Dense | Sparse |
|------|-------|--------|
| 벡터 형태 | Float[1024] | Dict[int, float] |
| 메트릭 | COSINE | IP |
| 강점 | 의미적 유사성 | 키워드 정확 매칭 |
| 약점 | 키워드 누락 | 의미 파악 한계 |

---

## 3. Implementation Steps

### Step 1: Sparse Search 결과 포맷팅 (1h)

**작업 내용:**
1. Sparse 결과 포맷 메서드
2. 스코어 정규화

**src/services/search_service.py (추가):**
```python
    def _format_sparse_results(
        self,
        hits: list[dict[str, Any]],
    ) -> list[SearchResult]:
        """Format Milvus sparse search hits to SearchResult.

        Args:
            hits: Raw search hits from Milvus

        Returns:
            List of formatted SearchResult
        """
        results = []
        for hit in hits:
            # Sparse search uses inner product, normalize if needed
            raw_score = float(hit.get("score", 0.0))

            results.append(
                SearchResult(
                    chunk_uuid=hit.get("chunk_uuid", ""),
                    doc_uuid=hit.get("doc_uuid", ""),
                    score=raw_score,
                    search_type=SearchType.SPARSE,
                    text_preview=hit.get("text_preview"),
                    title=hit.get("title"),
                    metadata={
                        "raw_score": raw_score,
                        "match_type": "lexical",
                    },
                )
            )
        return results
```

**완료 기준:**
- [ ] _format_sparse_results 구현
- [ ] 스코어 처리

---

### Step 2: Sparse Search 메서드 구현 (1.5h)

**작업 내용:**
1. sparse_search 메서드 구현
2. Sparse 임베딩 추출
3. 에러 핸들링

**src/services/search_service.py (계속):**
```python
    async def sparse_search(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Execute sparse vector (keyword) search.

        Uses inner product on sparse embeddings for BM25-style matching.

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

        # 2. Generate query embedding (sparse)
        embeddings = self._encode_query(query)
        if not embeddings or not embeddings.sparse:
            logger.warning("Failed to generate sparse query embedding")
            return []

        query_sparse = embeddings.sparse[0]

        # Validate sparse vector
        if not query_sparse:
            logger.warning("Empty sparse embedding for query")
            return []

        # 3. Execute search
        try:
            hits = await self._milvus_repo.sparse_search(
                query_sparse=query_sparse,
                filter_expr=filter_expr,
                top_k=top_k,
            )
        except Exception as e:
            logger.error(f"Sparse search failed: {e}")
            raise

        # 4. Format and filter results
        results = self._format_sparse_results(hits)

        # Apply minimum score filter
        if min_score > 0:
            results = [r for r in results if r.score >= min_score]

        logger.info(f"Sparse search returned {len(results)} results")
        return results
```

**완료 기준:**
- [ ] sparse_search 메서드 구현
- [ ] Sparse 임베딩 추출
- [ ] ACL 필터 적용

---

### Step 3: 한국어 키워드 검색 최적화 (0.5h)

**작업 내용:**
1. 한국어 쿼리 전처리 고려
2. 토큰 가중치 조정 (옵션)

**src/services/search_service.py (추가):**
```python
    def _preprocess_query(self, query: str) -> str:
        """Preprocess query for better search.

        Currently a passthrough - BGE-M3 handles Korean well.
        Can be extended for:
        - Query expansion
        - Stop word removal
        - Normalization

        Args:
            query: Raw query text

        Returns:
            Preprocessed query
        """
        # BGE-M3 handles Korean tokenization internally
        # Just trim whitespace for now
        return query.strip()

    def _boost_sparse_weights(
        self,
        sparse: dict[int, float],
        boost_factor: float = 1.0,
    ) -> dict[int, float]:
        """Boost sparse vector weights.

        Can be used to emphasize certain terms.

        Args:
            sparse: Sparse vector
            boost_factor: Multiplication factor

        Returns:
            Boosted sparse vector
        """
        if boost_factor == 1.0:
            return sparse

        return {k: v * boost_factor for k, v in sparse.items()}
```

**완료 기준:**
- [ ] _preprocess_query 구현
- [ ] _boost_sparse_weights 구현 (향후 확장용)

---

### Step 4: 테스트 작성 (1h)

**작업 내용:**
1. Sparse search 테스트
2. 한국어 쿼리 테스트

**tests/unit/test_services/test_sparse_search.py:**
```python
"""Tests for sparse search."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.search_service import SearchService
from src.domain.models.search import SearchType


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
        sparse=[{123: 0.5, 456: 0.8}],
    )
    return mock


@pytest.fixture
def mock_acl_service() -> MagicMock:
    """Create mock ACL service."""
    mock = MagicMock()
    mock.get_accessible_documents = AsyncMock(return_value=["doc-1"])
    mock.build_milvus_filter.return_value = 'doc_uuid in ["doc-1"]'
    return mock


@pytest.fixture
def search_service(
    mock_milvus_repo: MagicMock,
    mock_embedding_service: MagicMock,
    mock_acl_service: MagicMock,
) -> SearchService:
    """Create search service with mocks."""
    return SearchService(mock_milvus_repo, mock_embedding_service, mock_acl_service)


class TestSparseSearch:
    """Tests for sparse search."""

    async def test_sparse_search_success(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test successful sparse search."""
        mock_milvus_repo.sparse_search = AsyncMock(
            return_value=[
                {"chunk_uuid": "c1", "doc_uuid": "d1", "score": 0.9},
                {"chunk_uuid": "c2", "doc_uuid": "d1", "score": 0.7},
            ]
        )

        results = await search_service.sparse_search(
            query="키워드 검색",
            user_id="user1",
            top_k=10,
        )

        assert len(results) == 2
        assert results[0].search_type == SearchType.SPARSE

    async def test_sparse_search_korean_query(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test sparse search with Korean query."""
        mock_milvus_repo.sparse_search = AsyncMock(
            return_value=[
                {"chunk_uuid": "c1", "doc_uuid": "d1", "score": 0.85},
            ]
        )

        results = await search_service.sparse_search(
            query="인공지능 기술 문서",
            user_id="user1",
        )

        assert len(results) == 1

    async def test_sparse_search_empty_sparse_vector(
        self,
        search_service: SearchService,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test sparse search with empty sparse embedding."""
        mock_embedding_service.encode.return_value = MagicMock(
            dense=[[0.1] * 1024],
            sparse=[{}],  # Empty sparse
        )

        results = await search_service.sparse_search(
            query="test",
            user_id="user1",
        )

        assert len(results) == 0

    async def test_sparse_search_with_min_score(
        self,
        search_service: SearchService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test sparse search with minimum score filter."""
        mock_milvus_repo.sparse_search = AsyncMock(
            return_value=[
                {"chunk_uuid": "c1", "doc_uuid": "d1", "score": 0.9},
                {"chunk_uuid": "c2", "doc_uuid": "d1", "score": 0.3},
            ]
        )

        results = await search_service.sparse_search(
            query="test",
            user_id="user1",
            min_score=0.5,
        )

        assert len(results) == 1
        assert results[0].score >= 0.5


class TestPreprocessQuery:
    """Tests for query preprocessing."""

    def test_preprocess_query_strips_whitespace(
        self,
        search_service: SearchService,
    ) -> None:
        """Test that query is stripped."""
        result = search_service._preprocess_query("  test query  ")
        assert result == "test query"

    def test_preprocess_query_korean(
        self,
        search_service: SearchService,
    ) -> None:
        """Test Korean query preprocessing."""
        result = search_service._preprocess_query("  한국어 쿼리  ")
        assert result == "한국어 쿼리"
```

**완료 기준:**
- [ ] sparse_search 성공 테스트
- [ ] 한국어 쿼리 테스트
- [ ] 빈 sparse 벡터 테스트
- [ ] min_score 필터 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_sparse_search_success` | 정상 검색 | 결과 반환 |
| `test_sparse_search_korean` | 한국어 검색 | 정상 동작 |
| `test_sparse_search_empty` | 빈 sparse 벡터 | 빈 결과 |
| `test_sparse_search_min_score` | 최소 점수 필터 | 필터된 결과 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_sparse_search_real_milvus` | 실제 Milvus 검색 | 결과 반환 |
| `test_sparse_search_keyword_match` | 키워드 정확 매칭 | 높은 점수 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 짧은 쿼리 성능 저하 | Medium | Medium | 최소 쿼리 길이 권장 |
| Sparse 벡터 희소성 | Low | Low | 쿼리 확장 고려 |
| 토큰화 불일치 | Medium | Low | BGE-M3 일관된 사용 |

---

## 6. Definition of Done

- [ ] sparse_search 메서드 구현
- [ ] Sparse 임베딩 활용
- [ ] ACL 필터 적용
- [ ] 한국어 쿼리 지원
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 결과 포맷팅 | 1h | - |
| Step 2: Sparse Search 구현 | 1.5h | - |
| Step 3: 한국어 최적화 | 0.5h | - |
| Step 4: 테스트 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
