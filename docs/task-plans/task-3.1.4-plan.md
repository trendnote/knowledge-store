# Task Execution Plan: 3.1.4 - Hybrid Search API 통합

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 3.1.4 |
| **Task Name** | Hybrid Search API 통합 |
| **Estimate** | 6h |
| **Priority** | P0 |
| **Dependencies** | Task 3.1.1, 3.1.2, 3.1.3 |

### Description
3개 검색 방식을 병렬로 실행하고 결과를 통합하는 Hybrid Search를 구현합니다.

### Acceptance Criteria
- [ ] ACL 필터링 선실행
- [ ] asyncio.gather로 병렬 검색
- [ ] 결과 통합 (중복 제거, 점수 합산)
- [ ] 응답 시간 측정
- [ ] SearchResponse 반환

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 5.4 Search Service
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 5 FR-3, NFR-2

### 2.2 Hybrid Search 전략
```python
# 병렬 실행
results = await asyncio.gather(
    dense_search(query, ...),
    sparse_search(query, ...),
    graph_search(query, ...),
    return_exceptions=True
)

# 결과 통합 (RRF: Reciprocal Rank Fusion)
def rrf_score(ranks: list[int], k: int = 60) -> float:
    return sum(1 / (k + rank) for rank in ranks)
```

### 2.3 설계 결정
1. **병렬 실행**: asyncio.gather 사용
2. **결과 병합**: RRF (Reciprocal Rank Fusion)
3. **중복 제거**: chunk_uuid 기준
4. **가중치**: 검색 타입별 가중치 적용 가능
5. **Fail-safe**: 일부 검색 실패 시에도 결과 반환

### 2.4 RRF 알고리즘
```
RRF(d) = Σ 1 / (k + rank_i(d))

- k: 상수 (보통 60)
- rank_i(d): 검색 i에서 문서 d의 순위

예시:
- Dense: rank 1 → 1/(60+1) = 0.0164
- Sparse: rank 3 → 1/(60+3) = 0.0159
- Graph: rank 2 → 1/(60+2) = 0.0161
- Total RRF = 0.0484
```

---

## 3. Implementation Steps

### Step 1: 결과 병합 로직 (1.5h)

**작업 내용:**
1. RRF 스코어 계산
2. 중복 제거 및 병합
3. 정렬 및 Top-K 선택

**src/services/search_service.py (추가):**
```python
from dataclasses import dataclass
from typing import Any


@dataclass
class MergedResult:
    """Merged search result with RRF score."""

    chunk_uuid: str
    doc_uuid: str
    rrf_score: float
    sources: dict[SearchType, SearchResult]

    @property
    def best_text_preview(self) -> str | None:
        """Get text preview from any source."""
        for result in self.sources.values():
            if result.text_preview:
                return result.text_preview
        return None

    @property
    def best_title(self) -> str | None:
        """Get title from any source."""
        for result in self.sources.values():
            if result.title:
                return result.title
        return None

    def to_search_result(self) -> SearchResult:
        """Convert to SearchResult."""
        return SearchResult(
            chunk_uuid=self.chunk_uuid,
            doc_uuid=self.doc_uuid,
            score=self.rrf_score,
            search_type=SearchType.HYBRID,
            text_preview=self.best_text_preview,
            title=self.best_title,
            metadata={
                "sources": {
                    t.value: {"score": r.score, "rank": i}
                    for i, (t, r) in enumerate(self.sources.items())
                }
            },
        )


class SearchService:
    # ... existing code ...

    def _calculate_rrf_scores(
        self,
        results_by_type: dict[SearchType, list[SearchResult]],
        k: int = 60,
    ) -> dict[str, MergedResult]:
        """Calculate RRF scores for all results.

        Args:
            results_by_type: Results grouped by search type
            k: RRF constant (default 60)

        Returns:
            Dict of chunk_uuid to MergedResult
        """
        merged: dict[str, MergedResult] = {}

        for search_type, results in results_by_type.items():
            for rank, result in enumerate(results, start=1):
                chunk_uuid = result.chunk_uuid
                rrf_contribution = 1 / (k + rank)

                if chunk_uuid in merged:
                    merged[chunk_uuid].rrf_score += rrf_contribution
                    merged[chunk_uuid].sources[search_type] = result
                else:
                    merged[chunk_uuid] = MergedResult(
                        chunk_uuid=chunk_uuid,
                        doc_uuid=result.doc_uuid,
                        rrf_score=rrf_contribution,
                        sources={search_type: result},
                    )

        return merged

    def _merge_results(
        self,
        results_by_type: dict[SearchType, list[SearchResult]],
        top_k: int,
        weights: dict[SearchType, float] | None = None,
    ) -> list[SearchResult]:
        """Merge results from multiple search types using RRF.

        Args:
            results_by_type: Results grouped by search type
            top_k: Maximum results to return
            weights: Optional weights per search type

        Returns:
            Merged and sorted results
        """
        # Apply weights if provided
        if weights:
            weighted_results: dict[SearchType, list[SearchResult]] = {}
            for search_type, results in results_by_type.items():
                weight = weights.get(search_type, 1.0)
                weighted = []
                for r in results:
                    weighted_r = SearchResult(
                        chunk_uuid=r.chunk_uuid,
                        doc_uuid=r.doc_uuid,
                        score=r.score * weight,
                        search_type=r.search_type,
                        text_preview=r.text_preview,
                        title=r.title,
                        metadata=r.metadata,
                    )
                    weighted.append(weighted_r)
                weighted_results[search_type] = weighted
            results_by_type = weighted_results

        # Calculate RRF scores
        merged = self._calculate_rrf_scores(results_by_type)

        # Sort by RRF score and take top_k
        sorted_results = sorted(
            merged.values(),
            key=lambda x: x.rrf_score,
            reverse=True,
        )[:top_k]

        return [m.to_search_result() for m in sorted_results]
```

**완료 기준:**
- [ ] RRF 스코어 계산 구현
- [ ] MergedResult 클래스 구현
- [ ] _merge_results 구현
- [ ] 가중치 적용 지원

---

### Step 2: Hybrid Search 메서드 구현 (2h)

**작업 내용:**
1. hybrid_search 메서드
2. 병렬 실행 (asyncio.gather)
3. 응답 시간 측정

**src/services/search_service.py (계속):**
```python
    async def hybrid_search(
        self,
        request: SearchRequest,
    ) -> SearchResponse:
        """Execute hybrid search combining multiple search types.

        Runs Dense, Sparse, and Graph searches in parallel,
        then merges results using RRF.

        Args:
            request: Search request parameters

        Returns:
            SearchResponse with merged results
        """
        import asyncio
        import logging
        import time

        logger = logging.getLogger(__name__)
        start_time = time.time()

        # Determine which search types to use
        search_types = request.search_types or [
            SearchType.DENSE,
            SearchType.SPARSE,
            SearchType.GRAPH,
        ]

        logger.info(f"Hybrid search with types: {[t.value for t in search_types]}")

        # Build search tasks
        tasks: dict[SearchType, Any] = {}

        if SearchType.DENSE in search_types:
            tasks[SearchType.DENSE] = self.dense_search(
                query=request.query,
                user_id=request.user_id,
                user_groups=request.user_groups,
                top_k=request.top_k * 2,  # Over-fetch for merging
                min_score=request.min_score,
            )

        if SearchType.SPARSE in search_types:
            tasks[SearchType.SPARSE] = self.sparse_search(
                query=request.query,
                user_id=request.user_id,
                user_groups=request.user_groups,
                top_k=request.top_k * 2,
                min_score=request.min_score,
            )

        if SearchType.GRAPH in search_types:
            tasks[SearchType.GRAPH] = self.graph_search(
                query=request.query,
                user_id=request.user_id,
                user_groups=request.user_groups,
                top_k=request.top_k * 2,
                min_score=request.min_score,
            )

        # Execute in parallel
        task_list = list(tasks.values())
        task_keys = list(tasks.keys())

        results_list = await asyncio.gather(*task_list, return_exceptions=True)

        # Process results
        results_by_type: dict[SearchType, list[SearchResult]] = {}
        errors: list[str] = []

        for search_type, result in zip(task_keys, results_list):
            if isinstance(result, Exception):
                logger.error(f"{search_type.value} search failed: {result}")
                errors.append(f"{search_type.value}: {str(result)}")
            else:
                results_by_type[search_type] = result

        # Merge results
        merged_results = self._merge_results(
            results_by_type,
            top_k=request.top_k,
        )

        # Calculate search time
        search_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Hybrid search completed: {len(merged_results)} results "
            f"in {search_time_ms:.2f}ms"
        )

        return SearchResponse(
            results=merged_results,
            total=len(merged_results),
            search_time_ms=search_time_ms,
            search_types_used=list(results_by_type.keys()),
        )

    async def search(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        search_types: list[SearchType] | None = None,
        min_score: float = 0.0,
    ) -> SearchResponse:
        """Convenience method for hybrid search.

        Args:
            query: Search query
            user_id: User identifier
            user_groups: User's group memberships
            top_k: Maximum results
            search_types: Types of search to perform
            min_score: Minimum score threshold

        Returns:
            SearchResponse
        """
        request = SearchRequest(
            query=query,
            user_id=user_id,
            user_groups=user_groups or [],
            top_k=top_k,
            search_types=search_types or [
                SearchType.DENSE,
                SearchType.SPARSE,
                SearchType.GRAPH,
            ],
            min_score=min_score,
        )
        return await self.hybrid_search(request)
```

**완료 기준:**
- [ ] hybrid_search 구현
- [ ] asyncio.gather 병렬 실행
- [ ] 에러 처리 (부분 실패)
- [ ] 응답 시간 측정
- [ ] search 편의 메서드

---

### Step 3: 검색 타입 선택 및 가중치 (1h)

**작업 내용:**
1. 검색 타입별 가중치 설정
2. 동적 가중치 조정
3. 성능 최적화

**src/services/search_service.py (추가):**
```python
    # Default weights for different search types
    DEFAULT_WEIGHTS: dict[SearchType, float] = {
        SearchType.DENSE: 1.0,
        SearchType.SPARSE: 0.8,
        SearchType.GRAPH: 0.6,
    }

    async def hybrid_search_with_weights(
        self,
        request: SearchRequest,
        weights: dict[SearchType, float] | None = None,
    ) -> SearchResponse:
        """Execute hybrid search with custom weights.

        Args:
            request: Search request
            weights: Custom weights per search type

        Returns:
            SearchResponse
        """
        import asyncio
        import time

        start_time = time.time()
        effective_weights = weights or self.DEFAULT_WEIGHTS

        search_types = request.search_types or list(effective_weights.keys())

        # Filter weights for selected types
        active_weights = {
            t: effective_weights.get(t, 1.0)
            for t in search_types
        }

        # Execute searches in parallel
        tasks = {}
        if SearchType.DENSE in search_types:
            tasks[SearchType.DENSE] = self.dense_search(
                request.query, request.user_id, request.user_groups, request.top_k * 2
            )
        if SearchType.SPARSE in search_types:
            tasks[SearchType.SPARSE] = self.sparse_search(
                request.query, request.user_id, request.user_groups, request.top_k * 2
            )
        if SearchType.GRAPH in search_types:
            tasks[SearchType.GRAPH] = self.graph_search(
                request.query, request.user_id, request.user_groups, request.top_k * 2
            )

        results_list = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        results_by_type = {}
        for search_type, result in zip(tasks.keys(), results_list):
            if not isinstance(result, Exception):
                results_by_type[search_type] = result

        # Merge with weights
        merged = self._merge_results(
            results_by_type,
            top_k=request.top_k,
            weights=active_weights,
        )

        return SearchResponse(
            results=merged,
            total=len(merged),
            search_time_ms=(time.time() - start_time) * 1000,
            search_types_used=list(results_by_type.keys()),
        )

    def suggest_weights(self, query: str) -> dict[SearchType, float]:
        """Suggest weights based on query characteristics.

        Args:
            query: Search query

        Returns:
            Suggested weights
        """
        # Simple heuristic based on query length and type
        words = query.split()

        if len(words) <= 2:
            # Short query: prefer keyword match
            return {
                SearchType.DENSE: 0.6,
                SearchType.SPARSE: 1.0,
                SearchType.GRAPH: 0.8,
            }
        elif any(word in query.lower() for word in ['similar', 'like', 'related']):
            # Semantic query: prefer dense
            return {
                SearchType.DENSE: 1.0,
                SearchType.SPARSE: 0.5,
                SearchType.GRAPH: 0.7,
            }
        else:
            # Balanced
            return self.DEFAULT_WEIGHTS
```

**완료 기준:**
- [ ] 기본 가중치 설정
- [ ] hybrid_search_with_weights 구현
- [ ] suggest_weights 구현

---

### Step 4: 테스트 작성 (1.5h)

**작업 내용:**
1. Hybrid search 테스트
2. RRF 병합 테스트
3. 성능 테스트

**tests/unit/test_services/test_hybrid_search.py:**
```python
"""Tests for hybrid search."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.search_service import SearchService
from src.domain.models.search import (
    SearchRequest,
    SearchResult,
    SearchType,
)


@pytest.fixture
def search_service_with_mocks() -> SearchService:
    """Create search service with all mocks."""
    milvus = MagicMock()
    embedding = MagicMock()
    embedding.encode.return_value = MagicMock(
        dense=[[0.1] * 1024],
        sparse=[{1: 0.5}],
    )
    acl = MagicMock()
    acl.get_accessible_documents = AsyncMock(return_value=["doc-1"])
    acl.build_milvus_filter.return_value = 'doc_uuid in ["doc-1"]'
    neo4j = MagicMock()

    return SearchService(milvus, embedding, acl, neo4j)


class TestRRFMerging:
    """Tests for RRF result merging."""

    def test_calculate_rrf_scores(
        self,
        search_service_with_mocks: SearchService,
    ) -> None:
        """Test RRF score calculation."""
        results_by_type = {
            SearchType.DENSE: [
                SearchResult("c1", "d1", 0.9, SearchType.DENSE),
                SearchResult("c2", "d1", 0.8, SearchType.DENSE),
            ],
            SearchType.SPARSE: [
                SearchResult("c2", "d1", 0.85, SearchType.SPARSE),
                SearchResult("c1", "d1", 0.7, SearchType.SPARSE),
            ],
        }

        merged = search_service_with_mocks._calculate_rrf_scores(results_by_type)

        # c2 appears in both, should have higher combined score
        assert "c1" in merged
        assert "c2" in merged
        assert len(merged["c2"].sources) == 2  # Found in both

    def test_merge_results_deduplication(
        self,
        search_service_with_mocks: SearchService,
    ) -> None:
        """Test that duplicate chunks are merged."""
        results_by_type = {
            SearchType.DENSE: [
                SearchResult("c1", "d1", 0.9, SearchType.DENSE),
            ],
            SearchType.SPARSE: [
                SearchResult("c1", "d1", 0.85, SearchType.SPARSE),
            ],
        }

        merged = search_service_with_mocks._merge_results(results_by_type, top_k=10)

        assert len(merged) == 1
        assert merged[0].search_type == SearchType.HYBRID

    def test_merge_results_top_k(
        self,
        search_service_with_mocks: SearchService,
    ) -> None:
        """Test top_k limit on merged results."""
        results_by_type = {
            SearchType.DENSE: [
                SearchResult(f"c{i}", "d1", 0.9 - i * 0.1, SearchType.DENSE)
                for i in range(5)
            ],
        }

        merged = search_service_with_mocks._merge_results(results_by_type, top_k=3)

        assert len(merged) == 3


class TestHybridSearch:
    """Tests for hybrid search."""

    async def test_hybrid_search_all_types(
        self,
        search_service_with_mocks: SearchService,
    ) -> None:
        """Test hybrid search with all search types."""
        service = search_service_with_mocks

        # Mock individual searches
        service.dense_search = AsyncMock(
            return_value=[SearchResult("c1", "d1", 0.9, SearchType.DENSE)]
        )
        service.sparse_search = AsyncMock(
            return_value=[SearchResult("c2", "d1", 0.8, SearchType.SPARSE)]
        )
        service.graph_search = AsyncMock(
            return_value=[SearchResult("c3", "d1", 0.7, SearchType.GRAPH)]
        )

        request = SearchRequest(
            query="test query",
            user_id="user1",
            top_k=10,
        )

        response = await service.hybrid_search(request)

        assert response.total == 3
        assert len(response.search_types_used) == 3
        assert response.search_time_ms > 0

    async def test_hybrid_search_partial_failure(
        self,
        search_service_with_mocks: SearchService,
    ) -> None:
        """Test hybrid search continues when one type fails."""
        service = search_service_with_mocks

        service.dense_search = AsyncMock(
            return_value=[SearchResult("c1", "d1", 0.9, SearchType.DENSE)]
        )
        service.sparse_search = AsyncMock(side_effect=Exception("Sparse failed"))
        service.graph_search = AsyncMock(
            return_value=[SearchResult("c2", "d1", 0.7, SearchType.GRAPH)]
        )

        request = SearchRequest(query="test", user_id="user1", top_k=10)
        response = await service.hybrid_search(request)

        assert response.total == 2
        assert SearchType.SPARSE not in response.search_types_used

    async def test_hybrid_search_selected_types(
        self,
        search_service_with_mocks: SearchService,
    ) -> None:
        """Test hybrid search with selected types only."""
        service = search_service_with_mocks

        service.dense_search = AsyncMock(
            return_value=[SearchResult("c1", "d1", 0.9, SearchType.DENSE)]
        )
        service.sparse_search = AsyncMock(return_value=[])
        service.graph_search = AsyncMock(return_value=[])

        request = SearchRequest(
            query="test",
            user_id="user1",
            top_k=10,
            search_types=[SearchType.DENSE],
        )

        response = await service.hybrid_search(request)

        service.sparse_search.assert_not_called()
        service.graph_search.assert_not_called()


class TestPerformance:
    """Performance tests for hybrid search."""

    async def test_search_time_measurement(
        self,
        search_service_with_mocks: SearchService,
    ) -> None:
        """Test that search time is measured."""
        service = search_service_with_mocks

        service.dense_search = AsyncMock(return_value=[])
        service.sparse_search = AsyncMock(return_value=[])
        service.graph_search = AsyncMock(return_value=[])

        request = SearchRequest(query="test", user_id="user1", top_k=10)
        response = await service.hybrid_search(request)

        assert response.search_time_ms >= 0
```

**완료 기준:**
- [ ] RRF 병합 테스트
- [ ] 중복 제거 테스트
- [ ] 부분 실패 테스트
- [ ] 성능 측정 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_calculate_rrf_scores` | RRF 점수 계산 | 올바른 점수 |
| `test_merge_results_deduplication` | 중복 제거 | 단일 결과 |
| `test_hybrid_search_all_types` | 전체 검색 | 3개 타입 실행 |
| `test_hybrid_search_partial_failure` | 부분 실패 | 나머지 결과 반환 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_hybrid_search_performance` | P95 < 100ms | 성능 충족 |
| `test_hybrid_search_real_data` | 실제 데이터 | 관련 결과 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 검색 타임아웃 | High | Low | 개별 타임아웃 설정 |
| 메모리 사용 | Medium | Medium | 결과 크기 제한 |
| RRF 편향 | Low | Medium | 가중치 조정 가능 |

---

## 6. Definition of Done

- [ ] hybrid_search 메서드 구현
- [ ] 병렬 실행 (asyncio.gather)
- [ ] RRF 결과 병합
- [ ] 응답 시간 측정
- [ ] 부분 실패 처리
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 결과 병합 로직 | 1.5h | - |
| Step 2: Hybrid Search 구현 | 2h | - |
| Step 3: 가중치 설정 | 1h | - |
| Step 4: 테스트 | 1.5h | - |
| **Total** | **6h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
